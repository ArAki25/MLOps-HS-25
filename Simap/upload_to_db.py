"""
Upload SIMAP CSVs to Supabase/Postgres with idempotent upserts.

Usage:
  # Erstmal Tabellen anlegen (einmalig)
  python Simap/upload_to_db.py --init

  # CSV hochladen (Default-Pfad: data/simap_projects.csv)
  python Simap/upload_to_db.py --csv data/simap_projects.csv --batch-size 1000
"""

from __future__ import annotations
import argparse
import hashlib
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

# --------------- Config ---------------

EXPECTED_COLS = {
    # CSV -> DB mapping (wir nehmen, was wir finden)
    "publication_id": "publication_id",
    "project_id": "project_id",
    "kind": "kind",
    "title": "title",
    "language": "language",
    "cpv_code": "cpv_code",
    "buyer_name": "buyer_name",
    "publication_date": "publication_date",
    "last_updated_at": "last_updated_at",
    "raw_json": "raw_json",  # optional
}

SCHEMA_SQL = """
create table if not exists simap_raw (
  publication_id text primary key,
  project_id     text not null,
  fetched_at     timestamptz not null default now(),
  payload        jsonb not null,
  content_hash   text not null
);

create table if not exists simap_publication (
  publication_id text primary key,
  project_id     text not null,
  kind           text,
  title          text,
  language       text,
  cpv_code       text,
  buyer_name     text,
  publication_date date,
  last_updated_at timestamptz,
  content_hash   text not null,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);

create index if not exists idx_pub_project on simap_publication(project_id);
create index if not exists idx_pub_updated on simap_publication(last_updated_at);
"""

# --------------- Helpers ---------------

def sha256_json(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()

def parse_date(val: Optional[str]) -> Optional[str]:
    if not val or (isinstance(val, float) and pd.isna(val)):
        return None
    # Versuche mehrere Formate; gebe ISO (YYYY-MM-DD/THH:MM:SS±ZZ) zurück
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d.%m.%Y"):
        try:
            dt = datetime.strptime(str(val), fmt)
            # Unterscheide Date vs DateTime
            if fmt == "%Y-%m-%d":
                return dt.date().isoformat()
            return dt.isoformat()
        except ValueError:
            continue
    # Fallback: pandas versuchen
    try:
        dt = pd.to_datetime(val, utc=False, errors="coerce")
        if pd.isna(dt):
            return None
        # Wenn Uhrzeit 00:00:00 → nur Datum
        if getattr(dt, "hour", 0) == 0 and getattr(dt, "minute", 0) == 0 and getattr(dt, "second", 0) == 0:
            return dt.date().isoformat()
        return dt.isoformat()
    except Exception:
        return None

def normalize_row(rec: Dict[str, Any]) -> Dict[str, Any]:
    # Rohdaten
    raw: Dict[str, Any] = {}
    if "raw_json" in rec and pd.notna(rec["raw_json"]):
        try:
            raw = json.loads(rec["raw_json"])
        except Exception:
            raw = {"_raw_text": str(rec["raw_json"])}
    else:
        # Minimal-RAW aus vorhandenen Spalten (besser als nichts)
        raw_keys = ["title", "description", "cpv_code", "language", "buyer_name"]
        raw = {k: rec.get(k) for k in raw_keys if k in rec}

    out = {
        "publication_id": str(rec.get("publication_id")),
        "project_id": str(rec.get("project_id")),
        "kind": rec.get("kind"),
        "title": rec.get("title"),
        "language": rec.get("language") or "de",
        "cpv_code": rec.get("cpv_code"),
        "buyer_name": rec.get("buyer_name"),
        "publication_date": parse_date(rec.get("publication_date")),
        "last_updated_at": parse_date(rec.get("last_updated_at")),
        "raw": raw,
        "content_hash": sha256_json(raw),
    }

    # Minimal-Validierung
    if not out["publication_id"] or not out["project_id"]:
        raise ValueError("publication_id und project_id sind Pflichtfelder.")
    return out


# --------------- DB Ops ---------------

def get_conn():
    load_dotenv()
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL fehlt in .env")
    return psycopg2.connect(db_url)

def init_schema():
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)

def upsert_batch(rows: List[Dict[str, Any]]):
    if not rows:
        return
    with get_conn() as conn, conn.cursor() as cur:
        # RAW
        execute_values(cur, """
            insert into simap_raw (publication_id, project_id, payload, content_hash)
            values %s
            on conflict (publication_id) do update
            set payload = excluded.payload,
                content_hash = excluded.content_hash,
                fetched_at = now();
        """, [(r["publication_id"], r["project_id"], json.dumps(r["raw"]), r["content_hash"]) for r in rows])

        # Normalisiert
        execute_values(cur, """
            insert into simap_publication
            (publication_id, project_id, kind, title, language, cpv_code,
             buyer_name, publication_date, last_updated_at, content_hash)
            values %s
            on conflict (publication_id) do update
            set kind = excluded.kind,
                title = excluded.title,
                language = excluded.language,
                cpv_code = excluded.cpv_code,
                buyer_name = excluded.buyer_name,
                publication_date = excluded.publication_date,
                last_updated_at = excluded.last_updated_at,
                content_hash = excluded.content_hash,
                updated_at = now();
        """, [(
            r["publication_id"], r["project_id"], r.get("kind"), r.get("title"), r.get("language"),
            r.get("cpv_code"), r.get("buyer_name"), r.get("publication_date"), r.get("last_updated_at"),
            r["content_hash"]
        ) for r in rows])

# --------------- CLI ---------------

def run(csv_path: str, batch_size: int = 1000):
    if not os.path.exists(csv_path):
        raise FileNotFoundError(csv_path)

    df = pd.read_csv(csv_path)
    # Map nur bestehender Spalten
    cols = {c: c for c in df.columns}
    missing = [c for c in ("publication_id","project_id") if c not in cols]
    if missing:
        raise ValueError(f"CSV fehlt Pflichtspalte(n): {missing}")

    # Normalisieren & in Batches upserten
    total = 0
    batch: List[Dict[str, Any]] = []
    for _, rec in df.iterrows():
        # Nur erwartete Spalten extrahieren
        src = {k: rec[v] for k, v in EXPECTED_COLS.items() if v in df.columns}
        n = normalize_row(src)
        batch.append(n)
        if len(batch) >= batch_size:
            upsert_batch(batch)
            total += len(batch)
            print(f"Upserted {total} rows...")
            batch.clear()
    if batch:
        upsert_batch(batch)
        total += len(batch)
    print(f"Done. Upserted {total} rows.")

def main():
    ap = argparse.ArgumentParser(description="Upload SIMAP CSV to Supabase/Postgres")
    ap.add_argument("--csv", default="data/simap_projects.csv", help="Pfad zur CSV")
    ap.add_argument("--batch-size", type=int, default=1000)
    ap.add_argument("--init", action="store_true", help="Schema anlegen und beenden")
    args = ap.parse_args()

    if args.init:
        init_schema()
        print("Schema initialisiert.")
        return

    run(args.csv, args.batch_size)

if __name__ == "__main__":
    main()
