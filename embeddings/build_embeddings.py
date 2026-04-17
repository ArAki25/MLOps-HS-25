"""
End-to-End-Builder für public.archive_embeddings (Model: BAAI/bge-m3, 1024d).

Pipeline pro Source:
  1. Rows paginiert aus Supabase laden (Range-Header, 1000er-Batches).
  2. Rohtext + text_hash per embeddings.text_builder.build_text erzeugen.
  3. Bestehenden text_hash in archive_embeddings lookup'en; unveränderte Rows
     werden übersprungen (inkrementelles Update).
  4. Neue/geänderte Rows batched an bge-m3 (FP16 auf MPS/CUDA, FP32 auf CPU).
  5. Normalisierte 1024-d-Vektoren via UPSERT (on_conflict auf project_id bzw.
     archive_id) zurück in Supabase.

Aufruf:
  python -m embeddings.build_embeddings --source all                 # projects + archive, full
  python -m embeddings.build_embeddings --source archive --limit 500 # smoke test
  python -m embeddings.build_embeddings --source project --dry-run   # kein Write, nur Statistik
"""

from __future__ import annotations

import argparse
import logging
import math
import os
import sys
import time
from dataclasses import dataclass
from typing import Any, Iterable, Iterator, Optional

import requests
from dotenv import load_dotenv

from .text_builder import BuiltText, build_text

load_dotenv()

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
EMBEDDING_DIM = 1024
# bge-m3 default max_length ist 8192 → extreme Padding-Verschwendung bei unseren
# ~500–2000 char Texten. 2048 deckt Praktisch 100% unserer Rohtexte und macht
# das Encoding auf MPS FP16 um Faktor ~3 schneller.
ENCODE_MAX_SEQ = int(os.environ.get("EMBED_MAX_SEQ", "2048"))
ENCODE_BATCH   = int(os.environ.get("EMBED_BATCH", "64"))
PAGE_SIZE      = 1000
UPSERT_BATCH   = 500
REST_TIMEOUT   = 120

logger = logging.getLogger("build_embeddings")


# ---------------------------------------------------------------------------
# Supabase REST helpers
# ---------------------------------------------------------------------------

def _rest_headers(extra: Optional[dict] = None) -> dict:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError(
            "SUPABASE_URL / SUPABASE_KEY nicht gesetzt. "
            "Lege .env mit SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY (oder SUPABASE_KEY) an."
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


# ARCHIVE-Row-Spalten, die der Text-Builder tatsächlich liest (= minimal SELECT)
_COLS_ARCHIVE = [
    "id","simap_project_id","simap_publication_id",
    "title_de","title_fr","description_de","description_fr",
    "canton","city","country",
    "proc_office_name_de","proc_office_name_fr","proc_office_city","proc_office_canton",
    "pub_type","project_type","project_subtype","process_type","order_type",
    "construction_type","construction_category",
    "cpv_code_main","cpv_codes","bkp_codes",
    "winner_name","winner_city","winner_canton","all_winners","award_justification_de",
    "creation_language",
]

# PROJECTS-Row-Spalten (Schema ist weitgehend identisch, ein paar Felder fehlen)
_COLS_PROJECT = _COLS_ARCHIVE  # Columns sind ein Subset — Supabase ignoriert fehlende Felder nicht, also explizit:
_COLS_PROJECT = [c for c in _COLS_ARCHIVE]  # identisch, Supabase-Schema passt


def _fetch_page(table: str, columns: list[str], offset: int, limit: int) -> list[dict]:
    """Paginierter SELECT via PostgREST mit Range-Header."""
    url = f"{SUPABASE_URL}/rest/v1/{table}?select={','.join(columns)}&order=id.asc"
    headers = _rest_headers({
        "Range-Unit": "items",
        "Range":      f"{offset}-{offset + limit - 1}",
        "Prefer":     "count=exact",
    })
    r = requests.get(url, headers=headers, timeout=REST_TIMEOUT)
    r.raise_for_status()
    return r.json()


def _fetch_total_count(table: str) -> int:
    url = f"{SUPABASE_URL}/rest/v1/{table}?select=id&limit=1"
    headers = _rest_headers({"Prefer": "count=exact", "Range-Unit": "items", "Range": "0-0"})
    r = requests.get(url, headers=headers, timeout=REST_TIMEOUT)
    r.raise_for_status()
    cr = r.headers.get("Content-Range", "")
    try:
        return int(cr.split("/")[-1])
    except Exception:
        return -1


def iter_rows(table: str, columns: list[str], limit_total: Optional[int] = None) -> Iterator[dict]:
    """Yields rows paginiert. Respektiert optionales Gesamtlimit (für smoke-tests)."""
    offset = 0
    while True:
        page_size = PAGE_SIZE
        if limit_total is not None:
            remaining = limit_total - offset
            if remaining <= 0:
                return
            page_size = min(page_size, remaining)
        rows = _fetch_page(table, columns, offset, page_size)
        if not rows:
            return
        for r in rows:
            yield r
        if len(rows) < page_size:
            return
        offset += page_size


def _fetch_existing_hashes(source: str, ids: list[str]) -> dict[str, str]:
    """id -> text_hash Mapping aus archive_embeddings, für Inkrement-Logik."""
    if not ids:
        return {}
    key_col = "project_id" if source == "project" else "archive_id"
    out: dict[str, str] = {}
    # 200-er Batches gegen URL-Längen-Limits
    for i in range(0, len(ids), 200):
        chunk = ids[i:i + 200]
        in_list = ",".join(f'"{x}"' for x in chunk)
        url = (
            f"{SUPABASE_URL}/rest/v1/archive_embeddings"
            f"?select={key_col},text_hash&source=eq.{source}&{key_col}=in.({in_list})"
        )
        r = requests.get(url, headers=_rest_headers(), timeout=REST_TIMEOUT)
        r.raise_for_status()
        for row in r.json():
            k = row.get(key_col)
            if k:
                out[str(k)] = row.get("text_hash") or ""
    return out


def upsert_embeddings(records: list[dict]) -> None:
    """Batched Upsert via PostgREST (on_conflict auf partial unique indices)."""
    if not records:
        return
    url = f"{SUPABASE_URL}/rest/v1/archive_embeddings"
    headers = _rest_headers({
        "Prefer": "resolution=merge-duplicates,return=minimal",
    })
    for i in range(0, len(records), UPSERT_BATCH):
        chunk = records[i:i + UPSERT_BATCH]
        r = requests.post(url, headers=headers, json=chunk, timeout=REST_TIMEOUT)
        if r.status_code >= 400:
            logger.error("upsert failed %s %s", r.status_code, r.text[:500])
            r.raise_for_status()


# ---------------------------------------------------------------------------
# Model loader
# ---------------------------------------------------------------------------

_model = None
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
        "Loading %s on %s (dtype=%s, max_seq=%d, batch=%d)...",
        EMBEDDING_MODEL_NAME, device, dtype, ENCODE_MAX_SEQ, ENCODE_BATCH,
    )
    kwargs: dict[str, Any] = {"device": str(device)}
    try:
        _model = SentenceTransformer(
            EMBEDDING_MODEL_NAME, model_kwargs={"torch_dtype": dtype}, **kwargs,
        )
    except TypeError:
        _model = SentenceTransformer(EMBEDDING_MODEL_NAME, **kwargs)
    # max_seq_length vom Default (8192) runter auf einen realistischen Wert.
    try:
        _model.max_seq_length = min(_model.max_seq_length, ENCODE_MAX_SEQ)
    except Exception:
        _model.max_seq_length = ENCODE_MAX_SEQ
    _model_device = device
    return _model, _model_device


def encode_texts(texts: list[str]) -> list[list[float]]:
    """BGE-m3 Encode, L2-normalisiert, 1024d. Gibt Python-Listen für JSON-Upsert zurück."""
    model, _ = _load_model()
    vecs = model.encode(
        texts,
        batch_size=ENCODE_BATCH,
        normalize_embeddings=True,
        show_progress_bar=False,
        convert_to_numpy=True,
    )
    if vecs.shape[1] != EMBEDDING_DIM:
        raise RuntimeError(f"unexpected embedding dim {vecs.shape[1]} != {EMBEDDING_DIM}")
    return vecs.astype("float32").tolist()


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

@dataclass
class Stats:
    seen: int = 0
    new: int = 0
    unchanged: int = 0
    updated: int = 0
    skipped_empty: int = 0
    encoded: int = 0


def _source_meta(source: str) -> tuple[str, str, list[str]]:
    """source -> (table_name, id_key_column, columns)"""
    if source == "archive":
        return "archive", "archive_id", _COLS_ARCHIVE
    if source == "project":
        return "projects", "project_id", _COLS_PROJECT
    raise ValueError(source)


def _row_to_upsert(row: dict, source: str, bt: BuiltText, vec: list[float]) -> dict:
    base = {
        "source":          source,
        "pub_type":        row.get("pub_type"),
        "language":        bt.language,
        "text_hash":       bt.text_hash,
        "raw_text_preview": bt.preview,
        "embedding":       vec,
        "embedding_model": EMBEDDING_MODEL_NAME,
    }
    if source == "project":
        base["project_id"] = row.get("id")
    else:
        base["archive_id"] = row.get("id")
        base["archive_publication_id"] = row.get("simap_publication_id")
        base["archive_project_id"]     = row.get("simap_project_id")
    return base


def process_source(source: str, limit_total: Optional[int], dry_run: bool) -> Stats:
    table, key_col, columns = _source_meta(source)
    stats = Stats()
    total = _fetch_total_count(table)
    logger.info("=== source=%s table=%s total=%s limit=%s ===",
                source, table, total, limit_total if limit_total else "full")

    # Wir verarbeiten in logischen Batches von PAGE_SIZE (=1000), holen für jede
    # Batch die existierenden Hashes, builden Text, und feuern Encode+Upsert.
    buffer_rows: list[dict] = []
    buffer_texts: list[BuiltText] = []

    def flush_and_encode(batch_rows: list[dict], batch_built: list[BuiltText]) -> None:
        if not batch_rows:
            return
        ids = [str(r["id"]) for r in batch_rows]
        existing = _fetch_existing_hashes(source, ids) if not dry_run else {}

        to_encode_rows: list[dict] = []
        to_encode_built: list[BuiltText] = []
        for r, bt in zip(batch_rows, batch_built):
            prev = existing.get(str(r["id"]))
            if prev == bt.text_hash:
                stats.unchanged += 1
                continue
            if prev is None:
                stats.new += 1
            else:
                stats.updated += 1
            to_encode_rows.append(r)
            to_encode_built.append(bt)

        if not to_encode_rows:
            return

        texts = [bt.raw_text for bt in to_encode_built]
        t0 = time.time()
        vecs = encode_texts(texts) if not dry_run else [[0.0] * EMBEDDING_DIM] * len(texts)
        dt = time.time() - t0
        stats.encoded += len(texts)

        if not dry_run:
            recs = [_row_to_upsert(r, source, bt, v)
                    for r, bt, v in zip(to_encode_rows, to_encode_built, vecs)]
            upsert_embeddings(recs)
        logger.info(
            "[%s] batch encoded=%d unchanged=%d new=%d updated=%d rate=%.1f it/s",
            source, len(texts), stats.unchanged, stats.new, stats.updated,
            (len(texts) / dt) if dt > 0 else 0,
        )

    for row in iter_rows(table, columns, limit_total=limit_total):
        stats.seen += 1
        try:
            bt = build_text(row, source)
        except Exception as e:
            logger.warning("build_text failed for id=%s: %s", row.get("id"), e)
            stats.skipped_empty += 1
            continue
        if not bt.raw_text:
            stats.skipped_empty += 1
            continue
        buffer_rows.append(row)
        buffer_texts.append(bt)
        if len(buffer_rows) >= PAGE_SIZE:
            flush_and_encode(buffer_rows, buffer_texts)
            buffer_rows = []
            buffer_texts = []

    flush_and_encode(buffer_rows, buffer_texts)

    logger.info(
        "[%s] DONE seen=%d new=%d updated=%d unchanged=%d encoded=%d skipped=%d",
        source, stats.seen, stats.new, stats.updated, stats.unchanged,
        stats.encoded, stats.skipped_empty,
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
    ap = argparse.ArgumentParser(description="Baue archive_embeddings (bge-m3).")
    ap.add_argument("--source", choices=["project", "archive", "all"], default="all")
    ap.add_argument("--limit", type=int, default=None,
                    help="max rows per source (smoke test)")
    ap.add_argument("--dry-run", action="store_true",
                    help="kein Upsert, kein Model-Load — nur text-builder + hash-diff")
    args = ap.parse_args()

    sources = ["project", "archive"] if args.source == "all" else [args.source]
    overall = Stats()
    for s in sources:
        st = process_source(s, limit_total=args.limit, dry_run=args.dry_run)
        overall.seen      += st.seen
        overall.new       += st.new
        overall.updated   += st.updated
        overall.unchanged += st.unchanged
        overall.encoded   += st.encoded
        overall.skipped_empty += st.skipped_empty

    logger.info(
        "TOTAL seen=%d new=%d updated=%d unchanged=%d encoded=%d skipped=%d",
        overall.seen, overall.new, overall.updated, overall.unchanged,
        overall.encoded, overall.skipped_empty,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
