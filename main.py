"""
SIMAP CSV Exporter - Einfaches Tool zum Exportieren von Schweizer Ausschreibungsdaten.

Verwendung:
    python main.py

Das Script exportiert SIMAP-Projekte der letzten 30 Tage in eine CSV-Datei.
"""
import logging
from Simap.exporter import export_to_csv


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
    DAYS_BACK = 30              # Wie viele Tage zurück
    MAX_PAGES = None              # Maximale Anzahl API-Seiten (None = alle)
    MAX_PROJECTS = 100         # Maximale Anzahl Projekte (None = alle)

    # ========================================================================
    # FILTER (Optional - None = kein Filter)
    # ========================================================================

    # Publikationstypen filtern
    # Optionen: "tender" (Ausschreibungen), "award" (Zuschläge), "cancellation"
    PUBLICATION_TYPES = None
    # Beispiele:
    # PUBLICATION_TYPES = ["tender"]              # Nur offene Ausschreibungen
    # PUBLICATION_TYPES = ["award"]               # Nur Zuschläge
    # PUBLICATION_TYPES = ["tender", "award"]     # Beides

    # Kantone filtern
    # Optionen: "ZH", "BE", "LU", "GE", "VD", "AG", "SG", etc.
    CANTONS = None
    # Beispiele:
    # CANTONS = ["ZH", "BE"]                      # Nur Zürich und Bern
    # CANTONS = ["GE", "VD", "FR"]                # Nur Romandie

    # Sprachen filtern
    # Optionen: "de", "fr", "it", "en"
    LANGUAGES = "de"
    # Beispiele:
    # LANGUAGES = ["de"]                          # Nur deutschsprachig
    # LANGUAGES = ["fr", "it"]                    # Nur Französisch & Italienisch

    # Prozesstypen filtern
    # Optionen: "open", "selective", "invitation"
    PROCESS_TYPES = "open"
    # Beispiele:
    # PROCESS_TYPES = ["open"]                    # Nur offene Verfahren

    # ========================================================================
    # EXPORT STARTEN
    # ========================================================================

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


if __name__ == "__main__":
    main()
