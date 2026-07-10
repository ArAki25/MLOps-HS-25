"""
End-to-End-Builder für public.embeddings (Model: BAAI/bge-m3, 1024d).

Pipeline pro Source:
  1. Rows paginiert aus Supabase laden (Keyset auf id.asc, PAGE_SIZE-Batches).
     Keyset statt Offset vermeidet den Postgres-Sort/Scan auf wachsende
     Offsets und damit die 500er (statement_timeout) bei großen Tabellen.
  2. Rohtext + text_hash per embeddings.text_builder.build_text erzeugen.
  3. Bestehenden text_hash + PK in embeddings in EINEM Query lookup'en;
     unveränderte Rows werden übersprungen (inkrementelles Update).
  4. Neue/geänderte Rows batched an bge-m3 (FP16 auf MPS/CUDA, FP32 auf CPU).
  5. Normalisierte 1024-d-Vektoren via UPSERT zurück in Supabase.

  Die drei Phasen (Fetch+HashCheck / GPU-Encode / Upsert) laufen in einer
  überlappenden Pipeline: während die GPU encodet, holt ein Thread bereits
  die nächste Page und prüft Hashes; gleichzeitig schreibt ein anderer Thread
  die fertige vorige Batch nach Supabase.  Zu encodende Zeilen werden über
  mehrere Pages gesammelt (ENCODE_ACCUM_MIN), damit die GPU mit vollen
  Batches (EMBED_BATCH) arbeitet statt mit Mikro-Batches pro Page.

Aufruf:
  python -m embeddings.build_embeddings --source all                 # projects + archive, full
  python -m embeddings.build_embeddings --source archive --limit 500 # smoke test
  python -m embeddings.build_embeddings --source project --dry-run   # kein Write, nur Statistik
  python -m embeddings.build_embeddings --source archive --force      # alles neu encoden
"""

from __future__ import annotations

import argparse
import logging
import os
import queue
import random
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any

import requests
from dotenv import load_dotenv

from .text_builder import BuiltText, build_text

load_dotenv()

try:
    from tqdm import tqdm  # type: ignore
except Exception:  # pragma: no cover
    tqdm = None

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = (
    os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    or os.environ.get("SUPABASE_KEY")
    or os.environ.get("SECRET_KEY")
    or ""
)

EMBEDDING_MODEL_NAME = "BAAI/bge-m3"
EMBEDDING_DIM        = 1024
# bge-m3 default max_length ist 8192 → extreme Padding-Verschwendung bei unseren
# ~500–2000 char Texten. 2048 deckt praktisch 100 % unserer Rohtexte.
ENCODE_MAX_SEQ = int(os.environ.get("EMBED_MAX_SEQ", "2048"))
ENCODE_BATCH   = int(os.environ.get("EMBED_BATCH",   "128"))
# Mindestanzahl Texts im Puffer, bevor die GPU anspringt (außer letzter Flush).
# Kleine Werte = mehr GPU-Calls mit wenigen Texts → GPU idle. Höher = volle Batches.
# Default = ENCODE_BATCH: erst encoden, wenn sich mindestens eine volle Batch angesammelt hat.
ENCODE_ACCUM_MIN = int(os.environ.get("ENCODE_ACCUM_MIN", str(ENCODE_BATCH)))
# Hard-Cap für RAM (Texte + Metadaten im Puffer), bevor zwangsweise geflusht wird.
ENCODE_ACCUM_MAX = int(os.environ.get("ENCODE_ACCUM_MAX", "4096"))
# Kleinere Pages = weniger Last pro Request (weniger 500 bei großen Tabellen).
# Klein halten: bei 57014 (statement_timeout) hilft nur kleinere Statements.
PAGE_SIZE      = int(os.environ.get("PAGE_SIZE", "150"))
UPSERT_BATCH   = int(os.environ.get("UPSERT_BATCH", "80"))
# (connect, read) — lange Reads wirken wie „hängen“, daher getrennt begrenzen
REST_TIMEOUT   = float(os.environ.get("REST_TIMEOUT", "120"))
REST_CONNECT_S = float(os.environ.get("REST_CONNECT_S", "15"))

# Seit Umstellung auf Keyset-Pagination (id=gt.<last>) irrelevant —
# count=exact wird bei Fetch-Pages nicht mehr verwendet, weil es auf großen
# Tabellen den statement_timeout auslöst. Variable bleibt nur für Backward-Compat,
# wird im Code aber nicht mehr gelesen.
REST_FETCH_PREFER_COUNT = os.environ.get("REST_FETCH_PREFER_COUNT", "").lower() in (
    "1", "true", "yes", "on",
)

# IDs pro embeddings-IN-Query; bei 500 wird automatisch halbiert.
EMBED_LOOKUP_CHUNK = int(os.environ.get("EMBED_LOOKUP_CHUNK", "40"))
EMBED_LOOKUP_MIN   = int(os.environ.get("EMBED_LOOKUP_MIN", "5"))

# Pause zwischen erfolgreichen Archiv-Pages (ms) — entlastet PostgREST.
# 0 = maximaler Durchsatz (GPU wird eher gefüttert). Bei 500ern wieder 25–75 setzen.
REST_PAGE_PAUSE_MS = float(os.environ.get("REST_PAGE_PAUSE_MS", "0"))
# Optional: Pause zwischen Upsert-Sub-Batches (ms), z. B. 40 bei vielen 500 beim Schreiben.
REST_UPSERT_PAUSE_MS = float(os.environ.get("REST_UPSERT_PAUSE_MS", "0"))

# Prefetch-Queue: wie viele PreparedBatch-Objekte dürfen warten (Fetch ahead vom GPU-Thread).
# Höher = Fetcher kann weiter vorausladen, GPU wartet seltener auf REST.
PREFETCH_DEPTH = int(os.environ.get("PREFETCH_DEPTH", "8"))

logger = logging.getLogger("build_embeddings")


# ---------------------------------------------------------------------------
# Supabase REST helpers — mit Retry + Backoff
# ---------------------------------------------------------------------------

_TRANSIENT_HTTP   = {408, 425, 429, 500, 502, 503, 504}
REST_RETRIES      = int(os.environ.get("REST_RETRIES",       "12"))
REST_BACKOFF_BASE = float(os.environ.get("REST_BACKOFF_BASE_S", "1.0"))
REST_BACKOFF_MAX  = float(os.environ.get("REST_BACKOFF_MAX_S",  "45.0"))
REST_MIN_PAGE     = int(os.environ.get("REST_MIN_PAGE_SIZE",  "25"))
# Bei splittbaren Requests (Page/IN/Upsert): wenige Retries, dann sofort kleiner —
# sonst wiederholt Postgres dieselbe zu lange Query 12× (57014).
REST_RETRIES_SPLIT = int(os.environ.get("REST_RETRIES_SPLIT", "2"))

# requests.Session ist nicht thread-safe → ein Session-Objekt pro Thread (Keep-Alive).
_tls = threading.local()


def _session() -> requests.Session:
    s = getattr(_tls, "session", None)
    if s is None:
        s = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=8, pool_maxsize=8, max_retries=0)
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        _tls.session = s
    return s


def _rest_timeout_tuple() -> tuple[float, float]:
    """requests timeout=(connect, read)"""
    r = REST_TIMEOUT
    return (min(REST_CONNECT_S, r), r)


def _sleep_backoff(attempt: int) -> float:
    base   = min(REST_BACKOFF_MAX, REST_BACKOFF_BASE * (2 ** max(0, attempt - 1)))
    jitter = random.random() * 0.25 * base
    return base + jitter


def _request_with_retry(
    method: str,
    url: str,
    *,
    max_retries: int | None = None,
    **kwargs,
) -> requests.Response:
    """HTTP-Request mit Backoff. max_retries=None → REST_RETRIES (volle Retries).

    Für Requests, die bei Timeout/500 durch *kleinere Chunks* gelöst werden sollen,
    max_retries=REST_RETRIES_SPLIT setzen — sonst feuert Postgres 57014 zwölfmal hintereinander.
    """
    to = kwargs.get("timeout")
    if to is None or isinstance(to, (int, float)):
        kwargs = {**kwargs, "timeout": _rest_timeout_tuple()}
    mr = REST_RETRIES if max_retries is None else max_retries
    last_exc: Exception | None = None
    for attempt in range(1, mr + 1):
        try:
            r = _session().request(method, url, **kwargs)
            if r.status_code in _TRANSIENT_HTTP:
                raise requests.HTTPError(f"{r.status_code} transient", response=r)
            return r
        except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as e:
            last_exc = e
            status = None
            body_hint = ""
            if isinstance(e, requests.HTTPError) and getattr(e, "response", None) is not None:
                status = e.response.status_code
                try:
                    body_hint = (e.response.text or "")[:200].replace("\n", " ")
                except Exception:
                    body_hint = ""
                if status not in _TRANSIENT_HTTP:
                    raise
            if attempt >= mr:
                raise
            wait_s = _sleep_backoff(attempt)
            logger.warning(
                "REST retry %d/%d %s status=%s in %.1fs | %s",
                attempt, mr, method, status, wait_s, body_hint or url[:120],
            )
            time.sleep(wait_s)
    assert last_exc is not None
    raise last_exc


def _rest_headers(extra: dict | None = None) -> dict:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError(
            "SUPABASE_URL / SUPABASE_KEY nicht gesetzt. "
            "Lege .env mit SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY an."
        )
    h = {
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Accept":        "application/json",
        "Content-Type":  "application/json",
    }
    if extra:
        h.update(extra)
    return h


# ---------------------------------------------------------------------------
# Spalten-Definitionen
# ---------------------------------------------------------------------------

_COLS_ARCHIVE = [
    "id", "simap_project_id", "simap_publication_id",
    "title_de", "title_fr", "description_de", "description_fr",
    "canton", "city", "country",
    "proc_office_name_de", "proc_office_name_fr", "proc_office_city", "proc_office_canton",
    "pub_type", "project_type", "project_subtype", "process_type", "order_type",
    "construction_type", "construction_category",
    "cpv_code_main", "cpv_codes", "bkp_codes",
    "winner_name", "winner_city", "winner_canton", "all_winners", "award_justification_de",
    "creation_language",
]
_COLS_PROJECT = list(_COLS_ARCHIVE)


# ---------------------------------------------------------------------------
# Supabase Fetch-Helfer
# ---------------------------------------------------------------------------

def _fetch_page(
    table: str,
    columns: list[str],
    after_id: Any,
    limit: int,
) -> list[dict]:
    """Keyset-Pagination über `id.asc`.

    Statt Range/Offset nutzen wir `id=gt.<after_id>` + `limit=N`. Postgres
    kann pro Page einen `Index Only Scan + Limit` fahren (O(log n) + O(N)),
    statt bei Offset 150k erst 150k Rows zu sortieren und zu verwerfen
    (= 57014 statement_timeout = HTTP 500). Bei transienten 500ern wird
    die Page-Size halbiert und erneut versucht, bis REST_MIN_PAGE erreicht ist.

    `after_id=None` signalisiert die erste Seite (kein Filter).
    """
    params = [f"select={','.join(columns)}", "order=id.asc"]
    if after_id is not None:
        # PostgREST erwartet den Raw-Wert; UUIDs und Bigints sind URL-safe.
        params.append(f"id=gt.{after_id}")
    base_url = f"{SUPABASE_URL}/rest/v1/{table}?" + "&".join(params)

    headers = _rest_headers()
    attempt_size = limit
    while True:
        try:
            r = _request_with_retry(
                "GET",
                f"{base_url}&limit={attempt_size}",
                max_retries=REST_RETRIES_SPLIT,
                headers=headers,
            )
            r.raise_for_status()
            return r.json()
        except requests.HTTPError as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status in (500, 502, 503, 504) and attempt_size > REST_MIN_PAGE:
                attempt_size = max(REST_MIN_PAGE, attempt_size // 2)
                logger.warning("REST %s → page-size reduziert auf %d", status, attempt_size)
                continue
            raise


def _fetch_total_count(table: str) -> int:
    url = f"{SUPABASE_URL}/rest/v1/{table}?select=id&limit=1"
    headers = _rest_headers({"Prefer": "count=exact", "Range-Unit": "items", "Range": "0-0"})
    r = _request_with_retry("GET", url, headers=headers)
    r.raise_for_status()
    try:
        return int(r.headers.get("Content-Range", "").split("/")[-1])
    except Exception:
        return -1


def _parse_embedding_lookup_rows(
    key_col: str, data: list[dict]
) -> dict[str, tuple[str, int | None]]:
    out: dict[str, tuple[str, int | None]] = {}
    for row in data:
        k = row.get(key_col)
        if k:
            rid = row.get("id")
            out[str(k)] = (row.get("text_hash") or "", int(rid) if rid is not None else None)
    return out


def _fetch_embedding_lookup_chunk(
    source: str,
    key_col: str,
    ids_chunk: list[str],
) -> dict[str, tuple[str, int | None]]:
    """Ein IN-Query; bei 500 nach allen Retries → Chunk halbieren."""
    if not ids_chunk:
        return {}
    in_list = ",".join(f'"{x}"' for x in ids_chunk)
    url = (
        f"{SUPABASE_URL}/rest/v1/embeddings"
        f"?select=id,{key_col},text_hash"
        f"&source=eq.{source}&{key_col}=in.({in_list})"
    )
    try:
        r = _request_with_retry(
            "GET", url, max_retries=REST_RETRIES_SPLIT, headers=_rest_headers(),
        )
        r.raise_for_status()
        return _parse_embedding_lookup_rows(key_col, r.json())
    except requests.HTTPError as e:
        status = getattr(getattr(e, "response", None), "status_code", None)
        if status in (500, 502, 503, 504) and len(ids_chunk) > EMBED_LOOKUP_MIN:
            mid = len(ids_chunk) // 2
            logger.warning(
                "embeddings lookup HTTP %s bei %d IDs → split %d|%d (57014=Postgres statement_timeout)",
                status, len(ids_chunk), mid, len(ids_chunk) - mid,
            )
            a = _fetch_embedding_lookup_chunk(source, key_col, ids_chunk[:mid])
            b = _fetch_embedding_lookup_chunk(source, key_col, ids_chunk[mid:])
            return {**a, **b}
        raise


def _fetch_existing_info(
    source: str, ids: list[str]
) -> dict[str, tuple[str, int | None]]:
    """{source_id: (text_hash, embedding_pk_id | None)} — ein Query pro Chunk, bei 500 rekursiv kleiner."""
    if not ids:
        return {}
    key_col = "project_id" if source == "project" else "archive_id"
    out: dict[str, tuple[str, int | None]] = {}
    chunk_size = max(1, EMBED_LOOKUP_CHUNK)
    for i in range(0, len(ids), chunk_size):
        chunk = ids[i:i + chunk_size]
        part = _fetch_embedding_lookup_chunk(source, key_col, chunk)
        out.update(part)
    return out


# ---------------------------------------------------------------------------
# Upsert
# ---------------------------------------------------------------------------

def _upsert_chunk_post(url: str, headers: dict, chunk: list[dict]) -> None:
    """POST eines Chunks; bei 500 nach Retries → halbieren (kleinere Payloads)."""
    if not chunk:
        return
    try:
        r = _request_with_retry(
            "POST", url, max_retries=REST_RETRIES_SPLIT, headers=headers, json=chunk,
        )
        if r.status_code >= 400:
            logger.error("upsert failed %s %s", r.status_code, r.text[:500])
            r.raise_for_status()
    except requests.HTTPError as e:
        status = getattr(getattr(e, "response", None), "status_code", None)
        if status in (500, 502, 503, 504) and len(chunk) > 1:
            mid = len(chunk) // 2
            logger.warning(
                "Upsert HTTP %s bei %d rows → split %d|%d",
                status, len(chunk), mid, len(chunk) - mid,
            )
            _upsert_chunk_post(url, headers, chunk[:mid])
            _upsert_chunk_post(url, headers, chunk[mid:])
            return
        raise


def upsert_embeddings(records: list[dict]) -> None:
    """Batched Upsert.  Die Records enthalten bereits `id` (PK), wenn sie
    ein Update sind — damit umgehen wir das partial-unique-index-Problem."""
    if not records:
        return
    url = f"{SUPABASE_URL}/rest/v1/embeddings"
    headers = _rest_headers({"Prefer": "resolution=merge-duplicates,return=minimal"})
    nchunks = (len(records) + UPSERT_BATCH - 1) // UPSERT_BATCH
    for j, i in enumerate(range(0, len(records), UPSERT_BATCH)):
        chunk = records[i:i + UPSERT_BATCH]
        _upsert_chunk_post(url, headers, chunk)
        if REST_UPSERT_PAUSE_MS > 0 and j + 1 < nchunks:
            time.sleep(REST_UPSERT_PAUSE_MS / 1000.0)


# ---------------------------------------------------------------------------
# Model loader
# ---------------------------------------------------------------------------

_model        = None
_model_device = None


def _get_device():
    import torch
    if torch.cuda.is_available():
        return torch.device("cuda"), torch.float16
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return torch.device("mps"), torch.float16
    return torch.device("cpu"), torch.float32


def _load_model():
    global _model, _model_device
    if _model is not None:
        return _model, _model_device
    from sentence_transformers import SentenceTransformer
    device, dtype = _get_device()
    logger.info(
        "Lade %s auf %s (dtype=%s, max_seq=%d, batch=%d)...",
        EMBEDDING_MODEL_NAME, device, dtype, ENCODE_MAX_SEQ, ENCODE_BATCH,
    )
    kwargs: dict[str, Any] = {"device": str(device)}
    try:
        _model = SentenceTransformer(
            EMBEDDING_MODEL_NAME, model_kwargs={"torch_dtype": dtype}, **kwargs,
        )
    except TypeError:
        _model = SentenceTransformer(EMBEDDING_MODEL_NAME, **kwargs)
    try:
        _model.max_seq_length = min(_model.max_seq_length, ENCODE_MAX_SEQ)
    except Exception:
        _model.max_seq_length = ENCODE_MAX_SEQ
    if str(device).startswith("cuda"):
        try:
            import torch
            torch.backends.cudnn.benchmark = True
        except Exception:
            pass
    _model_device = device
    return _model, _model_device


def encode_texts(texts: list[str]) -> list[list[float]]:
    model, _ = _load_model()
    vecs = model.encode(
        texts,
        batch_size=ENCODE_BATCH,
        normalize_embeddings=True,
        show_progress_bar=False,
        convert_to_numpy=True,
    )
    if vecs.shape[1] != EMBEDDING_DIM:
        raise RuntimeError(f"Unerwartete Embedding-Dim: {vecs.shape[1]} != {EMBEDDING_DIM}")
    return vecs.astype("float32").tolist()


# ---------------------------------------------------------------------------
# Pipeline-Datenstrukturen
# ---------------------------------------------------------------------------

@dataclass
class PreparedBatch:
    """Ergebnis des Prefetch-Threads: fertig aufbereitete Seite."""
    rows:          list[dict]               # Quell-Rows (nur mit nutzbarem Text)
    built:         list[BuiltText]          # text_builder-Ergebnisse
    existing_info: dict[str, tuple[str, int | None]]  # id → (hash, pk)
    page_offset:   int
    # Nur diese Seite (len(raw_rows)) — NICHT kumulativ, sonst explodieren
    # stats.seen / skipped_empty / tqdm total.
    rows_in_page:  int


_SENTINEL = object()   # Signal: kein weiteres Batch


@dataclass
class Stats:
    seen:          int = 0
    new:           int = 0
    unchanged:     int = 0
    updated:       int = 0
    skipped_empty: int = 0
    encoded:       int = 0


# ---------------------------------------------------------------------------
# Pipelined process_source
# ---------------------------------------------------------------------------

def _source_meta(source: str) -> tuple[str, str, list[str]]:
    if source == "archive":
        return "archive", "archive_id", _COLS_ARCHIVE
    if source == "project":
        return "projects", "project_id", _COLS_PROJECT
    raise ValueError(source)


def _row_to_upsert(
    row: dict,
    source: str,
    bt: BuiltText,
    vec: list[float],
    pk_id: int | None,
) -> dict:
    base: dict[str, Any] = {
        "source":            source,
        "pub_type":          row.get("pub_type"),
        "language":          bt.language,
        "text_hash":         bt.text_hash,
        "raw_text_preview":  bt.preview,
        "embedding":         vec,
        "embedding_model":   EMBEDDING_MODEL_NAME,
    }
    if pk_id is not None:
        base["id"] = pk_id   # UPDATE via PK, kein Conflict
    if source == "project":
        base["project_id"] = row.get("id")
    else:
        base["archive_id"]              = row.get("id")
        base["archive_publication_id"]  = row.get("simap_publication_id")
        base["archive_project_id"]      = row.get("simap_project_id")
    return base


def process_source(
    source: str,
    limit_total: int | None,
    dry_run: bool,
    force: bool,
) -> Stats:
    table, key_col, columns = _source_meta(source)
    stats  = Stats()
    total  = _fetch_total_count(table)
    logger.info(
        "=== source=%s  table=%s  total=%s  limit=%s  page_size=%d  upsert_batch=%d"
        "  prefetch_depth=%d  encode_batch=%d  encode_accum_min=%d  encode_accum_max=%d"
        "  page_pause_ms=%.0f  rest_retries=%d ===",
        source, table, total, limit_total or "∞",
        PAGE_SIZE, UPSERT_BATCH, PREFETCH_DEPTH, ENCODE_BATCH, ENCODE_ACCUM_MIN,
        ENCODE_ACCUM_MAX, REST_PAGE_PAUSE_MS, REST_RETRIES,
    )

    # Modell vor Fetch-Thread laden — sonst läuft REST lange allein, Log wirkt „verkehrt“.
    if not dry_run:
        _load_model()

    stop_event    = threading.Event()
    prefetch_q: queue.Queue = queue.Queue(maxsize=PREFETCH_DEPTH)
    upsert_q:   queue.Queue = queue.Queue(maxsize=PREFETCH_DEPTH)
    fetch_exc:  list[Exception] = []
    upsert_exc: list[Exception] = []

    # ------------------------------------------------------------------
    # Thread 1 — Fetch + HashCheck  (Keyset-Pagination über id.asc)
    # ------------------------------------------------------------------
    def _fetcher() -> None:
        last_id: Any = None       # None = erste Seite (kein id=gt.<…>-Filter)
        rows_fetched: int = 0     # nur für Logging / limit_total-Steuerung
        try:
            while not stop_event.is_set():
                if limit_total is not None and rows_fetched >= limit_total:
                    break
                page_size = PAGE_SIZE
                if limit_total is not None:
                    page_size = min(page_size, limit_total - rows_fetched)

                raw_rows = _fetch_page(table, columns, last_id, page_size)
                if not raw_rows:
                    break

                rows_in_page = len(raw_rows)

                # Keyset-Cursor weitersetzen: letzte id in der (id.asc) sortierten
                # Page ist das Maximum. Fehlt die id-Spalte, stimmt etwas Grundsätzliches
                # nicht — dann hart abbrechen, statt endlos auf derselben Page zu bleiben.
                tail_id = raw_rows[-1].get("id")
                if tail_id is None:
                    raise RuntimeError(
                        f"Row ohne 'id' in Tabelle {table} — Keyset kann nicht fortgesetzt werden."
                    )
                last_id = tail_id

                good_rows:  list[dict]       = []
                good_built: list[BuiltText]  = []
                for row in raw_rows:
                    try:
                        bt = build_text(row, source)
                    except Exception as e:
                        logger.warning("build_text id=%s: %s", row.get("id"), e)
                        continue
                    if not bt.raw_text:
                        continue
                    good_rows.append(row)
                    good_built.append(bt)

                # Einzelner kombinierter Hash+PK-Lookup (statt zwei getrennter Queries).
                # Auch bei --force brauchen wir die PK-IDs, damit PostgREST per UPDATE
                # arbeitet (kein INSERT → kein Conflict auf partial unique index).
                existing_info: dict[str, tuple[str, int | None]] = {}
                if good_rows and not dry_run:
                    ids = [str(r["id"]) for r in good_rows]
                    existing_info = _fetch_existing_info(source, ids)

                batch = PreparedBatch(
                    rows=good_rows,
                    built=good_built,
                    existing_info=existing_info,
                    page_offset=rows_fetched,
                    rows_in_page=rows_in_page,
                )
                prefetch_q.put(batch)

                rows_fetched += rows_in_page
                if REST_PAGE_PAUSE_MS > 0:
                    time.sleep(REST_PAGE_PAUSE_MS / 1000.0)
        except Exception as e:
            fetch_exc.append(e)
        finally:
            prefetch_q.put(_SENTINEL)

    # ------------------------------------------------------------------
    # Thread 2 — Upsert (schreibt fertig encodete Batches nach Supabase)
    # ------------------------------------------------------------------
    def _upserter() -> None:
        try:
            while True:
                item = upsert_q.get()
                if item is _SENTINEL:
                    return
                records: list[dict] = item
                upsert_embeddings(records)
        except Exception as e:
            upsert_exc.append(e)
            stop_event.set()

    # ------------------------------------------------------------------
    # Progress-Bar
    # ------------------------------------------------------------------
    effective_total = limit_total if limit_total else (total if total > 0 else None)
    pbar = None
    force_tqdm = os.environ.get("FORCE_TQDM", "").lower() in ("1", "true", "yes", "on")
    if tqdm is not None and (sys.stderr.isatty() or force_tqdm):
        pbar = tqdm(
            total=effective_total, desc=source, unit="rows",
            dynamic_ncols=True,
        )

    fetch_thread  = threading.Thread(target=_fetcher,  daemon=True, name="fetcher")
    upsert_thread = threading.Thread(target=_upserter, daemon=True, name="upserter")
    fetch_thread.start()
    upsert_thread.start()

    wall_t0     = time.perf_counter()
    batches_done = 0

    # Puffer für GPU: mehrere Pages können sich anreichern, bis mindestens
    # ENCODE_ACCUM_MIN Texts da sind → volle ENCODE_BATCH-Calls statt Mikro-Batches.
    pending_r:  list[dict] = []
    pending_bt: list[BuiltText] = []
    pending_pk: list[int | None] = []

    def _flush_pending(*, eof: bool) -> None:
        """Leert den Encode-Puffer in Stücken à ENCODE_BATCH (Rest bei eof)."""
        nonlocal pending_r, pending_bt, pending_pk, batches_done
        while pending_r:
            n = len(pending_r)
            if not eof and n < ENCODE_ACCUM_MIN and n < ENCODE_ACCUM_MAX:
                break
            if n >= ENCODE_BATCH:
                take = ENCODE_BATCH
            elif eof:
                take = n
            elif n >= ENCODE_ACCUM_MAX:
                take = min(ENCODE_BATCH, n)
            elif n >= ENCODE_ACCUM_MIN:
                take = n
            else:
                break

            chunk_r  = pending_r[:take]
            chunk_bt = pending_bt[:take]
            chunk_pk = pending_pk[:take]
            del pending_r[:take]
            del pending_bt[:take]
            del pending_pk[:take]

            texts = [bt.raw_text for bt in chunk_bt]
            t0_enc = time.perf_counter()
            if dry_run:
                vecs = [[0.0] * EMBEDDING_DIM] * len(texts)
            else:
                vecs = encode_texts(texts)
            dt_enc = time.perf_counter() - t0_enc
            stats.encoded += len(texts)
            batches_done += 1

            wall_elapsed = time.perf_counter() - wall_t0
            e2e_rate     = stats.seen / wall_elapsed if wall_elapsed > 0 else 0
            enc_rate     = len(texts) / dt_enc if dt_enc > 0 else 0
            logger.info(
                "[%s] batch=%d  encoded=%d  new=%d  upd=%d  unch=%d"
                "  enc_rate=%.0f it/s  e2e_rate=%.0f it/s  total_enc=%d  pend=%d",
                source, batches_done, len(texts),
                stats.new, stats.updated, stats.unchanged,
                enc_rate, e2e_rate, stats.encoded, len(pending_r),
            )

            if not dry_run:
                records = [
                    _row_to_upsert(r, source, bt, v, pk)
                    for r, bt, v, pk in zip(chunk_r, chunk_bt, vecs, chunk_pk, strict=False)
                ]
                upsert_q.put(records)

    try:
        while True:
            batch = prefetch_q.get()
            if batch is _SENTINEL:
                _flush_pending(eof=True)
                break

            if fetch_exc:
                raise fetch_exc[0]
            if upsert_exc:
                raise upsert_exc[0]

            stats.seen          += batch.rows_in_page
            stats.skipped_empty += batch.rows_in_page - len(batch.rows)

            if pbar is not None:
                pbar.update(batch.rows_in_page)

            # Filter: nur neue/geänderte Rows encoden
            for row, bt in zip(batch.rows, batch.built, strict=False):
                existing_hash, pk_id = batch.existing_info.get(str(row["id"]), ("", None))
                if not force and existing_hash == bt.text_hash:
                    stats.unchanged += 1
                    continue
                if existing_hash:
                    stats.updated += 1
                else:
                    stats.new += 1
                pending_r.append(row)
                pending_bt.append(bt)
                pending_pk.append(pk_id)

            if pbar is not None:
                pbar.set_postfix({
                    "enc":   stats.encoded,
                    "new":   stats.new,
                    "upd":   stats.updated,
                    "unch":  stats.unchanged,
                    "skip":  stats.skipped_empty,
                }, refresh=False)

            _flush_pending(eof=False)

    except KeyboardInterrupt:
        logger.warning("[%s] Ctrl+C — stoppe Pipeline ...", source)
        stop_event.set()
        upsert_q.put(_SENTINEL)
        fetch_thread.join(timeout=5)
        upsert_thread.join(timeout=10)
        logger.warning("[%s] Abgebrochen. Neustart macht inkrementell weiter.", source)
        if pbar is not None:
            pbar.close()
        raise
    finally:
        if pbar is not None:
            pbar.close()

    upsert_q.put(_SENTINEL)
    upsert_thread.join()

    if upsert_exc:
        raise upsert_exc[0]

    wall_total = time.perf_counter() - wall_t0
    logger.info(
        "[%s] DONE  seen=%d  new=%d  upd=%d  unch=%d  enc=%d  skip=%d"
        "  wall=%.0fs  avg_e2e=%.1f it/s",
        source, stats.seen, stats.new, stats.updated, stats.unchanged,
        stats.encoded, stats.skipped_empty,
        wall_total, stats.seen / wall_total if wall_total > 0 else 0,
    )
    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=os.environ.get("LOG_LEVEL", "INFO"),
    )
    ap = argparse.ArgumentParser(description="Baue public.embeddings (bge-m3, pipelined).")
    ap.add_argument("--source",   choices=["project", "archive", "all"], default="all")
    ap.add_argument("--limit",    type=int, default=None,
                    help="Max Rows pro Source (Smoke-Test)")
    ap.add_argument("--dry-run",  action="store_true",
                    help="Kein Upsert, kein Model-Load — nur Text-Builder + Hash-Diff")
    ap.add_argument("--force",    action="store_true",
                    help="Ignoriert bestehende Hashes — encodiert alles neu")
    args = ap.parse_args()

    try:
        import torch
        logger.info(
            "Torch %s | cuda=%s | device=%s",
            torch.__version__,
            torch.cuda.is_available(),
            torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu",
        )
    except Exception as e:
        logger.info("Torch device-check: %s", e)

    sources = ["project", "archive"] if args.source == "all" else [args.source]
    overall = Stats()
    try:
        for s in sources:
            st = process_source(s, limit_total=args.limit, dry_run=args.dry_run, force=args.force)
            overall.seen          += st.seen
            overall.new           += st.new
            overall.updated       += st.updated
            overall.unchanged     += st.unchanged
            overall.encoded       += st.encoded
            overall.skipped_empty += st.skipped_empty
    except KeyboardInterrupt:
        logger.warning("Abbruch. Exit 130.")
        return 130

    logger.info(
        "TOTAL seen=%d new=%d upd=%d unch=%d enc=%d skip=%d",
        overall.seen, overall.new, overall.updated,
        overall.unchanged, overall.encoded, overall.skipped_empty,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
