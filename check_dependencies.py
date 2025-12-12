"""
Dependency Checker - Prüft alle Abhängigkeiten und Integration
"""

import sys
import os

print("="*70)
print("DEPENDENCY CHECK - MLOps Projekt")
print("="*70)

# ============================================================================
# 1. PYTHON VERSION
# ============================================================================
print("\n[1] PYTHON VERSION")
print("-"*70)
print(f"Python: {sys.version}")
print(f"Version: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")

if sys.version_info.major < 3 or sys.version_info.minor < 8:
    print("WARNUNG: Python 3.8+ empfohlen")
else:
    print("OK: Python Version kompatibel")

# ============================================================================
# 2. CORE DEPENDENCIES
# ============================================================================
print("\n[2] CORE DEPENDENCIES")
print("-"*70)

dependencies = {}

try:
    import pandas
    dependencies['pandas'] = pandas.__version__
    print(f"OK: pandas {pandas.__version__}")
except ImportError as e:
    print(f"FEHLT: pandas - {e}")
    dependencies['pandas'] = None

try:
    import numpy
    dependencies['numpy'] = numpy.__version__
    print(f"OK: numpy {numpy.__version__}")
except ImportError as e:
    print(f"FEHLT: numpy - {e}")
    dependencies['numpy'] = None

try:
    import sklearn
    dependencies['scikit-learn'] = sklearn.__version__
    print(f"OK: scikit-learn {sklearn.__version__}")
except ImportError as e:
    print(f"FEHLT: scikit-learn - {e}")
    dependencies['scikit-learn'] = None

try:
    import sentence_transformers
    dependencies['sentence-transformers'] = sentence_transformers.__version__
    print(f"OK: sentence-transformers {sentence_transformers.__version__}")
except ImportError as e:
    print(f"FEHLT: sentence-transformers - {e}")
    dependencies['sentence-transformers'] = None

try:
    import joblib
    dependencies['joblib'] = joblib.__version__
    print(f"OK: joblib {joblib.__version__}")
except ImportError as e:
    print(f"FEHLT: joblib - {e}")
    dependencies['joblib'] = None

try:
    import requests
    dependencies['requests'] = requests.__version__
    print(f"OK: requests {requests.__version__}")
except ImportError as e:
    print(f"FEHLT: requests - {e}")
    dependencies['requests'] = None

try:
    from dotenv import load_dotenv
    dependencies['python-dotenv'] = "OK"
    print("OK: python-dotenv")
except ImportError as e:
    print(f"FEHLT: python-dotenv - {e}")
    dependencies['python-dotenv'] = None

try:
    import torch
    dependencies['torch'] = torch.__version__
    print(f"OK: torch {torch.__version__}")
except ImportError as e:
    print(f"FEHLT: torch - {e}")
    dependencies['torch'] = None

# ============================================================================
# 3. PROJEKT-SPEZIFISCHE IMPORTS
# ============================================================================
print("\n[3] PROJEKT-SPEZIFISCHE IMPORTS")
print("-"*70)

projekt_imports = {}

try:
    from ml.algorithm.supabase_api_loader import SupabaseAPILoader
    projekt_imports['SupabaseAPILoader'] = True
    print("OK: SupabaseAPILoader")
except ImportError as e:
    projekt_imports['SupabaseAPILoader'] = False
    print(f"FEHLER: SupabaseAPILoader - {e}")

try:
    from ml.algorithm.supabase_storage_handler import SupabaseStorageHandler
    projekt_imports['SupabaseStorageHandler'] = True
    print("OK: SupabaseStorageHandler")
except ImportError as e:
    projekt_imports['SupabaseStorageHandler'] = False
    print(f"FEHLER: SupabaseStorageHandler - {e}")

try:
    from ml.classifier import ProjektKlassifikator
    projekt_imports['ProjektKlassifikator'] = True
    print("OK: ProjektKlassifikator")
except ImportError as e:
    projekt_imports['ProjektKlassifikator'] = False
    print(f"FEHLER: ProjektKlassifikator - {e}")

# ============================================================================
# 4. UMGEBUNGSVARIABLEN (.env)
# ============================================================================
print("\n[4] UMGEBUNGSVARIABLEN")
print("-"*70)

from dotenv import load_dotenv
load_dotenv()

env_vars = {}

supabase_url = os.getenv('SUPABASE_URL')
env_vars['SUPABASE_URL'] = supabase_url is not None
if supabase_url:
    print(f"OK: SUPABASE_URL = {supabase_url[:40]}...")
else:
    print("FEHLT: SUPABASE_URL")

supabase_key = os.getenv('SUPABASE_KEY')
env_vars['SUPABASE_KEY'] = supabase_key is not None
if supabase_key:
    print(f"OK: SUPABASE_KEY = {supabase_key[:20]}...")
else:
    print("FEHLT: SUPABASE_KEY")

supabase_service_key = os.getenv('SUPABASE_SERVICE_KEY')
env_vars['SUPABASE_SERVICE_KEY'] = supabase_service_key is not None
if supabase_service_key:
    print(f"OK: SUPABASE_SERVICE_KEY = {supabase_service_key[:20]}...")
else:
    print("FEHLT: SUPABASE_SERVICE_KEY")

database_url = os.getenv('DATABASE_URL')
env_vars['DATABASE_URL'] = database_url is not None
if database_url:
    print(f"OK: DATABASE_URL = {database_url[:40]}...")
else:
    print("WARNUNG: DATABASE_URL nicht gesetzt")

# ============================================================================
# 5. SUPABASE VERBINDUNGSTEST
# ============================================================================
print("\n[5] SUPABASE VERBINDUNGSTEST")
print("-"*70)

verbindung_ok = False

if projekt_imports.get('SupabaseAPILoader'):
    try:
        from ml.algorithm.supabase_api_loader import teste_supabase_api
        if teste_supabase_api():
            print("OK: Supabase API Verbindung erfolgreich")
            verbindung_ok = True
        else:
            print("FEHLER: Supabase API Verbindung fehlgeschlagen")
    except Exception as e:
        print(f"FEHLER: Verbindungstest - {e}")
else:
    print("UEBERSPRUNGEN: SupabaseAPILoader nicht verfuegbar")

# ============================================================================
# 6. STORAGE TEST
# ============================================================================
print("\n[6] SUPABASE STORAGE TEST")
print("-"*70)

storage_ok = False

if projekt_imports.get('SupabaseStorageHandler') and env_vars.get('SUPABASE_SERVICE_KEY'):
    try:
        from ml.algorithm.supabase_storage_handler import SupabaseStorageHandler
        handler = SupabaseStorageHandler(bucket_name="models")

        # Liste Dateien
        files = handler.liste_modelle("test/")
        print(f"OK: Storage Bucket 'models' erreichbar")
        print(f"    Dateien im test/ Ordner: {len(files)}")
        storage_ok = True
    except Exception as e:
        print(f"FEHLER: Storage Test - {e}")
else:
    print("UEBERSPRUNGEN: SupabaseStorageHandler oder SERVICE_KEY fehlt")

# ============================================================================
# 7. INTEGRATION TEST
# ============================================================================
print("\n[7] INTEGRATION TEST")
print("-"*70)

integration_ok = False

if all([
    projekt_imports.get('ProjektKlassifikator'),
    env_vars.get('SUPABASE_URL'),
    env_vars.get('SUPABASE_SERVICE_KEY')
]):
    try:
        from ml.classifier import ProjektKlassifikator

        # Erstelle Klassifikator
        klassifikator = ProjektKlassifikator()
        print("OK: ProjektKlassifikator initialisiert")

        # Prüfe Methoden
        if hasattr(klassifikator, 'speichern') and hasattr(klassifikator, 'laden'):
            print("OK: speichern() und laden() Methoden verfuegbar")

        if hasattr(klassifikator, 'lade_daten_von_supabase'):
            print("OK: lade_daten_von_supabase() Methode verfuegbar")

        integration_ok = True

    except Exception as e:
        print(f"FEHLER: Integration Test - {e}")
else:
    print("UEBERSPRUNGEN: Nicht alle Voraussetzungen erfuellt")

# ============================================================================
# 8. ZUSAMMENFASSUNG
# ============================================================================
print("\n" + "="*70)
print("ZUSAMMENFASSUNG")
print("="*70)

fehler_count = 0
warnung_count = 0

# Core Dependencies
print("\nCore Dependencies:")
for dep, version in dependencies.items():
    if version is None:
        print(f"  [FEHLT] {dep}")
        fehler_count += 1
    else:
        print(f"  [OK] {dep}: {version}")

# Projekt Imports
print("\nProjekt Imports:")
for imp, status in projekt_imports.items():
    if status:
        print(f"  [OK] {imp}")
    else:
        print(f"  [FEHLT] {imp}")
        fehler_count += 1

# Umgebungsvariablen
print("\nUmgebungsvariablen:")
for var, status in env_vars.items():
    if status:
        print(f"  [OK] {var}")
    else:
        if var == 'DATABASE_URL':
            print(f"  [WARNUNG] {var} (optional)")
            warnung_count += 1
        else:
            print(f"  [FEHLT] {var}")
            fehler_count += 1

# Tests
print("\nVerbindungstests:")
print(f"  {'[OK]' if verbindung_ok else '[FEHLER]'} Supabase API")
print(f"  {'[OK]' if storage_ok else '[FEHLER]'} Supabase Storage")
print(f"  {'[OK]' if integration_ok else '[FEHLER]'} Classifier Integration")

if not verbindung_ok:
    fehler_count += 1
if not storage_ok:
    fehler_count += 1
if not integration_ok:
    fehler_count += 1

# Finale Bewertung
print("\n" + "="*70)
if fehler_count == 0 and warnung_count == 0:
    print("ERGEBNIS: ALLES PERFEKT! Alle Tests bestanden.")
elif fehler_count == 0:
    print(f"ERGEBNIS: OK ({warnung_count} Warnung(en))")
else:
    print(f"ERGEBNIS: {fehler_count} Fehler, {warnung_count} Warnung(en)")
print("="*70)
