"""
SIMAP Downloader - Exportiert Schweizer Ausschreibungen in Supabase.

Nutzung:
    python main.py

Ändere START_DATE und CANTONS unten um zu filtern!
"""
import logging
import os
from dotenv import load_dotenv
from Simap.exporter import export_to_csv
from Simap.db_importer import import_csv_to_db

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def main():
    """Exportiert SIMAP-Daten und importiert sie in Supabase."""

    # ========================================================================
    # ANPASSBAR: Hier die Konfiguration ändern!
    # ========================================================================

    START_DATE = "2024-07-01"           # ← Ändere das Datum hier!
    CANTONS = ["ZH", "BE", "LU", "UR", "SZ", "OW", "NW", "GL", "ZG", "AG", "TG", "SH", "AI", "AR", "SG", "GR", "BL", "BS", "SO"]

    # Optional:
    PUBLICATION_TYPES = "tender"        # "tender", "award", oder None
    LANGUAGES = ["de", "en"]            # ["de"], ["fr"], oder None
    PROCESS_TYPES = ["open", "selective"]

    # ========================================================================
    # Intern (normalerweise nicht ändern)
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
        start_date=START_DATE,
        max_pages=MAX_PAGES,
        publication_types=PUBLICATION_TYPES,
        cantons=CANTONS,
        languages=LANGUAGES,
        process_types=PROCESS_TYPES,
        api_delay=0.1
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
