"""
SIMAP CSV Exporter - Einfaches Tool zum Exportieren von Schweizer Ausschreibungsdaten.

Verwendung:
    python main.py

Das Script exportiert SIMAP-Projekte der letzten 30 Tage in eine CSV-Datei
und/oder importiert sie direkt in eine Supabase-Datenbank.
"""
import logging
import os
from dotenv import load_dotenv
from Simap.exporter import export_to_csv
from Simap.db_importer import import_csv_to_db, import_records_directly

# Lade .env Datei falls vorhanden
load_dotenv()


def main():
    """Hauptfunktion - Exportiert SIMAP-Daten als CSV."""
    # Logging konfigurieren
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # ========================================================================
    # EXPORT-KONFIGURATION
    # ========================================================================

    # Basis-Parameter
    OUTPUT_FILE = "data/simap_projects.csv"
    DAYS_BACK = 2              # Wie viele Tage zurück
    MAX_PAGES = None            # Maximale Anzahl API-Seiten (None = alle)
    MAX_PROJECTS = None          # Maximale Anzahl Projekte (None = alle)

    # Datenbank-Konfiguration
    EXPORT_TO_CSV = True         # CSV-Export aktivieren (WICHTIG: Muss True sein!)
    IMPORT_TO_DB = True          # Direkter Import in Supabase aktivieren (benötigt .env mit DATABASE_URL)
    USE_DIRECT_IMPORT = False    # True = Direkt von API in DB, False = CSV -> DB

    # ========================================================================
    # FILTER (Optional - None = kein Filter)
    # ========================================================================

    # Publikationstypen filtern
    # Optionen: "tender" (Ausschreibungen), "award" (Zuschläge), "cancellation"
    PUBLICATION_TYPES = "tender"
    # Beispiele:
    # PUBLICATION_TYPES = ["tender"]              # Nur offene Ausschreibungen
    # PUBLICATION_TYPES = ["award"]               # Nur Zuschläge
    # PUBLICATION_TYPES = ["tender", "award"]     # Beides

    # Kantone filtern
    # Optionen: "ZH", "BE", "LU", "GE", "VD", "AG", "SG", etc.
    CANTONS = ["ZH", "BL", "BS", "AG"]
    # Beispiele:
    # CANTONS = ["ZH", "BE"]                      # Nur Zürich und Bern
    # CANTONS = ["GE", "VD", "FR"]                # Nur Romandie

    # Sprachen filtern
    # Optionen: "de", "fr", "it", "en"
    LANGUAGES = ["de", "en"]
    # Beispiele:
    # LANGUAGES = ["de"]                          # Nur deutschsprachig
    # LANGUAGES = ["fr", "it"]                    # Nur Französisch & Italienisch

    # Prozesstypen filtern
    # Optionen: "open", "selective", "invitation"
    PROCESS_TYPES = ["open", "selective"]
    # Beispiele:
    # PROCESS_TYPES = ["open"]                    # Nur offene Verfahren

    # ========================================================================
    # EXPORT STARTEN
    # ========================================================================

    # Workflow 1: CSV Export (klassisch)
    if EXPORT_TO_CSV:
        logging.info("=" * 60)
        logging.info("STARTE CSV-EXPORT")
        logging.info("=" * 60)

        export_to_csv(
            output_file=OUTPUT_FILE,
            days_back=DAYS_BACK,
            max_pages=MAX_PAGES,
            max_projects=MAX_PROJECTS,
            publication_types=PUBLICATION_TYPES,
            cantons=CANTONS,
            languages=LANGUAGES,
            process_types=PROCESS_TYPES
        )

    # Workflow 2: Datenbank-Import
    if IMPORT_TO_DB:
        # Prüfe ob DATABASE_URL gesetzt ist
        if not os.environ.get("DATABASE_URL"):
            logging.error("DATABASE_URL nicht gesetzt! Überspringe DB-Import.")
            logging.error("Bitte .env Datei mit DATABASE_URL erstellen.")
        else:
            logging.info("")
            logging.info("=" * 60)
            logging.info("STARTE DATENBANK-IMPORT")
            logging.info("=" * 60)

            if USE_DIRECT_IMPORT:
                # Option A: Direkt von API in Datenbank (ohne CSV-Zwischenschritt)
                logging.info("Modus: Direkter Import (API -> DB)")
                logging.warning("HINWEIS: Direkter Import noch nicht implementiert!")
                logging.warning("Verwende stattdessen CSV-Import (setze USE_DIRECT_IMPORT = False)")

                # TODO: Für vollständig automatisierte Pipeline könnte man hier
                # die Daten direkt sammeln und importieren:
                #
                # from Simap.api import SimapClient
                # from Simap.extract import extract_project_data
                #
                # client = SimapClient()
                # records = []
                # for project in client.get_projects(...):
                #     details = client.get_project_details(...)
                #     record = extract_project_data(project, details)
                #     records.append(record)
                #
                # import_records_directly(records)

            else:
                # Option B: CSV in Datenbank importieren
                logging.info("Modus: CSV-Import (CSV -> DB)")

                if not EXPORT_TO_CSV:
                    logging.warning("CSV-Export ist deaktiviert, aber DB-Import benötigt CSV!")
                    logging.warning("Versuche existierende CSV zu importieren...")

                try:
                    stats = import_csv_to_db(OUTPUT_FILE, batch_size=500 )
                    logging.info("")
                    logging.info(f"✓ {stats['inserted']} Projekte in Datenbank importiert")
                    if stats['failed'] > 0:
                        logging.warning(f"✗ {stats['failed']} Projekte fehlgeschlagen")

                except FileNotFoundError:
                    logging.error(f"CSV-Datei nicht gefunden: {OUTPUT_FILE}")
                    logging.error("Bitte zuerst CSV exportieren (EXPORT_TO_CSV = True)")
                except Exception as e:
                    logging.error(f"Fehler beim DB-Import: {e}")

    # Abschluss
    logging.info("")
    logging.info("=" * 60)
    logging.info("FERTIG!")
    logging.info("=" * 60)


if __name__ == "__main__":
    main()
