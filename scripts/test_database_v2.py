#!/usr/bin/env python
"""
Test-Skript für database_v2 Modul.

Testet:
- Connection Pool
- Repository-Operationen
- Sync-Funktionalität
- Filter und Abfragen
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from database_v2 import (
    init_pool, close_pool, repo, ProjectFilter, sync,
    SimapClient, parse_project_entry
)
from datetime import date, timedelta

def test_connection():
    """Test 1: Datenbankverbindung"""
    print("=" * 60)
    print("TEST 1: Datenbankverbindung")
    print("=" * 60)
    
    if not os.environ.get("DATABASE_URL"):
        print("❌ DATABASE_URL nicht gesetzt!")
        return False
    
    try:
        init_pool(os.environ["DATABASE_URL"])
        print("✓ Connection Pool initialisiert")
        
        # Test Query
        stats = repo.stats()
        print(f"✓ Verbindung erfolgreich!")
        print(f"  Projekte in DB: {stats.get('total', 0)}")
        return True
    except Exception as e:
        print(f"❌ Fehler: {e}")
        return False
    finally:
        close_pool()


def test_repository():
    """Test 2: Repository-Operationen"""
    print("\n" + "=" * 60)
    print("TEST 2: Repository-Operationen")
    print("=" * 60)
    
    init_pool(os.environ["DATABASE_URL"])
    
    try:
        # Test: Stats
        stats = repo.stats()
        print(f"✓ Stats: {stats}")
        
        # Test: Count
        total = repo.count()
        print(f"✓ Total Count: {total}")
        
        # Test: Find mit Filter
        filters = ProjectFilter(
            cantons=["ZH"],
            limit=5
        )
        projects = repo.find(filters)
        print(f"✓ Find (ZH, limit=5): {len(projects)} Projekte gefunden")
        
        if projects:
            print(f"  Beispiel: {projects[0].get('title_de', 'N/A')[:50]}...")
        
        # Test: Last Publication Date
        last_date = repo.get_last_publication_date()
        print(f"✓ Letztes Publication Date: {last_date}")
        
        return True
    except Exception as e:
        print(f"❌ Fehler: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        close_pool()


def test_client():
    """Test 3: SIMAP API Client"""
    print("\n" + "=" * 60)
    print("TEST 3: SIMAP API Client")
    print("=" * 60)
    
    try:
        client = SimapClient()
        print("✓ Client erstellt")
        
        # Test: Search (nur 1 Seite)
        start_date = (date.today() - timedelta(days=7)).isoformat()
        count = 0
        
        for entry in client.search_projects(
            publication_from=start_date,
            cantons=["ZH"],
            max_pages=1,
        ):
            count += 1
            if count <= 3:
                project = parse_project_entry(entry)
                print(f"  {project.publication_date} | {project.pub_type:10} | {project.title_str[:50]}")
        
        print(f"✓ {count} Projekte von API geladen (1 Seite)")
        return True
    except Exception as e:
        print(f"❌ Fehler: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_sync_dry_run():
    """Test 4: Sync (Dry-Run)"""
    print("\n" + "=" * 60)
    print("TEST 4: Sync (Dry-Run - nur 1 Seite)")
    print("=" * 60)
    
    init_pool(os.environ["DATABASE_URL"])
    
    try:
        stats = sync(
            days_back=7,
            cantons=["ZH"],
            max_pages=1,  # Nur 1 Seite für Test
        )
        
        print(f"✓ Sync abgeschlossen:")
        print(f"  Geladen: {stats.fetched}")
        print(f"  Eingefügt: {stats.inserted}")
        print(f"  Fehler: {stats.errors}")
        print(f"  Dauer: {stats.duration_seconds:.1f}s")
        
        return stats.errors == 0
    except Exception as e:
        print(f"❌ Fehler: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        close_pool()


def main():
    print("=" * 60)
    print("DATABASE_V2 TESTS")
    print("=" * 60)
    
    results = []
    
    # Test 1: Connection
    results.append(("Connection", test_connection()))
    
    # Test 2: Repository
    if results[0][1]:  # Nur wenn Connection funktioniert
        results.append(("Repository", test_repository()))
    
    # Test 3: Client (keine DB nötig)
    results.append(("API Client", test_client()))
    
    # Test 4: Sync
    if results[0][1]:  # Nur wenn Connection funktioniert
        results.append(("Sync", test_sync_dry_run()))
    
    # Zusammenfassung
    print("\n" + "=" * 60)
    print("ZUSAMMENFASSUNG")
    print("=" * 60)
    
    for name, success in results:
        status = "✓ PASS" if success else "❌ FAIL"
        print(f"{status} - {name}")
    
    all_passed = all(r[1] for r in results)
    
    if all_passed:
        print("\n✓ Alle Tests bestanden!")
        return 0
    else:
        print("\n⚠ Einige Tests fehlgeschlagen!")
        return 1
