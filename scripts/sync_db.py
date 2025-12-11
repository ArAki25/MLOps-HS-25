#!/usr/bin/env python
"""
SIMAP Database Sync Script.

Ersetzt: scripts/update_db.py, main.py

Verwendung:
    python scripts/sync_db.py              # Delta-Sync (ab letztem Datum)
    python scripts/sync_db.py --days 7     # Letzte 7 Tage
    python scripts/sync_db.py --full       # Full-Sync (30 Tage)
    python scripts/sync_db.py --dry-run    # Nur anzeigen, nicht speichern

Für GitHub Actions:
    python scripts/sync_db.py --days 2
"""
import argparse
import logging
import os
import sys

# Parent-Verzeichnis zum Path hinzufügen
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="SIMAP Database Sync",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
    # Standard Delta-Sync
    python scripts/sync_db.py
    
    # Letzte 7 Tage
    python scripts/sync_db.py --days 7
    
    # Nur Deutschschweiz
    python scripts/sync_db.py --german-cantons
    
    # Testing mit Limit
    python scripts/sync_db.py --max-pages 5 --dry-run
        """
    )
    
    parser.add_argument(
        "--days", type=int,
        help="Tage zurück (überschreibt Delta-Logik)"
    )
    parser.add_argument(
        "--full", action="store_true",
        help="Full-Sync statt Delta"
    )
    parser.add_argument(
        "--german-cantons", action="store_true",
        help="Nur deutschsprachige Kantone"
    )
    parser.add_argument(
        "--cantons", nargs="+",
        help="Spezifische Kantone (z.B. ZH BE GE)"
    )
    parser.add_argument(
        "--max-pages", type=int,
        help="Maximum Seiten (für Testing)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Nur laden, nicht in DB speichern"
    )
    
    args = parser.parse_args()
    
    # Database URL prüfen
    if not os.environ.get("DATABASE_URL"):
        logger.error("❌ DATABASE_URL nicht in .env gesetzt!")
        logger.info("Erstelle .env Datei mit:")
        logger.info('  DATABASE_URL="postgresql://user:pass@host:port/db"')
        sys.exit(1)
    
    # Kantone bestimmen
    if args.cantons:
        cantons = args.cantons
    elif args.german_cantons:
        from database_v2 import DEFAULT_CANTONS
        cantons = DEFAULT_CANTONS
        logger.info(f"Deutsche Kantone: {len(cantons)}")
    else:
        cantons = None  # Alle
    
    # Dry-Run Modus
    if args.dry_run:
        logger.info("🔍 DRY-RUN Modus - keine DB-Änderungen")
        _dry_run(
            days_back=args.days,
            cantons=cantons,
            max_pages=args.max_pages or 3,
        )
        return
    
    # Normaler Sync
    from database_v2 import sync
    
    stats = sync(
        days_back=args.days,
        cantons=cantons,
        full_sync=args.full,
        max_pages=args.max_pages,
    )
    
    # Exit-Code für GitHub Actions
    if stats.errors > 0:
        sys.exit(1)


def _dry_run(
    days_back: int | None,
    cantons: list[str] | None,
    max_pages: int,
):
    """Dry-Run: Nur laden und anzeigen."""
    from datetime import date, timedelta
    from database_v2 import SimapClient
    from database_v2.parser import parse_project_entry
    
    start_date = date.today() - timedelta(days=days_back or 7)
    
    logger.info(f"Lade Projekte ab {start_date}...")
    
    client = SimapClient()
    count = 0
    
    for entry in client.search_projects(
        publication_from=start_date.isoformat(),
        cantons=cantons,
        max_pages=max_pages,
    ):
        project = parse_project_entry(entry)
        count += 1
        
        if count <= 5:
            logger.info(f"  {project.publication_date} | {project.pub_type:10} | {project.title_str[:50]}")
    
    logger.info(f"\n✓ {count} Projekte gefunden (nicht gespeichert)")


if __name__ == "__main__":
    main()
