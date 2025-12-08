"""
SIMAP Downloader - Exportiert Schweizer Ausschreibungen in Supabase.

Nutzung:
    python main.py                  # Nutzt Standard-Konfiguration (im Code)
    python main.py --days 2         # Lädt Daten der letzten 2 Tage
    python main.py --start 2024-01-01 # Lädt ab spezifischem Datum
"""
import argparse
import logging
import os
from datetime import datetime, timedelta

from dotenv import load_dotenv

from database.importer import import_csv_to_db
from Simap.exporter import export_to_csv

load_dotenv()
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def main():
    """Exportiert SIMAP-Daten und importiert sie in Supabase."""

    # ========================================================================
    # STANDARD-KONFIGURATION (wird genutzt, wenn keine Argumente übergeben)
    # ========================================================================

    DEFAULT_START_DATE = "2024-07-01"
    CANTONS = [
        "ZH",
        "BE",
        "LU",
        "UR",
        "SZ",
        "OW",
        "NW",
        "GL",
        "ZG",
        "AG",
        "TG",
        "SH",
        "AI",
        "AR",
        "SG",
        "GR",
        "BL",
        "BS",
        "SO",
    ]

    # Optional:
    PUBLICATION_TYPES = "tender"  # "tender", "award", oder None
    LANGUAGES = ["de", "en"]  # ["de"], ["fr"], oder None
    PROCESS_TYPES = ["open", "selective"]

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
    args = parser.parse_args()

    # Datum bestimmen
    start_date = DEFAULT_START_DATE
    days_back = None

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
        start_date=start_date,  # Nutzt das berechnete Datum
        max_pages=MAX_PAGES,
        publication_types=PUBLICATION_TYPES,
        cantons=CANTONS,
        languages=LANGUAGES,
        process_types=PROCESS_TYPES,
        api_delay=0.1,
    )

    # 2. IMPORT IN DATENBANK
    if not os.environ.get("DATABASE_URL"):
        logging.error("❌ DATABASE_URL nicht in .env gesetzt!")
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
        logging.error(f"❌ Fehler: {e}")

    logging.info("")
    logging.info("=" * 60)
    logging.info("✓ FERTIG!")
    logging.info("=" * 60)


if __name__ == "__main__":
    main()
