"""
Supabase Database Importer für SIMAP-Daten.

Importiert SIMAP-Projekte direkt in eine Supabase (PostgreSQL) Datenbank
mit automatischem Upsert (INSERT ... ON CONFLICT UPDATE).
"""
import csv
import logging
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
import psycopg2
from psycopg2.extras import execute_values


def get_db_connection():
    """
    Erstellt eine Datenbankverbindung zu Supabase aus der DATABASE_URL.

    Returns:
        psycopg2.connection: Datenbankverbindung

    Raises:
        ValueError: Wenn DATABASE_URL nicht gesetzt ist
        psycopg2.Error: Bei Verbindungsfehlern
    """
    db_url = os.environ.get("DATABASE_URL")

    if not db_url:
        raise ValueError(
            "DATABASE_URL nicht gefunden! "
            "Bitte setze die Umgebungsvariable oder erstelle eine .env-Datei."
        )

    # Konvertiere das Format wenn nötig
    # Supabase liefert: user=... password=... host=... port=... dbname=...
    # psycopg2 erwartet entweder das oder: postgresql://user:pass@host:port/db

    if not db_url.startswith("postgresql://") and not db_url.startswith("postgres://"):
        # Parse die key=value Format
        conn = psycopg2.connect(db_url)
    else:
        conn = psycopg2.connect(db_url)

    return conn


def create_table_if_not_exists(conn) -> None:
    """
    Erstellt die simap_projects Tabelle falls sie nicht existiert.

    Die Tabelle hat optimierte Datentypen und Indizes für schnelle Abfragen.
    Primary Key ist (project_id, publication_id) für Upserts.

    Args:
        conn: Datenbankverbindung
    """
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS simap_projects (
        -- Primary Keys
        project_id TEXT NOT NULL,
        publication_id TEXT NOT NULL,

        -- IDs & Nummern
        project_number TEXT,
        publication_number TEXT,

        -- Basis-Informationen
        title TEXT,
        description TEXT,
        publication_date TIMESTAMP,
        publication_type TEXT,
        project_type TEXT,
        project_subtype TEXT,

        -- Auftraggeber
        contracting_authority TEXT,

        -- Ort
        canton TEXT,
        city TEXT,
        postal_code TEXT,
        country TEXT,

        -- Fristen & Prozess
        submission_deadline TIMESTAMP,
        process_type TEXT,
        lots_type TEXT,

        -- Geschätzte Preise
        estimated_amount NUMERIC,
        estimated_currency TEXT,

        -- Award-Informationen (Zuschläge)
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

        -- Klassifizierungen
        cpv_code TEXT,
        additional_cpv_codes TEXT,
        bkp_codes TEXT,
        ebkph_codes TEXT,
        ebkpt_codes TEXT,
        npk_codes TEXT,

        -- Weitere Details
        order_type TEXT,
        construction_type TEXT,
        construction_category TEXT,
        creation_language TEXT,

        -- Metadaten
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),

        -- Primary Key Constraint
        PRIMARY KEY (project_id, publication_id)
    );

    -- Indizes für häufige Abfragen
    CREATE INDEX IF NOT EXISTS idx_simap_publication_date ON simap_projects(publication_date DESC);
    CREATE INDEX IF NOT EXISTS idx_simap_publication_type ON simap_projects(publication_type);
    CREATE INDEX IF NOT EXISTS idx_simap_canton ON simap_projects(canton);
    CREATE INDEX IF NOT EXISTS idx_simap_process_type ON simap_projects(process_type);
    CREATE INDEX IF NOT EXISTS idx_simap_creation_language ON simap_projects(creation_language);

    -- Volltext-Suche Index für Titel und Beschreibung
    CREATE INDEX IF NOT EXISTS idx_simap_title_search ON simap_projects USING GIN(to_tsvector('german', COALESCE(title, '')));
    CREATE INDEX IF NOT EXISTS idx_simap_description_search ON simap_projects USING GIN(to_tsvector('german', COALESCE(description, '')));
    """

    with conn.cursor() as cur:
        cur.execute(create_table_sql)
        conn.commit()

    logging.info("✓ Tabelle 'simap_projects' bereit")


def import_records_to_db(
    records: List[Dict[str, Any]],
    conn,
    batch_size: int = 100
) -> Dict[str, int]:
    """
    Importiert Records direkt in die Datenbank mit Upsert-Logik.

    Verwendet ON CONFLICT UPDATE um bestehende Records zu aktualisieren.
    Arbeitet in Batches für bessere Performance.

    Args:
        records: Liste von Projekt-Dictionaries
        conn: Datenbankverbindung
        batch_size: Anzahl Records pro Batch

    Returns:
        Dictionary mit Statistiken (inserted, updated, failed)
    """
    if not records:
        logging.warning("Keine Records zum Importieren")
        return {"inserted": 0, "updated": 0, "failed": 0}

    # Definiere alle möglichen Felder (entsprechend der Tabelle)
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
        "creation_language"
    ]

    # SQL Statement mit Upsert
    placeholders = ", ".join(["%s"] * len(fields))
    update_fields = ", ".join([f"{f} = EXCLUDED.{f}" for f in fields if f not in ["project_id", "publication_id"]])

    insert_sql = f"""
    INSERT INTO simap_projects ({", ".join(fields)}, updated_at)
    VALUES %s
    ON CONFLICT (project_id, publication_id)
    DO UPDATE SET
        {update_fields},
        updated_at = NOW()
    """

    stats = {"inserted": 0, "updated": 0, "failed": 0}

    # Verarbeite in Batches
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]

        # Konvertiere Records zu Tupeln
        values = []
        for record in batch:
            # Extrahiere Werte in der richtigen Reihenfolge
            row = []
            for field in fields:
                value = record.get(field)
                # Leere Strings zu None konvertieren für saubere DB
                if value == "":
                    value = None
                row.append(value)
            values.append(tuple(row))

        try:
            with conn.cursor() as cur:
                # execute_values ist viel schneller als einzelne INSERTs
                execute_values(
                    cur,
                    insert_sql,
                    values,
                    template=f"({placeholders}, NOW())",
                    page_size=batch_size
                )
                conn.commit()
                stats["inserted"] += len(batch)

            logging.info(f"✓ Batch {i//batch_size + 1}: {len(batch)} Records importiert")

        except psycopg2.Error as e:
            logging.error(f"✗ Fehler bei Batch {i//batch_size + 1}: {e}")
            conn.rollback()
            stats["failed"] += len(batch)

    return stats


def import_csv_to_db(csv_file: str, batch_size: int = 100) -> Dict[str, int]:
    """
    Importiert eine CSV-Datei direkt in die Supabase-Datenbank.

    Args:
        csv_file: Pfad zur CSV-Datei
        batch_size: Anzahl Records pro Batch

    Returns:
        Dictionary mit Statistiken (inserted, updated, failed)

    Beispiel:
        stats = import_csv_to_db("data/simap_projects.csv")
        print(f"Importiert: {stats['inserted']}, Fehlgeschlagen: {stats['failed']}")
    """
    csv_path = Path(csv_file)

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV-Datei nicht gefunden: {csv_file}")

    logging.info(f"Starte CSV-Import: {csv_file}")

    # Verbindung herstellen
    conn = get_db_connection()
    logging.info("✓ Datenbankverbindung hergestellt")

    try:
        # Tabelle erstellen
        create_table_if_not_exists(conn)

        # CSV lesen
        records = []
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            records = list(reader)

        logging.info(f"✓ {len(records)} Records aus CSV gelesen")

        # In DB importieren
        stats = import_records_to_db(records, conn, batch_size=batch_size)

        logging.info("=" * 60)
        logging.info("IMPORT ABGESCHLOSSEN")
        logging.info("=" * 60)
        logging.info(f"Erfolgreich: {stats['inserted']}")
        logging.info(f"Fehlgeschlagen: {stats['failed']}")
        logging.info("=" * 60)

        return stats

    finally:
        conn.close()
        logging.info("✓ Datenbankverbindung geschlossen")


def import_records_directly(
    records: List[Dict[str, Any]],
    batch_size: int = 100
) -> Dict[str, int]:
    """
    Importiert Records direkt aus Python (ohne CSV-Zwischenschritt).

    Nützlich für automatisierte Pipelines die direkt von der API
    in die Datenbank schreiben.

    Args:
        records: Liste von Projekt-Dictionaries (von extract_project_data)
        batch_size: Anzahl Records pro Batch

    Returns:
        Dictionary mit Statistiken (inserted, updated, failed)

    Beispiel:
        from Simap.api import SimapClient
        from Simap.extract import extract_project_data

        client = SimapClient()
        records = []
        for project in client.get_projects(params):
            details = client.get_project_details(...)
            record = extract_project_data(project, details)
            records.append(record)

        stats = import_records_directly(records)
    """
    if not records:
        logging.warning("Keine Records zum Importieren")
        return {"inserted": 0, "updated": 0, "failed": 0}

    logging.info(f"Starte direkten Import von {len(records)} Records")

    # Verbindung herstellen
    conn = get_db_connection()
    logging.info("✓ Datenbankverbindung hergestellt")

    try:
        # Tabelle erstellen
        create_table_if_not_exists(conn)

        # In DB importieren
        stats = import_records_to_db(records, conn, batch_size=batch_size)

        logging.info("=" * 60)
        logging.info("IMPORT ABGESCHLOSSEN")
        logging.info("=" * 60)
        logging.info(f"Erfolgreich: {stats['inserted']}")
        logging.info(f"Fehlgeschlagen: {stats['failed']}")
        logging.info("=" * 60)

        return stats

    finally:
        conn.close()
        logging.info("✓ Datenbankverbindung geschlossen")
