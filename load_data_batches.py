"""
Batch-Loader: Lädt Daten in mehreren Batches aus Supabase.

Perfekt wenn du große Datenmengen in kleineren Schritten laden möchtest.
"""
from database import load_with_filters
from dotenv import load_dotenv

# .env laden
load_dotenv()

# ========================================================================
# KONFIGURATION - Hier anpassen!
# ========================================================================

# Batch-Einstellungen
BATCH_SIZE = 1000          # Wieviele Zeilen pro Batch?
NUM_BATCHES = 5            # Wieviele Batches gesamt?

# Filter (None = kein Filter)
CANTONS = None             # z.B. ['ZH', 'BE'] oder None
PUBLICATION_TYPES = None   # z.B. ['award', 'tender'] oder None
MIN_AMOUNT = None          # z.B. 100000 oder None

# Speichern?
SAVE_CSV = True
OUTPUT_DIR = "data/batches"

# ========================================================================
# MAIN
# ========================================================================


def main():
    import os
    from pathlib import Path

    print("=" * 60)
    print("BATCH-LOADER - DATEN AUS SUPABASE")
    print("=" * 60)

    # Output Dir erstellen
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

    total_rows = 0

    # Lade Batches nacheinander
    for batch_num in range(1, NUM_BATCHES + 1):
        offset = (batch_num - 1) * BATCH_SIZE

        print(f"\n{'='*60}")
        print(f"BATCH {batch_num}/{NUM_BATCHES}")
        print(f"{'='*60}")
        print(f"Lade {BATCH_SIZE} Zeilen (Offset: {offset})...")

        # Lade Batch
        df = load_with_filters(
            cantons=CANTONS,
            publication_types=PUBLICATION_TYPES,
            min_amount=MIN_AMOUNT,
            limit=BATCH_SIZE
        )

        if len(df) == 0:
            print(f"⚠️  Keine Daten gefunden für Batch {batch_num}")
            break

        print(f"✓ {len(df)} Zeilen geladen")
        total_rows += len(df)

        # Speichern
        if SAVE_CSV:
            filename = f"{OUTPUT_DIR}/batch_{batch_num:02d}.csv"
            df.to_csv(filename, index=False)
            print(f"✓ Gespeichert: {filename}")

    # Summary
    print(f"\n{'='*60}")
    print(f"FERTIG!")
    print(f"{'='*60}")
    print(f"Totale Zeilen geladen: {total_rows:,}")
    print(f"Batches: {NUM_BATCHES}")
    print(f"Batch-Größe: {BATCH_SIZE:,}")

    if SAVE_CSV:
        print(f"\n✓ CSV-Dateien in: {OUTPUT_DIR}/")
        # Zeige alle Files
        batch_files = list(Path(OUTPUT_DIR).glob("batch_*.csv"))
        for bf in sorted(batch_files):
            print(f"  - {bf.name}")


if __name__ == "__main__":
    main()
