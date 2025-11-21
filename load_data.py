"""
Script zum Laden von Daten aus Supabase.

Verwendung:
    python load_data.py

Einfach die Einstellungen unten anpassen!
"""
from database import load_all_data, load_with_filters, load_award_data
from dotenv import load_dotenv

# .env laden
load_dotenv()

# ========================================================================
# KONFIGURATION - Hier anpassen!
# ========================================================================

# Welche Daten laden?
LOAD_TYPE = "all"  # Optionen: "all", "filtered", "awards"

# Filter (None = kein Filter)
CANTONS = None              # z.B. ['ZH', 'BE', 'BS'] oder None für alle
PUBLICATION_TYPES = None    # z.B. ['award', 'tender'] oder None
PROCESS_TYPES = None        # z.B. ['open', 'selective'] oder None
LANGUAGES = None            # z.B. ['de', 'fr'] oder None
MIN_AMOUNT = None           # z.B. 100000 oder None
MAX_AMOUNT = None           # z.B. 500000 oder None

# Limit
LIMIT = 10  # Maximale Anzahl Zeilen (None = alle)

# Speichern?
SAVE_CSV = True
OUTPUT_FILE = "data/loaded_data.csv"

# ========================================================================
# MAIN
# ========================================================================


def main():
    print("=" * 60)
    print("DATENLADUNG AUS SUPABASE")
    print("=" * 60)

    # Daten laden je nach Typ
    if LOAD_TYPE == "awards":
        print(f"\nLade Award-Daten (limit={LIMIT})...")
        df = load_award_data(limit=LIMIT)

    elif LOAD_TYPE == "filtered":
        print(f"\nLade gefilterte Daten...")
        print(f"  Kantone: {CANTONS}")
        print(f"  Publikationstypen: {PUBLICATION_TYPES}")
        print(f"  Limit: {LIMIT}")

        df = load_with_filters(
            cantons=CANTONS,
            publication_types=PUBLICATION_TYPES,
            process_types=PROCESS_TYPES,
            languages=LANGUAGES,
            min_amount=MIN_AMOUNT,
            max_amount=MAX_AMOUNT,
            limit=LIMIT
        )

    else:  # "all"
        print(f"\nLade alle Daten (limit={LIMIT})...")
        df = load_all_data(limit=LIMIT)

    # Ergebnis anzeigen
    print(f"\n✓ {len(df)} Zeilen geladen")
    print(f"✓ {len(df.columns)} Spalten")
    print(f"\nErste 5 Zeilen:")
    print(df.head())

    # Speichern
    if SAVE_CSV:
        df.to_csv(OUTPUT_FILE, index=False)
        print(f"\n✓ Gespeichert: {OUTPUT_FILE}")

    print("\n" + "=" * 60)
    print("✓ FERTIG!")
    print("=" * 60)

    return df


if __name__ == "__main__":
    df = main()
