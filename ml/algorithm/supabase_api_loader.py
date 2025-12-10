"""
Alternative Supabase Loader using REST API instead of direct PostgreSQL connection
Funktioniert auch wenn PostgreSQL-Ports geblockt sind
"""

import sys
import os
import pandas as pd
import requests
from datetime import datetime, timedelta
from typing import Optional, List
from dotenv import load_dotenv

# Fix Windows Console Encoding
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

load_dotenv()


class SupabaseAPILoader:
    """Lädt Daten via Supabase REST API (kein PostgreSQL-Port nötig)"""

    def __init__(self, url: Optional[str] = None, key: Optional[str] = None):
        """
        Args:
            url: Supabase Project URL (z.B. https://xxx.supabase.co)
            key: Supabase API Key (anon/public key)
        """
        self.base_url = url or os.getenv('SUPABASE_URL')
        self.api_key = key or os.getenv('SUPABASE_KEY')

        if not self.base_url or not self.api_key:
            raise ValueError(
                "❌ SUPABASE_URL oder SUPABASE_KEY nicht gefunden!\n"
                "Bitte füge folgendes zur .env Datei hinzu:\n"
                "SUPABASE_URL=https://xxx.supabase.co\n"
                "SUPABASE_KEY=dein-anon-key"
            )

        # Entferne trailing slash
        self.base_url = self.base_url.rstrip('/')
        self.headers = {
            'apikey': self.api_key,
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
            'Prefer': 'return=representation'
        }

    def lade_projekte(self,
                     tage_zurueck: int = 10,
                     kantone: Optional[List[str]] = None,
                     projekt_typen: Optional[List[str]] = None,
                     auftrags_arten: Optional[List[str]] = None,
                     limit: int = 10000) -> pd.DataFrame:
        """
        Lädt Projekte via Supabase REST API

        Args:
            tage_zurueck: Anzahl Tage zurück
            kantone: Filter nach Kantonen
            projekt_typen: Filter nach Projekttypen
            auftrags_arten: Filter nach Auftragsarten
            limit: Max. Anzahl Projekte (default: 10000)

        Returns:
            DataFrame mit Projekten
        """
        try:
            # Berechne Start-Datum
            start_datum = (datetime.now() - timedelta(days=tage_zurueck)).strftime('%Y-%m-%d')

            # Basis-URL
            url = f"{self.base_url}/rest/v1/projects"

            # Query-Parameter
            params = {
                'select': '*',
                'publication_date': f'gte.{start_datum}',
                'order': 'publication_date.desc',
                'limit': limit
            }

            # Filter hinzufügen
            filters = []
            if kantone:
                filters.append(f"canton.in.({','.join(kantone)})")
            if projekt_typen:
                filters.append(f"project_type.in.({','.join(projekt_typen)})")
            if auftrags_arten:
                filters.append(f"order_type.in.({','.join(auftrags_arten)})")

            # Kombiniere Filter mit AND
            if filters:
                params['and'] = f"({','.join(filters)})"

            print(f"Lade Projekte aus Supabase API (letzte {tage_zurueck} Tage)...")

            # API Request
            response = requests.get(url, headers=self.headers, params=params, timeout=30)

            if response.status_code == 200:
                data = response.json()
                df = pd.DataFrame(data)
                print(f"✓ {len(df)} Projekte geladen")
                return df
            else:
                print(f"❌ API Fehler: {response.status_code}")
                print(f"   Response: {response.text}")
                return pd.DataFrame()

        except requests.exceptions.RequestException as e:
            print(f"❌ Netzwerkfehler: {e}")
            return pd.DataFrame()
        except Exception as e:
            print(f"❌ Fehler beim Laden: {e}")
            return pd.DataFrame()

    def teste_verbindung(self) -> bool:
        """Testet die API-Verbindung"""
        try:
            url = f"{self.base_url}/rest/v1/projects"
            params = {'select': 'count', 'limit': 1}

            response = requests.get(url, headers=self.headers, params=params, timeout=10)

            if response.status_code == 200:
                print("✓ API-Verbindung erfolgreich")
                return True
            else:
                print(f"❌ API-Fehler: {response.status_code}")
                return False

        except Exception as e:
            print(f"❌ Verbindungstest fehlgeschlagen: {e}")
            return False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass  # Kein cleanup nötig


# ============================================================================
# CONVENIENCE FUNKTIONEN
# ============================================================================

def lade_aus_supabase_api(tage_zurueck: int = 10) -> pd.DataFrame:
    """
    Convenience-Funktion: Lädt Projekte via API

    Args:
        tage_zurueck: Anzahl Tage zurück

    Returns:
        DataFrame mit Projekten
    """
    with SupabaseAPILoader() as loader:
        return loader.lade_projekte(tage_zurueck=tage_zurueck)


def teste_supabase_api() -> bool:
    """
    Testet Supabase API-Verbindung

    Returns:
        True bei Erfolg
    """
    with SupabaseAPILoader() as loader:
        return loader.teste_verbindung()


# ============================================================================
# MAIN (für Tests)
# ============================================================================

if __name__ == "__main__":
    print("="*70)
    print("SUPABASE API LOADER - TEST")
    print("="*70)

    # Test 1: Verbindung
    print("\n[TEST 1] API-Verbindungstest...")
    if teste_supabase_api():
        print("✓ Test 1 bestanden")
    else:
        print("❌ Test 1 fehlgeschlagen")
        print("\nBitte prüfe deine .env Datei:")
        print("  SUPABASE_URL=https://xxx.supabase.co")
        print("  SUPABASE_KEY=dein-anon-key")
        exit(1)

    # Test 2: Daten laden
    print("\n[TEST 2] Lade Projekte...")
    df = lade_aus_supabase_api(tage_zurueck=10)

    if len(df) > 0:
        print(f"✓ Test 2 bestanden - {len(df)} Projekte geladen")
        print(f"\nBeispiel-Projekt:")
        print(f"  Titel: {df.iloc[0]['title']}")
        print(f"  Kanton: {df.iloc[0].get('canton', 'N/A')}")
    else:
        print("⚠ Test 2: Keine Projekte gefunden")

    print("\n" + "="*70)
    print("TESTS ABGESCHLOSSEN")
    print("="*70)
