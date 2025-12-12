"""
Lädt SIMAP CSV-Daten in die Supabase-Tabelle simap_projects_old
"""
import os
import sys
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client, Client

# Fix Windows Console Encoding
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

load_dotenv()

def upload_csv_to_supabase(csv_path: str, table_name: str = 'projects'):
    """
    Lädt CSV-Daten in Supabase hoch

    Args:
        csv_path: Pfad zur CSV-Datei
        table_name: Name der Supabase-Tabelle
    """
    print("="*70)
    print("CSV-DATEN IN SUPABASE HOCHLADEN")
    print("="*70)

    # 1. Lade CSV
    print(f"\n[1] Lade CSV-Datei: {csv_path}")
    df = pd.read_csv(csv_path)
    print(f"    ✓ {len(df)} Zeilen geladen")
    print(f"    ✓ {len(df.columns)} Spalten: {list(df.columns)[:5]}...")

    # 2. Verbinde mit Supabase
    print(f"\n[2] Verbinde mit Supabase...")
    url = os.getenv('SUPABASE_URL')
    key = os.getenv('SUPABASE_KEY')

    if not url or not key:
        print("    ❌ SUPABASE_URL oder SUPABASE_KEY fehlt in .env!")
        return

    supabase: Client = create_client(url, key)
    print(f"    ✓ Verbindung hergestellt")

    # 3. Konvertiere Spaltennamen (CSV -> Supabase)
    print(f"\n[3] Passe Spaltennamen an...")
    column_mapping = {
        'pub_type': 'publication_type',
        'cpv': 'cpv_code',
        'estimated_value': 'estimated_amount',
        'proc_office_name': 'procurement_office'
    }

    df_renamed = df.rename(columns=column_mapping)
    print(f"    ✓ Spaltennamen angepasst")

    # 4. Konvertiere zu Liste von Dictionaries
    print(f"\n[4] Bereite Daten für Upload vor...")
    records = df_renamed.to_dict('records')
    print(f"    ✓ {len(records)} Datensätze vorbereitet")

    # 5. Upload in Batches (Supabase hat Limits)
    print(f"\n[5] Lade Daten hoch...")
    batch_size = 100
    total_uploaded = 0

    for i in range(0, len(records), batch_size):
        batch = records[i:i+batch_size]
        try:
            response = supabase.table(table_name).insert(batch).execute()
            total_uploaded += len(batch)
            print(f"    ✓ Batch {i//batch_size + 1}: {len(batch)} Datensätze hochgeladen")
        except Exception as e:
            print(f"    ❌ Fehler bei Batch {i//batch_size + 1}: {e}")

            # Versuche einzeln hochzuladen
            print(f"       Versuche Einzelupload...")
            for j, record in enumerate(batch):
                try:
                    supabase.table(table_name).insert(record).execute()
                    total_uploaded += 1
                except Exception as e2:
                    print(f"       ❌ Datensatz {i+j+1} fehlgeschlagen: {str(e2)[:80]}")

    # 6. Prüfe Ergebnis
    print(f"\n[6] Prüfe hochgeladene Daten...")
    try:
        response = supabase.table(table_name).select("*", count='exact').limit(1).execute()
        count = response.count if hasattr(response, 'count') else 'unbekannt'
        print(f"    ✓ Tabelle hat jetzt {count} Einträge")
    except Exception as e:
        print(f"    ⚠ Konnte Anzahl nicht prüfen: {e}")

    print("\n" + "="*70)
    print(f"✓ UPLOAD ABGESCHLOSSEN!")
    print("="*70)
    print(f"\nHochgeladen: {total_uploaded}/{len(records)} Datensätze")
    print(f"\nJetzt kannst du das Modell trainieren:")
    print(f"  python ml/classifier.py")

if __name__ == "__main__":
    csv_file = "Simap/simap_projects.csv"

    if not os.path.exists(csv_file):
        print(f"❌ CSV-Datei nicht gefunden: {csv_file}")
        sys.exit(1)

    upload_csv_to_supabase(csv_file)
