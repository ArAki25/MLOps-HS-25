#!/usr/bin/env python
"""
Einfaches Test-Skript für die SIMAP API v2.

Testet die get_projects Methode mit dem neuen Endpunkt.
"""
import logging
import os
import sys
from datetime import datetime, timedelta

# Füge Parent-Verzeichnis zum Path hinzu
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
from Simap.api import SimapClient

load_dotenv()

# Logging konfigurieren
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


def test_api():
    """Testet die SIMAP API mit verschiedenen Parametern."""
    
    client = SimapClient()
    
    # Test 1: Einfacher Test mit Datum (letzte 7 Tage)
    test_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    
    logger.info("=" * 60)
    logger.info("TEST 1: Einfacher Test mit Datum")
    logger.info(f"Datum: {test_date}")
    logger.info("=" * 60)
    
    params = {
        "start_date": test_date
        # search Parameter weglassen, da newestPublicationFrom als Filter ausreicht
    }
    
    try:
        count = 0
        for project in client.get_projects(params):
            count += 1
            if count == 1:
                logger.info(f"✓ Erste Projekt-Daten erhalten: {list(project.keys())[:5]}...")
            if count >= 5:  # Nur erste 5 Projekte anzeigen
                logger.info(f"✓ API funktioniert! {count} Projekte erfolgreich geladen.")
                break
                
    except Exception as e:
        logger.error(f"✗ Fehler: {e}")
        return False
    
    # Test 2: Test mit Kantonen (falls konfiguriert)
    try:
        from config import DEFAULT_CANTONS
        if DEFAULT_CANTONS:
            logger.info("")
            logger.info("=" * 60)
            logger.info("TEST 2: Test mit Kantonen")
            logger.info(f"Kantone: {DEFAULT_CANTONS}")
            logger.info("=" * 60)
            
            params = {
                "start_date": test_date,
                "cantons": DEFAULT_CANTONS if isinstance(DEFAULT_CANTONS, list) else [DEFAULT_CANTONS]
                # search Parameter weglassen
            }
            
            count = 0
            for project in client.get_projects(params):
                count += 1
                if count >= 3:
                    logger.info(f"✓ API mit Kantonen funktioniert! {count} Projekte geladen.")
                    break
    except ImportError:
        logger.info("Keine DEFAULT_CANTONS in config.py gefunden, überspringe Test 2")
    except Exception as e:
        logger.warning(f"Test 2 fehlgeschlagen: {e}")
    
    logger.info("")
    logger.info("=" * 60)
    logger.info("✓ Alle Tests abgeschlossen!")
    logger.info("=" * 60)
    
    return True


if __name__ == "__main__":
    success = test_api()
    sys.exit(0 if success else 1)
