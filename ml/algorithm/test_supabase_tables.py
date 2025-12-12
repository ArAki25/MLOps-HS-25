"""
Test welche Tabellen in Supabase verfügbar sind
"""
import os
import sys
from dotenv import load_dotenv
from supabase import create_client, Client

# Fix encoding
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

load_dotenv()

url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_KEY')

print(f"URL: {url}")
print(f"Key: {key[:20]}...")

try:
    # Erstelle Supabase Client
    supabase: Client = create_client(url, key)
    print("\nSupabase Client erstellt")

    # Versuche verschiedene Tabellennamen
    table_names = ['projects', 'project', 'simap_projects', 'tenders', 'ausschreibungen', 'simap']

    print("\nTeste verschiedene Tabellennamen...")
    found = False
    for table in table_names:
        try:
            print(f"\n  Teste '{table}'...")
            response = supabase.table(table).select("*").limit(1).execute()
            print(f"    OK - Tabelle '{table}' gefunden!")
            print(f"    Anzahl Spalten: {len(response.data[0].keys()) if response.data else 0}")
            if response.data:
                print(f"    Spalten: {', '.join(list(response.data[0].keys())[:10])}...")
            found = True
            break
        except Exception as e:
            error_msg = str(e)[:80]
            print(f"    Fehler: {error_msg}")

    if not found:
        print("\nKeine der Test-Tabellen gefunden!")
        print("Bitte gib den korrekten Tabellennamen an.")

except Exception as e:
    print(f"\nFehler: {e}")
