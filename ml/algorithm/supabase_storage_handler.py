"""
Supabase Storage Handler für ML-Modelle
Ermöglicht Upload/Download von .pkl Modellen zu/von Supabase Storage
"""

import os
import sys
import requests
import joblib
from typing import Optional, Any
from pathlib import Path
from dotenv import load_dotenv

# Fix Windows Console Encoding
if sys.platform == 'win32':
    import codecs
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

load_dotenv()


class SupabaseStorageHandler:
    """Handler für Supabase Storage - Upload/Download von ML-Modellen"""

    def __init__(self, url: Optional[str] = None, key: Optional[str] = None, bucket_name: str = "models"):
        """
        Args:
            url: Supabase Project URL (z.B. https://xxx.supabase.co)
            key: Supabase Service Role Key (für private buckets) oder anon key
            bucket_name: Name des Storage Buckets (default: "models")
        """
        self.base_url = url or os.getenv('SUPABASE_URL')
        # Für private buckets brauchst du den SERVICE_ROLE_KEY
        self.api_key = key or os.getenv('SUPABASE_SERVICE_KEY') or os.getenv('SUPABASE_KEY')
        self.bucket_name = bucket_name

        if not self.base_url or not self.api_key:
            raise ValueError(
                "❌ SUPABASE_URL oder SUPABASE_SERVICE_KEY nicht gefunden!\n"
                "Für private Storage buckets brauchst du:\n"
                "SUPABASE_URL=https://xxx.supabase.co\n"
                "SUPABASE_SERVICE_KEY=dein-service-role-key\n\n"
                "Den Service Role Key findest du unter: Settings → API → service_role"
            )

        self.base_url = self.base_url.rstrip('/')
        self.storage_url = f"{self.base_url}/storage/v1"

        self.headers = {
            'apikey': self.api_key,
            'Authorization': f'Bearer {self.api_key}',
        }

    def upload_modell(self, lokaler_pfad: str, remote_pfad: str) -> bool:
        """
        Lädt ein lokales Modell (.pkl) zu Supabase Storage hoch

        Args:
            lokaler_pfad: Pfad zur lokalen .pkl Datei
            remote_pfad: Pfad im Bucket (z.B. "v1/mein_modell.pkl")

        Returns:
            True bei Erfolg
        """
        try:
            if not os.path.exists(lokaler_pfad):
                print(f"❌ Datei nicht gefunden: {lokaler_pfad}")
                return False

            # Lese Datei
            with open(lokaler_pfad, 'rb') as f:
                file_data = f.read()

            # Upload URL
            url = f"{self.storage_url}/object/{self.bucket_name}/{remote_pfad}"

            # Content-Type für .pkl Dateien
            upload_headers = self.headers.copy()
            upload_headers['Content-Type'] = 'application/octet-stream'

            print(f"📤 Uploading {lokaler_pfad} → {self.bucket_name}/{remote_pfad}...")

            # Versuche zuerst POST (neue Datei)
            response = requests.post(url, headers=upload_headers, data=file_data, timeout=60)

            # Falls Datei existiert (409), verwende PUT zum Überschreiben
            if response.status_code == 409 or (response.status_code == 400 and "already exists" in response.text.lower()):
                print("  Datei existiert bereits - überschreibe...")
                response = requests.put(url, headers=upload_headers, data=file_data, timeout=60)

            if response.status_code in [200, 201]:
                print("✓ Upload erfolgreich!")
                return True
            else:
                print(f"❌ Upload fehlgeschlagen: {response.status_code}")
                print(f"   Response: {response.text}")
                return False

        except Exception as e:
            print(f"❌ Fehler beim Upload: {e}")
            return False

    def download_modell(self, remote_pfad: str, lokaler_pfad: Optional[str] = None) -> Optional[str]:
        """
        Lädt ein Modell von Supabase Storage herunter

        Args:
            remote_pfad: Pfad im Bucket (z.B. "v1/mein_modell.pkl")
            lokaler_pfad: Optionaler lokaler Pfad. Falls None, wird temp Datei erstellt

        Returns:
            Pfad zur heruntergeladenen Datei oder None bei Fehler
        """
        try:
            # Download URL
            url = f"{self.storage_url}/object/{self.bucket_name}/{remote_pfad}"

            print(f"📥 Downloading {self.bucket_name}/{remote_pfad}...")

            response = requests.get(url, headers=self.headers, timeout=60)

            if response.status_code == 200:
                # Falls kein lokaler Pfad angegeben, erstelle temp Datei
                if lokaler_pfad is None:
                    import tempfile
                    temp_dir = tempfile.gettempdir()
                    filename = Path(remote_pfad).name
                    lokaler_pfad = os.path.join(temp_dir, filename)

                # Erstelle Verzeichnis falls nötig
                os.makedirs(os.path.dirname(lokaler_pfad) or '.', exist_ok=True)

                # Speichere Datei
                with open(lokaler_pfad, 'wb') as f:
                    f.write(response.content)

                print(f"✓ Download erfolgreich: {lokaler_pfad}")
                return lokaler_pfad
            else:
                print(f"❌ Download fehlgeschlagen: {response.status_code}")
                print(f"   Response: {response.text}")
                return None

        except Exception as e:
            print(f"❌ Fehler beim Download: {e}")
            return None

    def lade_modell_direkt(self, remote_pfad: str) -> Optional[Any]:
        """
        Lädt ein Modell direkt in den Speicher (ohne lokale Datei)

        Args:
            remote_pfad: Pfad im Bucket (z.B. "v1/mein_modell.pkl")

        Returns:
            Geladenes Modell oder None bei Fehler
        """
        try:
            # Download URL
            url = f"{self.storage_url}/object/{self.bucket_name}/{remote_pfad}"

            print(f"📥 Lade Modell {self.bucket_name}/{remote_pfad}...")

            response = requests.get(url, headers=self.headers, timeout=60)

            if response.status_code == 200:
                # Lade direkt aus Bytes mit joblib
                import io
                model = joblib.load(io.BytesIO(response.content))
                print(f"✓ Modell erfolgreich geladen")
                return model
            else:
                print(f"❌ Download fehlgeschlagen: {response.status_code}")
                print(f"   Response: {response.text}")
                return None

        except Exception as e:
            print(f"❌ Fehler beim Laden: {e}")
            return None

    def speichere_modell_direkt(self, model: Any, remote_pfad: str) -> bool:
        """
        Speichert ein Modell direkt ohne lokale Datei

        Args:
            model: Das zu speichernde Modell (joblib-kompatibel)
            remote_pfad: Pfad im Bucket (z.B. "v1/mein_modell.pkl")

        Returns:
            True bei Erfolg
        """
        try:
            import io

            # Serialisiere Modell in Memory
            buffer = io.BytesIO()
            joblib.dump(model, buffer)
            buffer.seek(0)

            # Upload URL
            url = f"{self.storage_url}/object/{self.bucket_name}/{remote_pfad}"

            upload_headers = self.headers.copy()
            upload_headers['Content-Type'] = 'application/octet-stream'

            print(f"📤 Speichere Modell → {self.bucket_name}/{remote_pfad}...")

            # Versuche zuerst POST (neue Datei)
            response = requests.post(url, headers=upload_headers, data=buffer.getvalue(), timeout=60)

            # Falls Datei existiert (409), verwende PUT zum Überschreiben
            if response.status_code == 409 or (response.status_code == 400 and "already exists" in response.text.lower()):
                print("  Datei existiert bereits - überschreibe...")
                response = requests.put(url, headers=upload_headers, data=buffer.getvalue(), timeout=60)

            if response.status_code in [200, 201]:
                print("✓ Modell erfolgreich gespeichert!")
                return True
            else:
                print(f"❌ Speichern fehlgeschlagen: {response.status_code}")
                print(f"   Response: {response.text}")
                return False

        except Exception as e:
            print(f"❌ Fehler beim Speichern: {e}")
            return False

    def liste_modelle(self, pfad_prefix: str = "") -> list:
        """
        Listet alle Dateien im Bucket auf

        Args:
            pfad_prefix: Optionaler Prefix-Filter (z.B. "v1/")

        Returns:
            Liste von Dateinamen
        """
        try:
            url = f"{self.storage_url}/object/list/{self.bucket_name}"

            payload = {
                "prefix": pfad_prefix,
                "limit": 100,
                "offset": 0
            }

            response = requests.post(url, headers=self.headers, json=payload, timeout=30)

            if response.status_code == 200:
                files = response.json()
                return [f['name'] for f in files if 'name' in f]
            else:
                print(f"❌ Fehler beim Auflisten: {response.status_code}")
                return []

        except Exception as e:
            print(f"❌ Fehler beim Auflisten: {e}")
            return []

    def erstelle_bucket(self) -> bool:
        """
        Erstellt den Bucket falls er nicht existiert

        Returns:
            True bei Erfolg
        """
        try:
            url = f"{self.storage_url}/bucket"

            payload = {
                "name": self.bucket_name,
                "public": False,  # Private bucket für Modelle
                "file_size_limit": 52428800,  # 50 MB
                "allowed_mime_types": ["application/octet-stream"]
            }

            response = requests.post(url, headers=self.headers, json=payload, timeout=30)

            if response.status_code in [200, 201]:
                print(f"✓ Bucket '{self.bucket_name}' erstellt")
                return True
            elif response.status_code == 409:
                print(f"ℹ Bucket '{self.bucket_name}' existiert bereits")
                return True
            else:
                print(f"❌ Fehler beim Erstellen: {response.status_code}")
                print(f"   Response: {response.text}")
                return False

        except Exception as e:
            print(f"❌ Fehler: {e}")
            return False


# ============================================================================
# CONVENIENCE FUNKTIONEN
# ============================================================================

def lade_modell_von_storage(remote_pfad: str, bucket: str = "models") -> Optional[Any]:
    """
    Convenience-Funktion: Lädt Modell direkt von Supabase Storage

    Args:
        remote_pfad: Pfad im Bucket (z.B. "production/classifier_v1.pkl")
        bucket: Bucket-Name

    Returns:
        Geladenes Modell
    """
    handler = SupabaseStorageHandler(bucket_name=bucket)
    return handler.lade_modell_direkt(remote_pfad)


def speichere_modell_zu_storage(model: Any, remote_pfad: str, bucket: str = "models") -> bool:
    """
    Convenience-Funktion: Speichert Modell zu Supabase Storage

    Args:
        model: Das Modell
        remote_pfad: Pfad im Bucket
        bucket: Bucket-Name

    Returns:
        True bei Erfolg
    """
    handler = SupabaseStorageHandler(bucket_name=bucket)
    return handler.speichere_modell_direkt(model, remote_pfad)


# ============================================================================
# MAIN (für Tests)
# ============================================================================

if __name__ == "__main__":
    print("="*70)
    print("SUPABASE STORAGE HANDLER - TEST")
    print("="*70)

    # Test Setup
    handler = SupabaseStorageHandler(bucket_name="models")

    # Test 1: Bucket erstellen
    print("\n[TEST 1] Bucket erstellen/prüfen...")
    if handler.erstelle_bucket():
        print("✓ Test 1 bestanden")
    else:
        print("❌ Test 1 fehlgeschlagen")
        exit(1)

    # Test 2: Modelle auflisten
    print("\n[TEST 2] Modelle auflisten...")
    models = handler.liste_modelle()
    print(f"✓ {len(models)} Dateien gefunden")
    if models:
        print(f"   Erste Datei: {models[0]}")

    # Test 3: Test-Modell erstellen und hochladen
    print("\n[TEST 3] Test-Modell hochladen...")
    test_model = {"test": "data", "version": "1.0"}
    test_remote_path = "test/test_model.pkl"

    if handler.speichere_modell_direkt(test_model, test_remote_path):
        print("✓ Upload erfolgreich")

        # Test 4: Modell wieder herunterladen
        print("\n[TEST 4] Test-Modell herunterladen...")
        loaded_model = handler.lade_modell_direkt(test_remote_path)

        if loaded_model and loaded_model == test_model:
            print("✓ Download erfolgreich - Daten stimmen überein!")
        else:
            print("❌ Download fehlgeschlagen oder Daten unterschiedlich")
    else:
        print("❌ Upload fehlgeschlagen")

    print("\n" + "="*70)
    print("TESTS ABGESCHLOSSEN")
    print("="*70)
