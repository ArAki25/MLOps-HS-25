"""
Prüft die Struktur und Inhalte der simap_projects_old Tabelle
"""
import os
import sys
import requests
from dotenv import load_dotenv

# Fix Windows Console Encoding
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

load_dotenv()

url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_KEY')

headers = {
    'apikey': key,
    'Authorization': f'Bearer {key}',
}

# Lade erste 5 Projekte OHNE Datumsfilter
api_url = f"{url}/rest/v1/projects"
params = {
    'select': '*',
    'limit': 5
}

print("Teste Supabase-Daten...")
print(f"URL: {api_url}")
print()

response = requests.get(api_url, headers=headers, params=params, timeout=10)

if response.status_code == 200:
    data = response.json()
    print(f"✓ {len(data)} Projekte gefunden")

    if data:
        print("\n" + "="*70)
        print("STRUKTUR DER TABELLE:")
        print("="*70)
        first_item = data[0]
        print(f"\nSpalten ({len(first_item.keys())}):")
        for key in sorted(first_item.keys()):
            value = first_item[key]
            if value is not None:
                value_str = str(value)[:50]
                print(f"  - {key:30} = {value_str}")
            else:
                print(f"  - {key:30} = None")

        print("\n" + "="*70)
        print("BEISPIEL-PROJEKT:")
        print("="*70)
        print(f"Titel: {first_item.get('title', 'N/A')}")
        print(f"Beschreibung: {str(first_item.get('description', 'N/A'))[:100]}...")

        # Prüfe Datumsfelder
        print("\n" + "="*70)
        print("DATUMSFELDER:")
        print("="*70)
        date_fields = [k for k in first_item.keys() if 'date' in k.lower() or 'datum' in k.lower()]
        if date_fields:
            for field in date_fields:
                print(f"  {field}: {first_item.get(field)}")
        else:
            print("  Keine Datumsfelder gefunden!")

    else:
        print("⚠ Tabelle ist leer!")
else:
    print(f"❌ Fehler: {response.status_code}")
    print(f"Response: {response.text}")
