"""
Zentrale Konfiguration für das SIMAP-Projekt.

Alle konfigurierbaren Werte an einem Ort für einfache Anpassung.
Kann durch Umgebungsvariablen überschrieben werden.
"""
import os
from datetime import datetime, timedelta

# ============================================================================
# API Konfiguration
# ============================================================================

# SIMAP API Basis-URL
SIMAP_API_BASE_URL = "https://www.simap.ch/api"

# API Timeout und Retries
API_TIMEOUT = int(os.getenv("API_TIMEOUT", "20"))
API_MAX_RETRIES = int(os.getenv("API_MAX_RETRIES", "3"))
API_DELAY = float(os.getenv("API_DELAY", "0.1"))  # Sekunden zwischen Requests

# ============================================================================
# Datenbank Konfiguration
# ============================================================================

# Supabase DATABASE_URL (aus .env oder Umgebungsvariable)
DATABASE_URL = os.getenv("DATABASE_URL")

# Batch-Grösse für DB-Imports
DB_BATCH_SIZE = int(os.getenv("DB_BATCH_SIZE", "1000"))

# ============================================================================
# Standard-Filter für SIMAP-Abfragen
# ============================================================================

# Kantone die standardmässig abgefragt werden
# Kann überschrieben werden mit --cantons oder in Scripts
DEFAULT_CANTONS = [
    "ZH",  # Zürich
    "BE",  # Bern
    "LU",  # Luzern
    "UR",  # Uri
    "SZ",  # Schwyz
    "OW",  # Obwalden
    "NW",  # Nidwalden
    "GL",  # Glarus
    "ZG",  # Zug
    "AG",  # Aargau
    "TG",  # Thurgau
    "SH",  # Schaffhausen
    "AI",  # Appenzell Innerrhoden
    "AR",  # Appenzell Ausserrhoden
    "SG",  # St. Gallen
    "GR",  # Graubünden
    "BL",  # Basel-Landschaft
    "BS",  # Basel-Stadt
    "SO",  # Solothurn
]

# Alle Schweizer Kantone (für Referenz)
ALL_CANTONS = [
    "ZH", "BE", "LU", "UR", "SZ", "OW", "NW", "GL", "ZG", "FR",
    "SO", "BS", "BL", "SH", "AR", "AI", "SG", "GR", "AG", "TG",
    "TI", "VD", "VS", "NE", "GE", "JU",
]

# Standard-Sprachen
DEFAULT_LANGUAGES = ["de", "en"]

# Standard-Prozesstypen
DEFAULT_PROCESS_TYPES = ["open", "selective"]

# Standard-Publikationstyp
DEFAULT_PUBLICATION_TYPE = "tender"  # oder "award", None für alle

# ============================================================================
# Zeitraum-Konfiguration
# ============================================================================

# Standard: Wie viele Tage zurück für Abfragen
DEFAULT_DAYS_BACK = int(os.getenv("DEFAULT_DAYS_BACK", "30"))

# Berechne dynamisches Standard-Startdatum
def get_default_start_date(days_back: int = None) -> str:
    """Berechnet das Standard-Startdatum basierend auf days_back."""
    days = days_back or DEFAULT_DAYS_BACK
    return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

# ============================================================================
# Output-Konfiguration
# ============================================================================

# Standard-Ausgabedatei
DEFAULT_OUTPUT_FILE = "data/simap_projects.csv"

# Maximum Seiten für API-Abfragen (None = unbegrenzt)
MAX_PAGES = None

# Maximum Projekte pro Abfrage (None = unbegrenzt)
MAX_PROJECTS = None

# ============================================================================
# UI Konfiguration
# ============================================================================

# Flask Secret Key (sollte in Production aus .env kommen)
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")

# Standard-Port für UI
UI_PORT = int(os.getenv("UI_PORT", "5000"))

# Debug-Modus
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# ============================================================================
# ML Konfiguration
# ============================================================================

# TF-IDF Max Features
TFIDF_MAX_FEATURES = int(os.getenv("TFIDF_MAX_FEATURES", "15000"))

# Random Forest Estimators
RF_N_ESTIMATORS = int(os.getenv("RF_N_ESTIMATORS", "100"))

# Test-Split Grösse
TEST_SIZE = float(os.getenv("TEST_SIZE", "0.15"))

# ============================================================================
# Logging Konfiguration
# ============================================================================

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"

# ============================================================================
# Hilfsfunktionen
# ============================================================================

def get_config_summary() -> dict:
    """Gibt eine Zusammenfassung der aktuellen Konfiguration zurück."""
    return {
        "database": {
            "url_configured": DATABASE_URL is not None,
            "batch_size": DB_BATCH_SIZE,
        },
        "api": {
            "timeout": API_TIMEOUT,
            "max_retries": API_MAX_RETRIES,
            "delay": API_DELAY,
        },
        "filters": {
            "cantons": len(DEFAULT_CANTONS),
            "languages": DEFAULT_LANGUAGES,
            "process_types": DEFAULT_PROCESS_TYPES,
        },
        "output": {
            "default_file": DEFAULT_OUTPUT_FILE,
            "days_back": DEFAULT_DAYS_BACK,
        },
    }


if __name__ == "__main__":
    # Zeige Konfiguration wenn direkt ausgeführt
    import json
    print("SIMAP Konfiguration:")
    print(json.dumps(get_config_summary(), indent=2))

