"""
Zentrale Verwaltung der Datenbankverbindung.

Stellt eine einheitliche `get_db_connection()` Funktion bereit, die alle
Datenbankzugriffe nutzen. Nutzt DATABASE_URL aus der Umgebung bzw. .env.
"""

import logging
import os
from typing import Optional

import psycopg2
from dotenv import load_dotenv

# .env laden, falls vorhanden
load_dotenv()

logger = logging.getLogger(__name__)


def get_db_connection(dsn: Optional[str] = None):
    """
    Erstellt eine psycopg2-Datenbankverbindung.

    Args:
        dsn: Optionaler DSN-String. Fällt zurück auf env `DATABASE_URL`.

    Raises:
        ValueError: Wenn keine DSN/`DATABASE_URL` vorhanden ist.
        psycopg2.Error: Bei Verbindungsfehlern.
    """
    db_url = dsn or os.environ.get("DATABASE_URL")

    if not db_url:
        raise ValueError(
            "DATABASE_URL nicht gefunden! "
            "Bitte setze die Umgebungsvariable oder erstelle eine .env-Datei."
        )

    try:
        conn = psycopg2.connect(db_url)
        logger.debug("Datenbankverbindung hergestellt")
        return conn
    except psycopg2.Error as exc:
        logger.error("Fehler beim Verbinden mit der Datenbank: %s", exc)
        raise


