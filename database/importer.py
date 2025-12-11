"""
Importer für SIMAP-Daten in PostgreSQL (Supabase).

Enthält Funktionen für Table-Setup, Batch-Upserts aus CSV oder direkten
Records sowie Hilfsfunktionen zur Wiederverwendung.
"""

import csv
import logging
from pathlib import Path
from typing import Any, Dict, List

import psycopg2
from psycopg2.extras import execute_values

from .connection import get_db_connection

logger = logging.getLogger(__name__)


def create_table_if_not_exists(conn) -> None:
    """Erstellt die Tabelle `simap_projects`, falls sie fehlt."""
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS simap_projects (
        project_id TEXT NOT NULL,
        publication_id TEXT NOT NULL,
        project_number TEXT,
        publication_number TEXT,
        title TEXT,
        description TEXT,
        publication_date TIMESTAMP,
        publication_type TEXT,
        project_type TEXT,
        project_subtype TEXT,
        contracting_authority TEXT,
        canton TEXT,
        city TEXT,
        postal_code TEXT,
        country TEXT,
        submission_deadline TIMESTAMP,
        process_type TEXT,
        lots_type TEXT,
        estimated_amount NUMERIC,
        estimated_currency TEXT,
        award_decision_date TIMESTAMP,
        number_of_submissions INTEGER,
        winner_name TEXT,
        winner_city TEXT,
        winner_canton TEXT,
        winner_postal_code TEXT,
        winner_country TEXT,
        award_amount NUMERIC,
        award_currency TEXT,
        award_vat_type TEXT,
        cpv_code TEXT,
        additional_cpv_codes TEXT,
        bkp_codes TEXT,
        ebkph_codes TEXT,
        ebkpt_codes TEXT,
        npk_codes TEXT,
        order_type TEXT,
        construction_type TEXT,
        construction_category TEXT,
        creation_language TEXT,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        PRIMARY KEY (project_id, publication_id)
    );
    CREATE INDEX IF NOT EXISTS idx_simap_publication_date ON simap_projects(publication_date DESC);
    CREATE INDEX IF NOT EXISTS idx_simap_publication_type ON simap_projects(publication_type);
    CREATE INDEX IF NOT EXISTS idx_simap_canton ON simap_projects(canton);
    CREATE INDEX IF NOT EXISTS idx_simap_process_type ON simap_projects(process_type);
    CREATE INDEX IF NOT EXISTS idx_simap_creation_language ON simap_projects(creation_language);
    CREATE INDEX IF NOT EXISTS idx_simap_title_search ON simap_projects USING GIN(to_tsvector('german', COALESCE(title, '')));
    CREATE INDEX IF NOT EXISTS idx_simap_description_search ON simap_projects USING GIN(to_tsvector('german', COALESCE(description, '')));
    """

    with conn.cursor() as cur:
        cur.execute(create_table_sql)
        conn.commit()

    logger.info("✓ Tabelle 'simap_projects' bereit")


def import_records_to_db(
    records: List[Dict[str, Any]],
    conn,
    batch_size: int = 1000,
) -> Dict[str, int]:
    """Importiert Records mit Upsert-Logik in Batches."""
    if not records:
        logger.warning("Keine Records zum Importieren")
        return {"inserted": 0, "updated": 0, "failed": 0}

    fields = [
        "project_id", "publication_id", "project_number", "publication_number",
        "title", "description", "publication_date", "publication_type",
        "project_type", "project_subtype", "contracting_authority",
        "canton", "city", "postal_code", "country",
        "submission_deadline", "process_type", "lots_type",
        "estimated_amount", "estimated_currency",
        "award_decision_date", "number_of_submissions",
        "winner_name", "winner_city", "winner_canton",
        "winner_postal_code", "winner_country",
        "award_amount", "award_currency", "award_vat_type",
        "cpv_code", "additional_cpv_codes", "bkp_codes",
        "ebkph_codes", "ebkpt_codes", "npk_codes",
        "order_type", "construction_type", "construction_category",
        "creation_language",
    ]

    placeholders = ", ".join(["%s"] * len(fields))
    update_fields = ", ".join(
        f"{f} = EXCLUDED.{f}"
        for f in fields
        if f not in ["project_id", "publication_id"]
    )

    insert_sql = f"""
    INSERT INTO simap_projects ({", ".join(fields)}, updated_at)
    VALUES %s
    ON CONFLICT (project_id, publication_id)
    DO UPDATE SET
        {update_fields},
        updated_at = NOW()
    """

    stats = {"inserted": 0, "updated": 0, "failed": 0}

    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        values = []
        for record in batch:
            row = []
            for field in fields:
                value = record.get(field)
                if value == "":
                    value = None
                row.append(value)
            values.append(tuple(row))

        try:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    insert_sql,
                    values,
                    template=f"({placeholders}, NOW())",
                    page_size=batch_size,
                )
                conn.commit()
                stats["inserted"] += len(batch)

            logger.info("✓ Batch %s: %s Records importiert", i // batch_size + 1, len(batch))
        except psycopg2.Error as exc:
            logger.error("✗ Fehler bei Batch %s: %s", i // batch_size + 1, exc)
            conn.rollback()
            stats["failed"] += len(batch)

    return stats


def import_csv_to_db(csv_file: str, batch_size: int = 1000) -> Dict[str, int]:
    """Importiert eine CSV-Datei in die Datenbank."""
    csv_path = Path(csv_file)

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV-Datei nicht gefunden: {csv_file}")

    logger.info("Starte CSV-Import: %s", csv_file)
    conn = get_db_connection()
    logger.info("✓ Datenbankverbindung hergestellt")

    try:
        create_table_if_not_exists(conn)

        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            records = list(reader)

        logger.info("✓ %s Records aus CSV gelesen", len(records))

        stats = import_records_to_db(records, conn, batch_size=batch_size)

        logger.info("=" * 60)
        logger.info("IMPORT ABGESCHLOSSEN")
        logger.info("=" * 60)
        logger.info("Erfolgreich: %s", stats["inserted"])
        logger.info("Fehlgeschlagen: %s", stats["failed"])
        logger.info("=" * 60)

        return stats
    finally:
        conn.close()
        logger.info("✓ Datenbankverbindung geschlossen")


def import_records_directly(
    records: List[Dict[str, Any]],
    batch_size: int = 1000,
) -> Dict[str, int]:
    """Importiert Records direkt aus Python ohne CSV-Zwischenschritt."""
    if not records:
        logger.warning("Keine Records zum Importieren")
        return {"inserted": 0, "updated": 0, "failed": 0}

    logger.info("Starte direkten Import von %s Records", len(records))

    conn = get_db_connection()
    logger.info("✓ Datenbankverbindung hergestellt")

    try:
        create_table_if_not_exists(conn)
        stats = import_records_to_db(records, conn, batch_size=batch_size)

        logger.info("=" * 60)
        logger.info("IMPORT ABGESCHLOSSEN")
        logger.info("=" * 60)
        logger.info("Erfolgreich: %s", stats["inserted"])
        logger.info("Fehlgeschlagen: %s", stats["failed"])
        logger.info("=" * 60)

        return stats
    finally:
        conn.close()
        logger.info("✓ Datenbankverbindung geschlossen")


