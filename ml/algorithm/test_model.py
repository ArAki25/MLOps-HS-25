"""
Test-Script für den SIMAP Projekt-Klassifikator mit Supabase
Testet Verbindung, Datenladung und Model-Funktionen
"""

import sys
import os
from dotenv import load_dotenv

# Fix Windows Console Encoding
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Lade Umgebungsvariablen
load_dotenv()

# Füge Parent-Directory zum Path hinzu
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from algorithm.model import SupabaseLoader, ProjektKlassifikator

def print_header(title):
    """Druckt eine formatierte Überschrift"""
    print("\n" + "="*70)
    print(title)
    print("="*70)


def test_1_umgebungsvariablen():
    """Test 1: Prüfe ob DATABASE_URL gesetzt ist"""
    print_header("TEST 1: Umgebungsvariablen")

    database_url = os.getenv('DATABASE_URL')

    if not database_url:
        print("❌ DATABASE_URL nicht gefunden!")
        print("\nBitte erstelle eine .env Datei mit:")
        print("DATABASE_URL=postgresql://postgres:PASSWORD@db.xxx.supabase.co:5432/postgres")
        return False

    # Prüfe ob es ein Platzhalter ist
    if '[YOUR-PASSWORD]' in database_url or 'YOUR_PASSWORD' in database_url:
        print("❌ DATABASE_URL enthält noch Platzhalter!")
        print("Bitte ersetze [YOUR-PASSWORD] mit deinem echten Passwort")
        return False

    print(f"✓ DATABASE_URL gefunden")
    print(f"  Host: {database_url.split('@')[1].split(':')[0] if '@' in database_url else '?'}")
    return True


def test_2_supabase_verbindung():
    """Test 2: Teste Supabase-Verbindung"""
    print_header("TEST 2: Supabase-Verbindung")

    try:
        loader = SupabaseLoader()

        if loader.verbinden():
            print("✓ Verbindung erfolgreich hergestellt")
            loader.trennen()
            return True
        else:
            print("❌ Verbindung fehlgeschlagen")
            return False

    except Exception as e:
        print(f"❌ Fehler beim Verbinden: {e}")
        return False


def test_3_daten_laden():
    """Test 3: Lade Test-Daten"""
    print_header("TEST 3: Daten aus Supabase laden")

    try:
        with SupabaseLoader() as db:
            # Lade nur 5 Tage, um schnell zu sein
            df = db.lade_projekte(tage_zurueck=5)

            if len(df) == 0:
                print("⚠ Keine Projekte gefunden (letzte 5 Tage)")
                print("Versuche mit mehr Tagen...")
                df = db.lade_projekte(tage_zurueck=30)

            if len(df) > 0:
                print(f"✓ {len(df)} Projekte geladen")
                print(f"\nBeispiel-Projekt:")
                print(f"  Titel: {df.iloc[0]['title']}")
                print(f"  Kanton: {df.iloc[0].get('canton', 'N/A')}")
                print(f"  Typ: {df.iloc[0].get('project_type', 'N/A')}")
                print(f"  Datum: {df.iloc[0].get('publication_date', 'N/A')}")

                print(f"\nVerfügbare Spalten ({len(df.columns)}):")
                print(f"  {', '.join(df.columns.tolist()[:8])}...")

                return df
            else:
                print("❌ Keine Projekte in der Datenbank gefunden")
                return None

    except Exception as e:
        print(f"❌ Fehler beim Laden: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_4_model_initialisierung():
    """Test 4: Initialisiere Model"""
    print_header("TEST 4: Model Initialisierung")

    try:
        print("Initialisiere ProjektKlassifikator...")
        klassifikator = ProjektKlassifikator()
        print("✓ Model erfolgreich initialisiert")
        print(f"  Embedding Model: {klassifikator.embedding_model}")
        print(f"  Kategoriale Features: {len(klassifikator.categorical_features)}")
        return klassifikator
    except Exception as e:
        print(f"❌ Fehler bei Initialisierung: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_5_schnelltest_mit_dummy_kriterien(klassifikator, df):
    """Test 5: Schnelltest mit Dummy-Kriterien"""
    print_header("TEST 5: Schnelltest mit Dummy-Kriterien")

    if klassifikator is None or df is None or len(df) == 0:
        print("⚠ Übersprungen (benötigt Model und Daten)")
        return False

    try:
        # Erstelle simple Test-Kriterien
        test_kriterien = {
            'keywords': ['brücke', 'strasse', 'tunnel', 'bau']
        }

        # Wenn Kanton-Spalte existiert, nutze häufigsten Kanton
        if 'canton' in df.columns:
            haeufigster_kanton = df['canton'].value_counts().index[0]
            test_kriterien['kantone'] = [haeufigster_kanton]
            print(f"Teste mit Kanton: {haeufigster_kanton}")

        klassifikator.kriterien_config = test_kriterien

        # Erstelle Labels
        print("\nErstelle Labels...")
        labels = klassifikator.erstelle_labels_aus_kriterien(df, test_kriterien)

        n_interessant = sum(labels == 1)
        n_nicht = sum(labels == 0)

        print(f"\n✓ Labels erstellt:")
        print(f"  Interessant: {n_interessant} ({n_interessant/len(labels)*100:.1f}%)")
        print(f"  Nicht interessant: {n_nicht}")

        if n_interessant < 10:
            print("\n⚠ Sehr wenige interessante Projekte für Training")
            print("Für echtes Training mehr Kriterien oder Daten verwenden!")
            return False

        # Wenn genug Daten: Teste Feature-Erstellung
        if n_interessant >= 10:
            print("\nTeste Feature-Erstellung (kleine Stichprobe)...")
            df_sample = df.head(20)  # Nur 20 für schnellen Test
            features = klassifikator.erstelle_features(df_sample, fit=True)
            print(f"✓ Features erstellt: {features.shape}")

        return True

    except Exception as e:
        print(f"❌ Fehler beim Schnelltest: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_6_filter_funktionen(df):
    """Test 6: Teste Filterfunktionen"""
    print_header("TEST 6: Supabase Filter-Funktionen")

    if df is None or len(df) == 0:
        print("⚠ Übersprungen (benötigt Daten)")
        return False

    try:
        # Teste Filter nach Kanton (wenn vorhanden)
        if 'canton' in df.columns and df['canton'].notna().any():
            test_kanton = df['canton'].value_counts().index[0]

            with SupabaseLoader() as db:
                df_filtered = db.lade_projekte(
                    tage_zurueck=30,
                    kantone=[test_kanton]
                )

                print(f"✓ Kanton-Filter funktioniert:")
                print(f"  Ohne Filter: {len(df)} Projekte")
                print(f"  Mit Filter ({test_kanton}): {len(df_filtered)} Projekte")
                return True
        else:
            print("⚠ Keine Kanton-Spalte zum Testen")
            return False

    except Exception as e:
        print(f"❌ Fehler beim Filter-Test: {e}")
        return False


def main():
    """Hauptfunktion - führt alle Tests aus"""
    print("="*70)
    print("SIMAP PROJEKT-KLASSIFIKATOR - TEST SUITE")
    print("="*70)
    print("\nDieses Script testet:")
    print("  1. Umgebungsvariablen (.env)")
    print("  2. Supabase-Verbindung")
    print("  3. Daten laden")
    print("  4. Model Initialisierung")
    print("  5. Schnelltest mit Dummy-Kriterien")
    print("  6. Filter-Funktionen")

    # Führe Tests aus
    results = {}

    results['env'] = test_1_umgebungsvariablen()

    if not results['env']:
        print("\n" + "="*70)
        print("TESTS ABGEBROCHEN - Umgebungsvariablen fehlen")
        print("="*70)
        return

    results['connection'] = test_2_supabase_verbindung()

    if not results['connection']:
        print("\n" + "="*70)
        print("TESTS ABGEBROCHEN - Keine Verbindung zu Supabase")
        print("="*70)
        print("\nMögliche Lösungen:")
        print("1. Prüfe ob DATABASE_URL korrekt ist")
        print("2. Prüfe ob Passwort korrekt ist")
        print("3. Prüfe ob Internetverbindung besteht")
        print("4. Prüfe Supabase Dashboard ob Projekt aktiv ist")
        return

    df = test_3_daten_laden()
    results['data'] = df is not None

    klassifikator = test_4_model_initialisierung()
    results['model'] = klassifikator is not None

    results['quicktest'] = test_5_schnelltest_mit_dummy_kriterien(klassifikator, df)

    results['filters'] = test_6_filter_funktionen(df)

    # Zusammenfassung
    print("\n" + "="*70)
    print("TEST ZUSAMMENFASSUNG")
    print("="*70)

    for test_name, result in results.items():
        status = "✓ BESTANDEN" if result else "❌ FEHLGESCHLAGEN"
        print(f"{test_name.upper():15s}: {status}")

    # Gesamtergebnis
    all_critical_passed = all([
        results['env'],
        results['connection'],
        results['data'],
        results['model']
    ])

    print("\n" + "="*70)
    if all_critical_passed:
        print("✓ ALLE KRITISCHEN TESTS BESTANDEN!")
        print("="*70)
        print("\nDein Model ist bereit!")
        print("Starte das Hauptprogramm mit:")
        print("  python ml/algorithm/model.py")
    else:
        print("❌ EINIGE TESTS FEHLGESCHLAGEN")
        print("="*70)
        print("\nBitte behebe die Fehler oben, bevor du weitermachst.")

    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTests abgebrochen durch Benutzer.")
    except Exception as e:
        print(f"\n\n❌ Unerwarteter Fehler: {e}")
        import traceback
        traceback.print_exc()
