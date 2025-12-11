#!/usr/bin/env python
"""
Script zum Laden von Daten aus Supabase (database_v2).

Verwendung:
    python scripts/load_data.py
    python scripts/load_data.py --type filtered --cantons ZH BE --limit 100
    python scripts/load_data.py --type awards --limit 50
"""
import argparse
import os
import sys

# Füge Parent-Verzeichnis zum Path hinzu
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from dotenv import load_dotenv

from database_v2 import repo, ProjectFilter, init_pool, close_pool, get_connection
from psycopg2.extras import RealDictCursor

# .env laden
load_dotenv()


def load_all_data(limit: int = None) -> pd.DataFrame:
    """Lädt alle Projekte aus der Datenbank."""
    filters = ProjectFilter(limit=limit or 1000)
    projects = repo.find(filters)
    return pd.DataFrame(projects)


def load_with_filters(
    cantons: list[str] = None,
    publication_types: list[str] = None,
    process_types: list[str] = None,
    languages: list[str] = None,  # Wird ignoriert - Spalten sind bereits mehrsprachig
    min_amount: float = None,
    max_amount: float = None,
    limit: int = None,
) -> pd.DataFrame:
    """Lädt Projekte mit Filtern."""
    filters = ProjectFilter(
        cantons=cantons,
        pub_types=publication_types,
        process_types=process_types,
        limit=limit or 1000,
    )
    projects = repo.find(filters)
    df = pd.DataFrame(projects)
    
    # Betrag-Filter (nur bei Awards möglich)
    if min_amount is not None or max_amount is not None:
        # Für Betrag-Filter müssen wir Award-Daten laden
        df_awards = load_award_data(limit=limit)
        if not df_awards.empty:
            if min_amount is not None:
                df_awards = df_awards[df_awards['award_amount'] >= min_amount]
            if max_amount is not None:
                df_awards = df_awards[df_awards['award_amount'] <= max_amount]
            return df_awards
        return pd.DataFrame()
    
    return df


def load_award_data(limit: int = None) -> pd.DataFrame:
    """Lädt Award-Daten mit allen Award-Feldern."""
    # Erweiterte Query für Awards mit allen Feldern
    sql = """
        SELECT 
            id, simap_project_id, simap_publication_id,
            project_number, publication_number,
            title_de, title_fr, title_it,
            publication_date, pub_type, project_type,
            process_type, order_type, canton, city,
            submission_deadline, lots_count,
            -- Award-spezifische Felder
            winner_name, winner_city, winner_canton,
            award_amount, award_currency, award_vat_type,
            number_of_submissions, award_decision_date,
            cpv_codes, bkp_codes,
            created_at, updated_at
        FROM projects
        WHERE pub_type = 'award'
        ORDER BY publication_date DESC
        LIMIT %s
    """
    
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, (limit or 1000,))
            rows = cur.fetchall()
            return pd.DataFrame([dict(row) for row in rows])


def main():
    parser = argparse.ArgumentParser(description="SIMAP Daten aus Supabase laden (database_v2)")
    parser.add_argument(
        "--type", choices=["all", "filtered", "awards"], default="all",
        help="Welche Daten laden? (default: all)"
    )
    parser.add_argument(
        "--cantons", nargs="+", help="Kantone zum Filtern (z.B. ZH BE BS)"
    )
    parser.add_argument(
        "--pub-types", nargs="+", help="Publikationstypen (z.B. tender award)"
    )
    parser.add_argument(
        "--process-types", nargs="+", help="Prozesstypen (z.B. open selective)"
    )
    parser.add_argument(
        "--languages", nargs="+", help="Sprachen (z.B. de fr) - wird ignoriert"
    )
    parser.add_argument(
        "--min-amount", type=float, help="Minimaler Betrag (nur bei Awards)"
    )
    parser.add_argument(
        "--max-amount", type=float, help="Maximaler Betrag (nur bei Awards)"
    )
    parser.add_argument(
        "--limit", type=int, help="Maximale Anzahl Zeilen"
    )
    parser.add_argument(
        "--output", "-o", default="data/loaded_data.csv",
        help="Output-Datei (default: data/loaded_data.csv)"
    )
    parser.add_argument(
        "--no-save", action="store_true", help="Nicht als CSV speichern"
    )
    
    args = parser.parse_args()
    
    # Database Pool initialisieren
    if not os.environ.get("DATABASE_URL"):
        print("❌ DATABASE_URL nicht in .env gesetzt!")
        sys.exit(1)
    
    init_pool(os.environ["DATABASE_URL"])

    try:
        print("=" * 60)
        print("DATENLADUNG AUS SUPABASE (database_v2)")
        print("=" * 60)

        # Daten laden je nach Typ
        if args.type == "awards":
            print(f"\nLade Award-Daten (limit={args.limit})...")
            df = load_award_data(limit=args.limit)

        elif args.type == "filtered":
            print(f"\nLade gefilterte Daten...")
            print(f"  Kantone: {args.cantons}")
            print(f"  Publikationstypen: {args.pub_types}")
            print(f"  Prozesstypen: {args.process_types}")
            print(f"  Limit: {args.limit}")

            df = load_with_filters(
                cantons=args.cantons,
                publication_types=args.pub_types,
                process_types=args.process_types,
                languages=args.languages,
                min_amount=args.min_amount,
                max_amount=args.max_amount,
                limit=args.limit
            )

        else:  # "all"
            print(f"\nLade alle Daten (limit={args.limit})...")
            df = load_all_data(limit=args.limit)

        # Ergebnis anzeigen
        if df.empty:
            print("\n⚠ Keine Daten gefunden!")
        else:
            print(f"\n✓ {len(df)} Zeilen geladen")
            print(f"✓ {len(df.columns)} Spalten")
            print(f"\nErste 5 Zeilen:")
            print(df.head())

            # Speichern
            if not args.no_save:
                # Sicherstellen dass data/ existiert
                os.makedirs(os.path.dirname(args.output), exist_ok=True)
                df.to_csv(args.output, index=False)
                print(f"\n✓ Gespeichert: {args.output}")

        print("\n" + "=" * 60)
        print("✓ FERTIG!")
        print("=" * 60)

        return df
    
    finally:
        close_pool()


if __name__ == "__main__":
    df = main()

