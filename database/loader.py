"""
Database Loader - Lädt SIMAP-Daten aus Supabase in Pandas DataFrames.

Dieses Modul stellt Funktionen zur Verfügung, um Daten aus der
Supabase PostgreSQL-Datenbank zu laden und in Pandas DataFrames umzuwandeln.
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Lade .env Datei
load_dotenv()

# Logging konfigurieren
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_db_connection():
    """
    Erstellt eine Datenbankverbindung zu Supabase.

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

    try:
        conn = psycopg2.connect(db_url)
        logger.debug("✓ Datenbankverbindung hergestellt")
        return conn
    except psycopg2.Error as e:
        logger.error(f"✗ Fehler beim Verbinden: {e}")
        raise


def _execute_query(query: str, params: tuple = ()) -> pd.DataFrame:
    """
    Führt eine SQL-Query aus und gibt das Ergebnis als DataFrame zurück.

    Args:
        query: SQL-Query
        params: Parameter für die Query

    Returns:
        pd.DataFrame: Abfrageergebnis

    Raises:
        psycopg2.Error: Bei Datenbankfehlern
    """
    conn = None
    try:
        conn = get_db_connection()

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            rows = cur.fetchall()

        if not rows:
            logger.warning("Keine Daten gefunden")
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        logger.info(f"✓ {len(df)} Zeilen geladen")

        return df

    except psycopg2.Error as e:
        logger.error(f"✗ Fehler bei Datenbankabfrage: {e}")
        raise

    finally:
        if conn:
            conn.close()


def load_all_data(limit: Optional[int] = None) -> pd.DataFrame:
    """
    Lädt alle Daten aus der simap_projects Tabelle.

    Args:
        limit: Maximale Anzahl von Zeilen (None = unbegrenzt)

    Returns:
        pd.DataFrame: Alle SIMAP-Projekte

    Beispiel:
        df = load_all_data(limit=10000)
        print(df.shape)  # (10000, 45)
    """
    logger.info("Lade alle Daten...")

    query = "SELECT * FROM simap_projects ORDER BY publication_date DESC"

    if limit:
        query += f" LIMIT {limit}"

    return _execute_query(query)


def load_by_canton(canton: str, limit: Optional[int] = None) -> pd.DataFrame:
    """
    Lädt Daten für einen bestimmten Kanton.

    Args:
        canton: Kantonkürzel (z.B. 'ZH', 'BE', 'BS', 'AG')
        limit: Maximale Anzahl von Zeilen

    Returns:
        pd.DataFrame: Projekte aus dem angegebenen Kanton

    Beispiel:
        df_zh = load_by_canton('ZH')
        df_zg = load_by_canton('ZG', limit=5000)
    """
    logger.info(f"Lade Daten für Kanton: {canton}")

    query = "SELECT * FROM simap_projects WHERE canton = %s ORDER BY publication_date DESC"

    if limit:
        query += f" LIMIT {limit}"

    return _execute_query(query, (canton,))


def load_by_publication_type(pub_type: str, limit: Optional[int] = None) -> pd.DataFrame:
    """
    Lädt Daten nach Publikationstyp.

    Args:
        pub_type: Publikationstyp ('tender', 'award', 'cancellation')
        limit: Maximale Anzahl von Zeilen

    Returns:
        pd.DataFrame: Projekte des angegebenen Publikationstyps

    Beispiel:
        df_tender = load_by_publication_type('tender')
        df_awards = load_by_publication_type('award', limit=1000)
    """
    logger.info(f"Lade {pub_type} Daten...")

    query = "SELECT * FROM simap_projects WHERE publication_type = %s ORDER BY publication_date DESC"

    if limit:
        query += f" LIMIT {limit}"

    return _execute_query(query, (pub_type,))


def load_by_date_range(
    start_date: datetime,
    end_date: Optional[datetime] = None,
    limit: Optional[int] = None
) -> pd.DataFrame:
    """
    Lädt Daten innerhalb eines Datumsbereichs.

    Args:
        start_date: Startdatum
        end_date: Enddatum (None = heute)
        limit: Maximale Anzahl von Zeilen

    Returns:
        pd.DataFrame: Projekte im angegebenen Zeitraum

    Beispiel:
        # Letzte 30 Tage
        start = datetime.now() - timedelta(days=30)
        df = load_by_date_range(start)

        # Spezifischer Zeitraum
        start = datetime(2024, 1, 1)
        end = datetime(2024, 12, 31)
        df = load_by_date_range(start, end)
    """
    if end_date is None:
        end_date = datetime.now()

    logger.info(f"Lade Daten von {start_date.date()} bis {end_date.date()}...")

    query = """
    SELECT * FROM simap_projects
    WHERE publication_date >= %s AND publication_date <= %s
    ORDER BY publication_date DESC
    """

    if limit:
        query += f" LIMIT {limit}"

    return _execute_query(query, (start_date, end_date))


def load_award_data(limit: Optional[int] = None) -> pd.DataFrame:
    """
    Lädt nur Zuschlag-Daten (award_decision_date ist nicht NULL).

    Dies sind Projekte, bei denen bereits ein Auftrag vergeben wurde
    und Gewinner-Informationen vorhanden sind.

    Args:
        limit: Maximale Anzahl von Zeilen

    Returns:
        pd.DataFrame: Projekte mit Zuschlag-Informationen

    Beispiel:
        df_awards = load_award_data()
        print(df_awards[['winner_name', 'award_amount', 'award_currency']])
    """
    logger.info("Lade Award-Daten...")

    query = """
    SELECT * FROM simap_projects
    WHERE award_decision_date IS NOT NULL
    ORDER BY award_decision_date DESC
    """

    if limit:
        query += f" LIMIT {limit}"

    return _execute_query(query)


def load_with_filters(
    cantons: Optional[List[str]] = None,
    publication_types: Optional[List[str]] = None,
    process_types: Optional[List[str]] = None,
    languages: Optional[List[str]] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    limit: Optional[int] = None,
) -> pd.DataFrame:
    """
    Lädt Daten mit verschiedenen Filteroptionen.

    Diese Funktion ist das Herzstück für flexible Datenabfragen.

    Args:
        cantons: Liste von Kantonen (z.B. ['ZH', 'BE', 'BS'])
        publication_types: Liste von Publikationstypen (z.B. ['tender', 'award'])
        process_types: Liste von Prozesstypen (z.B. ['open', 'selective'])
        languages: Liste von Sprachen (z.B. ['de', 'fr'])
        min_amount: Minimale geschätzte Summe
        max_amount: Maximale geschätzte Summe
        limit: Maximale Anzahl von Zeilen

    Returns:
        pd.DataFrame: Gefilterte Daten

    Beispiel:
        # Alle offenen Ausschreibungen in den Kantonen ZH und BL
        df = load_with_filters(
            cantons=['ZH', 'BL'],
            publication_types=['tender'],
            process_types=['open'],
            limit=5000
        )

        # Awards über CHF 100'000
        df_big_awards = load_with_filters(
            publication_types=['award'],
            min_amount=100000,
            limit=1000
        )
    """
    conditions = []
    params = []

    # Kantone
    if cantons:
        placeholders = ",".join(["%s"] * len(cantons))
        conditions.append(f"canton IN ({placeholders})")
        params.extend(cantons)

    # Publikationstypen
    if publication_types:
        placeholders = ",".join(["%s"] * len(publication_types))
        conditions.append(f"publication_type IN ({placeholders})")
        params.extend(publication_types)

    # Prozesstypen
    if process_types:
        placeholders = ",".join(["%s"] * len(process_types))
        conditions.append(f"process_type IN ({placeholders})")
        params.extend(process_types)

    # Sprachen
    if languages:
        placeholders = ",".join(["%s"] * len(languages))
        conditions.append(f"creation_language IN ({placeholders})")
        params.extend(languages)

    # Betrag-Range
    if min_amount is not None:
        conditions.append("estimated_amount >= %s")
        params.append(min_amount)

    if max_amount is not None:
        conditions.append("estimated_amount <= %s")
        params.append(max_amount)

    # SQL zusammenbauen
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    query = f"""
    SELECT * FROM simap_projects
    WHERE {where_clause}
    ORDER BY publication_date DESC
    """

    if limit:
        query += f" LIMIT {limit}"

    logger.info(f"Lade Daten mit Filtern...")
    logger.debug(f"Query: {query}")

    return _execute_query(query, tuple(params))


def get_statistics() -> Dict[str, Any]:
    """
    Gibt Statistiken über die Datenbank zurück.

    Returns:
        Dictionary mit verschiedenen Statistiken

    Beispiel:
        stats = get_statistics()
        print(f"Totale Projekte: {stats['total_projects']}")
        print(f"Kantone: {stats['unique_cantons']}")
    """
    logger.info("Lade Datenbankstatistiken...")

    conn = None
    try:
        conn = get_db_connection()

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Verschiedene Statistiken abfragen
            queries = {
                'total_projects': "SELECT COUNT(*) as count FROM simap_projects",
                'unique_cantons': "SELECT COUNT(DISTINCT canton) as count FROM simap_projects",
                'unique_publication_types': "SELECT COUNT(DISTINCT publication_type) as count FROM simap_projects",
                'with_awards': "SELECT COUNT(*) as count FROM simap_projects WHERE award_decision_date IS NOT NULL",
                'total_estimated_amount': "SELECT COALESCE(SUM(estimated_amount), 0) as sum FROM simap_projects WHERE estimated_amount IS NOT NULL",
                'total_award_amount': "SELECT COALESCE(SUM(award_amount), 0) as sum FROM simap_projects WHERE award_amount IS NOT NULL",
            }

            stats = {}
            for name, query in queries.items():
                cur.execute(query)
                result = cur.fetchone()
                if 'count' in result:
                    stats[name] = result['count']
                elif 'sum' in result:
                    stats[name] = float(result['sum'])

        logger.info(f"✓ Statistiken geladen")
        return stats

    except psycopg2.Error as e:
        logger.error(f"✗ Fehler beim Laden der Statistiken: {e}")
        raise

    finally:
        if conn:
            conn.close()
