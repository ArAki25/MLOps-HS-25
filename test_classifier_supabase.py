"""
Quick Test: Classifier mit Supabase Storage
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent / "ml"))

from classifier import ProjektKlassifikator
import joblib

print("="*70)
print("TEST: Classifier mit Supabase Storage")
print("="*70)

# Test 1: Erstelle ein einfaches Test-Modell
print("\n[TEST 1] Erstelle Test-Modell-Daten...")
klassifikator = ProjektKlassifikator()

# Erstelle minimal test data
test_model_data = {
    'rf_classifier': None,  # Würde normalerweise ein trainiertes Modell sein
    'label_encoders': {'test': 'encoder'},
    'kriterien_config': {'kantone': ['ZH'], 'keywords': ['IT', 'Software']}
}

# Speichere manuell um RF-Classifier-Prüfung zu umgehen
klassifikator.rf_classifier = "dummy"  # Trick für Test
klassifikator.label_encoders = test_model_data['label_encoders']
klassifikator.kriterien_config = test_model_data['kriterien_config']

# Test 2: Speichere zu Supabase
print("\n[TEST 2] Speichere zu Supabase Storage...")
try:
    klassifikator.speichern(
        pfad="test/classifier_test.pkl",
        zu_supabase=True,
        bucket_name="models"
    )
    print("✓ Speichern erfolgreich")
except Exception as e:
    print(f"❌ Fehler beim Speichern: {e}")
    exit(1)

# Test 3: Lade von Supabase
print("\n[TEST 3] Lade von Supabase Storage...")
klassifikator_neu = ProjektKlassifikator()
try:
    klassifikator_neu.laden(
        pfad="test/classifier_test.pkl",
        von_supabase=True,
        bucket_name="models"
    )
    print("✓ Laden erfolgreich")
except Exception as e:
    print(f"❌ Fehler beim Laden: {e}")
    exit(1)

# Test 4: Prüfe ob Daten übereinstimmen
print("\n[TEST 4] Prüfe Daten...")
if klassifikator_neu.kriterien_config == klassifikator.kriterien_config:
    print("✓ Kriterien stimmen überein!")
    print(f"  Kantone: {klassifikator_neu.kriterien_config['kantone']}")
    print(f"  Keywords: {klassifikator_neu.kriterien_config['keywords']}")
else:
    print("❌ Daten unterschiedlich")
    exit(1)

print("\n" + "="*70)
print("✓ ALLE TESTS BESTANDEN!")
print("="*70)
print("\nDu kannst jetzt:")
print("1. Modelle direkt zu Supabase speichern nach Training")
print("2. Modelle von Supabase laden für Vorhersagen")
print("3. Den restricted Storage Bucket verwenden")
print("\nBeispiel:")
print("  klassifikator.speichern('production/model_v1.pkl', zu_supabase=True)")
print("  klassifikator.laden('production/model_v1.pkl', von_supabase=True)")
