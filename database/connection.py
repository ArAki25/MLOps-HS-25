"""
Zentrale Verwaltung der Datenbankverbindung.

Stellt eine einheitliche `get_db_connection()` Funktion bereit, die alle
Datenbankzugriffe nutzen. Nutzt DATABASE_URL aus der Umgebung bzw. .env.
"""

import logging
import os
from typing import Optional

import psycopg2
from psycopg2 import pool
from dotenv import load_dotenv

# .env laden, falls vorhanden
load_dotenv()

logger = logging.getLogger(__name__)

# Einfacher Connection-Pool (fügt sich in bestehende API ein)
_pool: Optional[pool.SimpleConnectionPool] = None


class _PooledConnection:
    """Wrapper, der close() in putconn() übersetzt."""

    def __init__(self, conn, pool_ref: pool.SimpleConnectionPool):
        self._conn = conn
        self._pool = pool_ref

    def __getattr__(self, item):
        return getattr(self._conn, item)

    def close(self):
        # Gibt die Verbindung an den Pool zurück, statt sie zu schließen
        self._pool.putconn(self._conn)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()


def _get_pool(dsn: str) -> pool.SimpleConnectionPool:
    global _pool
    if _pool is None:
        _pool = pool.SimpleConnectionPool(
            minconn=1,
            maxconn=5,
            dsn=dsn,
        )
        logger.debug("Connection-Pool initialisiert")
    return _pool


def get_db_connection(dsn: Optional[str] = None):
    """
    Liefert eine gepoolte psycopg2-Verbindung.

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
        pool_ref = _get_pool(db_url)
        conn = pool_ref.getconn()
        logger.debug("Gepoolte Datenbankverbindung ausgeliehen")
        return _PooledConnection(conn, pool_ref)
    except psycopg2.Error as exc:
        logger.error("Fehler beim Verbinden mit der Datenbank: %s", exc)
        raise


