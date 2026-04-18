#!/usr/bin/env python3
"""
Archive-Embeddings Generator
============================

Erzeugt semantische Vektoren für die Supabase-Tabelle ``archive`` (SIMAP-Archiv,
befüllt aus ``archive/simap_archive_to_supabase.py``) und schreibt sie in die
Tabelle ``embeddings``. Der Embedding-Raum ist identisch zu dem, der für
die Tabelle ``projects`` verwendet wird (gleiches Modell, gleicher Prefix,
gleiche Text-Struktur, gleiche Normalisierung) — damit ``pgvector``-Cosinus
zwischen aktuellen Projekten und Archiv direkt vergleichbar ist.

Zieltabelle (einmalig in Supabase anlegen):

    CREATE TABLE IF NOT EXISTS embeddings (
        simap_project_id      text        PRIMARY KEY,
        simap_publication_id  text,                  -- gewählte Publikation
        source_lang           text,                  -- DE/FR/IT/EN der Textbasis
        embedding             vector(384)  NOT NULL,
        text_hash             text         NOT NULL,
        updated_at            timestamptz  NOT NULL DEFAULT now()
    );

    CREATE INDEX IF NOT EXISTS embeddings_hnsw
        ON embeddings
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64);

Usage
-----
    # Dry-Run: 200 Zeilen aus archive laden, Embeddings rechnen, aber nichts schreiben
    python -m ML.generate_archive_embeddings -l 200 -d

    # Inkrementell (nur neue/geänderte Projekte) — Normalbetrieb
    python -m ML.generate_archive_embeddings

    # Alles neu rechnen (z.B. nach Änderung der Textbau-Logik)
    python -m ML.generate_archive_embeddings -f -b 128

Env-Vars (aus .env oder Shell):
    SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY      (oder SUPABASE_SERVICE_KEY / SUPABASE_KEY)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import requests
from dotenv import load_dotenv

from ML.embedding_text import build_archive_embedding_text, text_hash

# =============================================================================
# Konfiguration  —  MUSS IDENTISCH SEIN ZUR projects-Pipeline
# =============================================================================
EMBEDDING_MODEL_NAME = "intfloat/multilingual-e5-small"
EMBEDDING_DIM = 384
E5_PASSAGE_PREFIX = "passage: "

# Trunkierungs-Cap. Bewusst großzügiger als im alten ML_SAJF-Lauf (800):
# E5-small akzeptiert ~512 Tokens ≈ 1800–2200 Zeichen DE.
MAX_CHARS_DESCRIPTION = 1600
MAX_CHARS_TITLE = 500

DEFAULT_ENCODE_BATCH = 64          # auf GPU ruhig 128–256 setzen
PAGE_SIZE = 1000                   # Supabase REST PostgREST-Range
UPSERT_BATCH = 200                 # Zeilen pro Upsert-Request
SUPABASE_TIMEOUT = 60

SOURCE_TABLE = "archive"
TARGET_TABLE = "embeddings"

# Felder, die wir aus ``archive`` brauchen (ein REST-Call pro Seite).
SELECT_COLUMNS = ",".join([
    "simap_project_id",
    "simap_publication_id",
    "publication_date",
    "creation_language",
    "pub_type",
    "title_de", "title_fr",
    "description_de", "description_fr",
    "order_type",
    "process_type",
    "cpv_code_main",
    "cpv_codes",
    "bkp_codes",
    "canton",
])


# =============================================================================
# Logging
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("archive-emb")

# =============================================================================
# Supabase REST-Client (ohne supabase-py — analog zu simap_archive_to_supabase)
# =============================================================================
@dataclass
class Supa:
    url: str
    key: str

    @classmethod
    def from_env(cls) -> "Supa":
        env_path = Path(__file__).resolve().parent.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)
        else:
            load_dotenv()

        url = os.getenv("SUPABASE_URL", "").rstrip("/")
        key = (
            os.getenv("SUPABASE_SERVICE_ROLE_KEY")
            or os.getenv("SUPABASE_SERVICE_KEY")
            or os.getenv("SUPABASE_KEY")
            or ""
        )
        if not url or not key:
            log.error(
                "SUPABASE_URL und SUPABASE_SERVICE_ROLE_KEY müssen in .env "
                "oder Umgebung gesetzt sein."
            )
            sys.exit(1)
        return cls(url=url, key=key)

    def _headers(self, prefer: str = "") -> dict[str, str]:
        h = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }
        if prefer:
            h["Prefer"] = prefer
        return h

    def fetch_existing_hashes(self) -> dict[str, str]:
        """Liest alle vorhandenen (simap_project_id → text_hash) für Incremental."""
        log.info("Lade vorhandene Hashes aus %s …", TARGET_TABLE)
        hashes: dict[str, str] = {}
        offset = 0
        while True:
            url = (
                f"{self.url}/rest/v1/{TARGET_TABLE}"
                f"?select=simap_project_id,text_hash"
            )
            headers = self._headers()
            headers["Range-Unit"] = "items"
            headers["Range"] = f"{offset}-{offset + PAGE_SIZE - 1}"
            r = requests.get(url, headers=headers, timeout=SUPABASE_TIMEOUT)
            if r.status_code == 404:
                log.warning(
                    "Tabelle %s existiert noch nicht — bitte zuerst anlegen "
                    "(siehe Docstring oben).",
                    TARGET_TABLE,
                )
                return {}
            if r.status_code not in (200, 206):
                log.error("Hash-Fetch fehlgeschlagen: %d %s", r.status_code, r.text[:300])
                return hashes
            batch = r.json()
            if not batch:
                break
            for row in batch:
                pid = row.get("simap_project_id")
                th = row.get("text_hash")
                if pid and th:
                    hashes[str(pid)] = th
            if len(batch) < PAGE_SIZE:
                break
            offset += PAGE_SIZE
        log.info("  → %d vorhandene Embeddings", len(hashes))
        return hashes

    def iter_archive_rows(
        self, limit: int | None = None
    ) -> Iterable[dict[str, Any]]:
        """
        Iteriert alle Zeilen aus archive, paginiert per Range-Header.
        Bevorzugt die 'älteste' Publikation pro Projekt (ASC nach
        publication_date) damit wir die Ursprungs-Ausschreibung treffen,
        nicht den Zuschlag.
        """
        emitted = 0
        offset = 0
        while True:
            remaining = None if limit is None else max(0, limit - emitted)
            if remaining == 0:
                return
            page_size = PAGE_SIZE if remaining is None else min(PAGE_SIZE, remaining)

            url = (
                f"{self.url}/rest/v1/{SOURCE_TABLE}"
                f"?select={SELECT_COLUMNS}"
                f"&order=simap_project_id.asc,publication_date.asc"
            )
            headers = self._headers()
            headers["Range-Unit"] = "items"
            headers["Range"] = f"{offset}-{offset + page_size - 1}"
            r = requests.get(url, headers=headers, timeout=SUPABASE_TIMEOUT)
            if r.status_code not in (200, 206):
                log.error("Archive-Fetch fehlgeschlagen: %d %s",
                          r.status_code, r.text[:300])
                return
            batch = r.json()
            if not batch:
                return
            for row in batch:
                yield row
                emitted += 1
            if len(batch) < page_size:
                return
            offset += page_size

    def upsert_embeddings(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        url = (
            f"{self.url}/rest/v1/{TARGET_TABLE}"
            f"?on_conflict=simap_project_id"
        )
        headers = self._headers("resolution=merge-duplicates,return=minimal")
        r = requests.post(url, headers=headers, json=rows, timeout=SUPABASE_TIMEOUT * 2)
        if r.status_code not in (200, 201, 204):
            log.error("Upsert fehlgeschlagen: %d %s", r.status_code, r.text[:400])
            raise RuntimeError(f"Upsert failed ({r.status_code})")


# =============================================================================
# Deduplizierung: pro simap_project_id die beste Row wählen
# =============================================================================
def _score_row(row: dict[str, Any]) -> tuple[int, int, int]:
    """Höher = besser. Kriterien (lexikografisch absteigend):

        1. hat überhaupt Beschreibung (DE oder FR)
        2. Länge der Beschreibung
        3. hat Titel
    """
    desc_len = max(
        len(row.get("description_de") or ""),
        len(row.get("description_fr") or ""),
    )
    has_desc = 1 if desc_len > 0 else 0
    has_title = 1 if (row.get("title_de") or row.get("title_fr")) else 0
    return (has_desc, desc_len, has_title)


def dedupe_by_project(
    rows: Iterable[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Behält pro simap_project_id die semantisch reichste Publikation."""
    best: dict[str, dict[str, Any]] = {}
    total = 0
    for row in rows:
        total += 1
        pid = str(row.get("simap_project_id") or "").strip()
        if not pid:
            continue
        prev = best.get(pid)
        if prev is None or _score_row(row) > _score_row(prev):
            best[pid] = row
    log.info("  → Dedup: %d Publikationen → %d eindeutige Projekte",
             total, len(best))
    return best


# =============================================================================
# Main Pipeline
# =============================================================================
def main() -> int:
    parser = argparse.ArgumentParser(description="SIMAP Archive -> Embeddings")
    parser.add_argument(
        "-l", "--limit", type=int, default=None,
        help="Maximale Anzahl an Archiv-Zeilen, die geladen werden (Testing).",
    )
    parser.add_argument(
        "-d", "--dry-run", action="store_true",
        help="Embeddings berechnen, aber nichts nach Supabase schreiben.",
    )
    parser.add_argument(
        "-f", "--force-all", action="store_true",
        help="Hash-Vergleich ignorieren, alle Embeddings neu rechnen.",
    )
    parser.add_argument(
        "-b", "--batch-size", type=int, default=DEFAULT_ENCODE_BATCH,
        help=f"Encode-Batchsize (Default {DEFAULT_ENCODE_BATCH}).",
    )
    args = parser.parse_args()

    log.info("╔══════════════════════════════════════════════╗")
    log.info("║  Archive-Embeddings Generator                ║")
    log.info("╚══════════════════════════════════════════════╝")
    log.info("Modell: %s  |  Dim: %d  |  Prefix: '%s'",
             EMBEDDING_MODEL_NAME, EMBEDDING_DIM, E5_PASSAGE_PREFIX.strip())

    supa = Supa.from_env()

    # ── Phase A: Archiv laden + pro project_id deduplizieren ────────────────
    log.info("Lade archive (limit=%s) …", args.limit or "∞")
    t0 = time.time()
    rows_iter = supa.iter_archive_rows(limit=args.limit)
    per_project = dedupe_by_project(rows_iter)
    log.info("Archiv-Load fertig in %.1fs", time.time() - t0)

    # ── Phase B: Text + Hash pro Projekt ────────────────────────────────────
    payload: list[tuple[str, dict[str, Any], str, str, str]] = []
    empty_text = 0
    for pid, row in per_project.items():
        text, lang = build_archive_embedding_text(
            row,
            max_chars_title=MAX_CHARS_TITLE,
            max_chars_description=MAX_CHARS_DESCRIPTION,
        )
        if not text:
            empty_text += 1
            continue
        h = text_hash(text)
        payload.append((pid, row, text, lang, h))
    if empty_text:
        log.info("  %d Projekte ohne nutzbaren Text übersprungen", empty_text)

    # ── Phase C: Incremental-Filter ─────────────────────────────────────────
    existing = {} if args.force_all else supa.fetch_existing_hashes()
    to_encode = [
        (pid, row, text, lang, h)
        for (pid, row, text, lang, h) in payload
        if existing.get(pid) != h
    ]
    skipped = len(payload) - len(to_encode)
    log.info("Zu encoden: %d  |  unverändert (skip): %d", len(to_encode), skipped)

    if not to_encode:
        log.info("Nichts zu tun. Fertig.")
        return 0

    # ── Phase D: Modell laden ───────────────────────────────────────────────
    log.info("Lade Embedding-Modell (kann beim ersten Mal ~1 Min dauern) …")
    from sentence_transformers import SentenceTransformer
    import torch

    model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    if torch.cuda.is_available():
        model = model.to("cuda")
        log.info("  → GPU aktiv")
    else:
        log.info("  → CPU")

    # ── Phase E: Encoden ────────────────────────────────────────────────────
    texts_prefixed = [E5_PASSAGE_PREFIX + t for (_, _, t, _, _) in to_encode]
    log.info("Encode %d Texte mit batch_size=%d …",
             len(texts_prefixed), args.batch_size)
    t0 = time.time()
    embeddings = model.encode(
        texts_prefixed,
        batch_size=args.batch_size,
        show_progress_bar=True,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )
    log.info("  → %.1fs  (%.1f Texte/s)",
             time.time() - t0,
             len(texts_prefixed) / max(1e-6, time.time() - t0))

    assert embeddings.shape == (len(to_encode), EMBEDDING_DIM), (
        f"Unerwartete Embedding-Shape: {embeddings.shape}"
    )

    # ── Phase F: Upsert ─────────────────────────────────────────────────────
    if args.dry_run:
        log.info("Dry-Run aktiv — schreibe nichts.")
        # Sanity-Check: zeig einen Beispieltext
        (pid0, _, text0, lang0, h0) = to_encode[0]
        log.info("Beispiel project_id=%s lang=%s hash=%s",
                 pid0, lang0, h0[:8])
        log.info("Textanfang: %s", text0[:240].replace("\n", " "))
        log.info("Vektor[:6] = %s", np.round(embeddings[0][:6], 4).tolist())
        return 0

    log.info("Upsert in Batches von %d …", UPSERT_BATCH)
    inserted = 0
    failed = 0
    for i in range(0, len(to_encode), UPSERT_BATCH):
        chunk = to_encode[i:i + UPSERT_BATCH]
        chunk_emb = embeddings[i:i + UPSERT_BATCH]
        rows_out: list[dict[str, Any]] = []
        for (pid, row, _text, lang, h), emb in zip(chunk, chunk_emb):
            rows_out.append({
                "simap_project_id":     pid,
                "simap_publication_id": row.get("simap_publication_id"),
                "source_lang":          lang,
                "embedding":            emb.astype(np.float32).tolist(),
                "text_hash":            h,
            })
        try:
            supa.upsert_embeddings(rows_out)
            inserted += len(rows_out)
        except Exception as e:
            failed += len(rows_out)
            log.error("Batch-Upsert fehlgeschlagen: %s", e)

        if (i // UPSERT_BATCH) % 10 == 0:
            log.info("  %d / %d upserted", inserted, len(to_encode))

    log.info("Fertig: %d upserted, %d fehlgeschlagen, %d unverändert",
             inserted, failed, skipped)
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
