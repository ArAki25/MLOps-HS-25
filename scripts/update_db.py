#!/usr/bin/env python
"""
SIMAP Downloader - Exportiert Schweizer Ausschreibungen in Supabase.

Nutzung:
    python scripts/update_db.py                  # Nutzt Standard-Konfiguration
    python scripts/update_db.py --days 2         # Lädt Daten der letzten 2 Tage
    python scripts/update_db.py --start 2024-01-01 # Lädt ab spezifischem Datum
    
Für GitHub Actions:
    python scripts/update_db.py --days 2
"""
import argparse
import logging
import os
import sys
from datetime import datetime, timedelta

# Füge Parent-Verzeichnis zum Path hinzu
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

from database.importer import import_csv_to_db
from Simap.exporter import export_to_csv

# Lade config falls vorhanden
try:
    from config import DEFAULT_CANTONS, DEFAULT_LANGUAGES, DEFAULT_PROCESS_TYPES
except ImportError:
    DEFAULT_CANTONS = None
    DEFAULT_LANGUAGES = None
    DEFAULT_PROCESS_TYPES = None

load_dotenv()
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def main():
    """Exportiert SIMAP-Daten und importiert sie in Supabase."""

    # ========================================================================
    # STANDARD-KONFIGURATION (wird genutzt, wenn keine Argumente übergeben)
    # Kann über config.py überschrieben werden
    # ========================================================================

    # Dynamisches Standard-Datum: 30 Tage zurück
    default_start = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    
    # Verwende Config-Werte oder Fallbacks
    CANTONS = DEFAULT_CANTONS or [
        "ZH", "BE", "LU", "UR", "SZ", "OW", "NW", "GL", "ZG", "AG",
        "TG", "SH", "AI", "AR", "SG", "GR", "BL", "BS", "SO",
    ]

    PUBLICATION_TYPES = "tender"  # "tender", "award", oder None
    LANGUAGES = DEFAULT_LANGUAGES or ["de", "en"]
    PROCESS_TYPES = DEFAULT_PROCESS_TYPES or ["open", "selective"]

    # ========================================================================
    # Argument Parser
    # ========================================================================
    parser = argparse.ArgumentParser(description="SIMAP Downloader & Importer")
    parser.add_argument(
        "--days", type=int, help="Anzahl Tage zurück (z.B. 1 für heute/gestern)"
    )
    parser.add_argument(
        "--start", type=str, help="Startdatum YYYY-MM-DD (überschreibt --days)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Nur exportieren, nicht in DB importieren"
    )
    args = parser.parse_args()

    # Datum bestimmen
    start_date = default_start

    if args.start:
        start_date = args.start
        logging.info(f"Argument: Startdatum gesetzt auf {start_date}")
    elif args.days is not None:
        # Berechne Datum aus Tagen
        since = datetime.now() - timedelta(days=args.days)
        start_date = since.strftime("%Y-%m-%d")
        logging.info(f"Argument: {args.days} Tage zurück -> Startdatum {start_date}")
    else:
        logging.info(f"Keine Argumente: Nutze Standard-Startdatum {start_date}")

    # ========================================================================
    # Intern
    # ========================================================================

    OUTPUT_FILE = "data/simap_projects.csv"
    MAX_PAGES = None
    BATCH_SIZE = 1000

    # 1. EXPORT VON API
    logging.info("=" * 60)
    logging.info("1. EXPORTIERE VON SIMAP API...")
    logging.info("=" * 60)

    export_to_csv(
        output_file=OUTPUT_FILE,
        start_date=start_date,
        max_pages=MAX_PAGES,
        publication_types=PUBLICATION_TYPES,
        cantons=CANTONS,
        languages=LANGUAGES,
        process_types=PROCESS_TYPES,
        api_delay=0.1,
    )

    # 2. IMPORT IN DATENBANK
    if args.dry_run:
        logging.info("Dry-run Modus: Überspringe Datenbank-Import")
        return

    if not os.environ.get("DATABASE_URL"):
        logging.error("DATABASE_URL nicht in .env gesetzt!")
        return

    logging.info("")
    logging.info("=" * 60)
    logging.info("2. IMPORTIERE IN SUPABASE...")
    logging.info("=" * 60)

    try:
        stats = import_csv_to_db(OUTPUT_FILE, batch_size=BATCH_SIZE)
        logging.info("")
        logging.info(f"✓ {stats['inserted']} Projekte importiert")
        if stats['failed'] > 0:
            logging.warning(f"✗ {stats['failed']} Projekte fehlgeschlagen")
    except Exception as e:
        logging.error(f"Fehler: {e}")
        raise  # Re-raise für GitHub Actions Exit-Code

    logging.info("")
    logging.info("=" * 60)
    logging.info("✓ FERTIG!")
    logging.info("=" * 60)


if __name__ == "__main__":
    main()

