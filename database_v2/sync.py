"""
SIMAP → Database Synchronisation.

Hauptmodul für die Datensynchronisation von SIMAP in die lokale DB.
Unterstützt Full-Sync und Delta-Sync Strategien.
"""
import logging
import time
from datetime import date, timedelta
from typing import Optional

from .client import SimapClient
from .parser import parse_project_entry
from .repository import repo
from .models import Project, SyncStats

logger = logging.getLogger(__name__)

# Standard-Kantone (Deutschschweiz)
DEFAULT_CANTONS = [
    "ZH", "BE", "LU", "UR", "SZ", "OW", "NW", "GL", "ZG",
    "SO", "BS", "BL", "SH", "AR", "AI", "SG", "GR", "AG", "TG",
]


def sync(
    days_back: Optional[int] = None,
    cantons: Optional[list[str]] = None,
    full_sync: bool = False,
    max_pages: Optional[int] = None,
) -> SyncStats:
    """
    Synchronisiert Projekte von SIMAP in die Datenbank.
    
    Strategien:
    - Delta-Sync (default): Ab letztem bekannten Datum - 1 Tag
    - Full-Sync: Ab days_back oder explizitem Startdatum
    
    Args:
        days_back: Wie viele Tage zurück (None = Delta oder 7 Tage)
        cantons: Kantone zu synchronisieren (None = DEFAULT_CANTONS)
        full_sync: Erzwinge Full-Sync statt Delta
        max_pages: Limit für Testing
        
    Returns:
        SyncStats mit Statistiken
    """
    stats = SyncStats()
    start_time = time.time()
    
    # Start-Datum bestimmen
    start_date = _determine_start_date(days_back, full_sync)
    cantons = cantons or DEFAULT_CANTONS
    
    logger.info("=" * 60)
    logger.info(f"SIMAP Sync gestartet")
    logger.info(f"  Start-Datum: {start_date}")
    logger.info(f"  Kantone: {len(cantons)} ({', '.join(cantons[:5])}...)")
    logger.info(f"  Modus: {'Full-Sync' if full_sync else 'Delta-Sync'}")
    logger.info("=" * 60)
    
    client = SimapClient()
    projects: list[Project] = []
    
    try:
        # Projekte von API laden
        for entry in client.search_projects(
            publication_from=start_date.isoformat(),
            cantons=cantons,
            max_pages=max_pages,
        ):
            try:
                project = parse_project_entry(entry)
                projects.append(project)
                stats.fetched += 1
                
                if stats.fetched % 100 == 0:
                    logger.info(f"  ... {stats.fetched} Projekte geladen")
                    
            except Exception as e:
                logger.warning(f"Parse-Fehler: {e}")
                stats.errors += 1
        
        if not projects:
            logger.warning("Keine neuen Projekte gefunden")
            stats.duration_seconds = time.time() - start_time
            return stats
        
        # In DB speichern
        logger.info(f"Speichere {len(projects)} Projekte in DB...")
        inserted, updated = repo.upsert_batch(projects)
        stats.inserted = inserted
        stats.updated = updated
        
    except Exception as e:
        logger.error(f"Sync-Fehler: {e}")
        stats.errors += 1
    
    stats.duration_seconds = time.time() - start_time
    
    logger.info("=" * 60)
    logger.info(f"✓ Sync abgeschlossen")
    logger.info(f"  Geladen: {stats.fetched}")
    logger.info(f"  Gespeichert: {stats.inserted}")
    logger.info(f"  Fehler: {stats.errors}")
    logger.info(f"  Dauer: {stats.duration_seconds:.1f}s")
    logger.info("=" * 60)
    
    return stats


def _determine_start_date(
    days_back: Optional[int],
    full_sync: bool,
) -> date:
    """Bestimmt das Start-Datum für den Sync."""
    
    if days_back is not None:
        # Explizit angegeben
        return date.today() - timedelta(days=days_back)
    
    if full_sync:
        # Full-Sync: Standard 30 Tage
        return date.today() - timedelta(days=30)
    
    # Delta-Sync: Letztes Datum aus DB
    last_date = repo.get_last_publication_date()
    
    if last_date:
        # Ab letztem Datum minus 1 Tag (Sicherheitspuffer)
        return last_date - timedelta(days=1)
    
    # Keine Daten in DB: 7 Tage zurück
    return date.today() - timedelta(days=7)


def sync_awards(days_back: int = 365) -> SyncStats:
    """
    Spezieller Sync nur für Awards (für ML-Training).
    
    Awards enthalten historische Zuschlagsdaten:
    - winner_name, winner_city
    - award_amount, award_currency
    - number_of_submissions
    
    Diese Daten sind wertvoll für Win-Probability Analysen.
    """
    logger.info("Starte Award-Sync für ML-Training...")
    
    # Hier müssten wir den projectSubTypes Filter nutzen
    # Die API unterstützt das via newestPubTypes Parameter
    
    # Für jetzt: Normaler Sync, dann im Repo filtern
    stats = sync(days_back=days_back, full_sync=True)
    
    return stats


# Convenience für CLI
if __name__ == "__main__":
    import argparse
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    
    parser = argparse.ArgumentParser(description="SIMAP Sync")
    parser.add_argument("--days", type=int, help="Tage zurück")
    parser.add_argument("--full", action="store_true", help="Full-Sync")
    parser.add_argument("--max-pages", type=int, help="Max Seiten (Testing)")
    args = parser.parse_args()
    
    if not os.environ.get("DATABASE_URL"):
        print("❌ DATABASE_URL nicht gesetzt!")
        exit(1)
    
    stats = sync(
        days_back=args.days,
        full_sync=args.full,
        max_pages=args.max_pages,
    )
    
    print(f"\n✓ {stats.fetched} Projekte synchronisiert")
