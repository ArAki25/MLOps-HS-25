#!/usr/bin/env python
"""
Script zum Laden von Daten aus Supabase.

Verwendung:
    python scripts/load_data.py
    python scripts/load_data.py --type filtered --cantons ZH BE --limit 100

Einfach die Einstellungen unten anpassen oder CLI-Argumente verwenden!
"""
import argparse
import os
import sys

# Füge Parent-Verzeichnis zum Path hinzu
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

from database import load_all_data, load_with_filters, load_award_data

# .env laden
load_dotenv()


def main():
    parser = argparse.ArgumentParser(description="SIMAP Daten aus Supabase laden")
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
        "--languages", nargs="+", help="Sprachen (z.B. de fr)"
    )
    parser.add_argument(
        "--min-amount", type=float, help="Minimaler Betrag"
    )
    parser.add_argument(
        "--max-amount", type=float, help="Maximaler Betrag"
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

    print("=" * 60)
    print("DATENLADUNG AUS SUPABASE")
    print("=" * 60)

    # Daten laden je nach Typ
    if args.type == "awards":
        print(f"\nLade Award-Daten (limit={args.limit})...")
        df = load_award_data(limit=args.limit)

    elif args.type == "filtered":
        print(f"\nLade gefilterte Daten...")
        print(f"  Kantone: {args.cantons}")
        print(f"  Publikationstypen: {args.pub_types}")
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


if __name__ == "__main__":
    df = main()

