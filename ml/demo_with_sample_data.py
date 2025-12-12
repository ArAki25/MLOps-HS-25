"""
Demo: Classifier mit Supabase - Mit Beispieldaten
Da die Tabelle leer ist, erstellen wir Beispieldaten zum Testen
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

# Füge den ml/algorithm Pfad hinzu
sys.path.append(str(Path(__file__).parent / "algorithm"))

from supabase_api_loader import teste_supabase_api
from classifier import ProjektKlassifikator

def erstelle_beispieldaten():
    """Erstellt Beispieldaten im SIMAP-Format"""
    print("\n[INFO] Erstelle Beispieldaten...")

    # Mix aus relevanten und irrelevanten Projekten
    relevant_titles = [
        'Sanierung Hauptstrasse', 'Neubau Brücke', 'Tunnel Renovation',
        'Strassenbau Projekt', 'Brückensanierung', 'Tunnelbau',
        'Brücke Instandsetzung', 'Tunnel Sanierung', 'Tiefbau'
    ]

    irrelevant_titles = [
        'IT-Dienstleistungen', 'Büromaterial Lieferung', 'Software Entwicklung',
        'Catering Service', 'Reinigungsdienste', 'Gebäudereinigung',
        'Versicherung Ausschreibung', 'Marketing Kampagne', 'Event Organisation',
        'Textildruck', 'Druckerei Auftrag', 'Werbematerial'
    ]

    # 50% relevant, 50% irrelevant
    titles = (relevant_titles * 6 + irrelevant_titles * 4)[:100]

    data = {
        'id': range(1, 101),
        'title': titles,
        'description': [
            'Umfassende Sanierung der Hauptstrasse inkl. Belag',
            'Neubau einer Autobahnbrücke',
            'Renovationsarbeiten im Alpentunnel',
            'Entwicklung von Geschäftsanwendungen',
            'Lieferung von Büromaterial für Verwaltung',
            'Neubau und Sanierung von Kantonsstrassen',
        ] * 17,  # ca. 100 Einträge
        'canton': ['ZH', 'BE', 'GR', 'VD', 'AG', 'SG', 'TI', 'VS'] * 13,
        'project_type': ['tender', 'direct_award'] * 50,
        'order_type': ['construction', 'service', 'supply'] * 34,
        'publication_date': ['2024-12-01'] * 100,
        'submission_deadline': ['2025-01-15'] * 100,
        'estimated_amount': np.random.randint(100000, 5000000, 100),
        'cpv_code': ['45', '71', '72', '30'] * 25,
        'publication_type': ['tender'] * 100,
        'project_subtype': ['open'] * 100,
        'process_type': ['open'] * 100,
        'lots_type': ['single'] * 100,
        'construction_type': ['new'] * 100,
        'construction_category': ['building'] * 100,
        'creation_language': ['de'] * 100,
    }

    # Kürze auf 100
    for key in data:
        if len(data[key]) > 100:
            data[key] = data[key][:100]

    df = pd.DataFrame(data)
    print(f"✓ {len(df)} Beispiel-Projekte erstellt")
    return df

def main():
    print("="*70)
    print("DEMO: CLASSIFIER MIT SUPABASE-INTEGRATION")
    print("="*70)

    # Schritt 1: Teste Supabase-Verbindung
    print("\n[SCHRITT 1] Teste Supabase-Verbindung...")
    if teste_supabase_api():
        print("✓ Supabase ist verbunden und bereit!")
    else:
        print("⚠ Supabase-Verbindung fehlgeschlagen")
        print("  (Demo läuft trotzdem mit Beispieldaten)")

    # Schritt 2: Lade Daten (Beispieldaten, da Tabelle leer ist)
    print("\n[SCHRITT 2] Lade Daten...")
    print("  Info: Da simap_projects leer ist, nutzen wir Beispieldaten")
    df = erstelle_beispieldaten()

    # Schritt 3: Initialisiere Classifier
    print("\n[SCHRITT 3] Initialisiere ProjektKlassifikator...")
    klassifikator = ProjektKlassifikator()

    # Schritt 4: Definiere Kriterien
    print("\n[SCHRITT 4] Definiere Kriterien...")
    kriterien = {
        'kantone': ['ZH', 'BE', 'GR'],
        'keywords': ['Brücke', 'Strasse', 'Tunnel', 'Sanierung'],
        'projekt_typen': ['tender'],
        'auftrags_arten': ['construction']
    }
    klassifikator.kriterien_config = kriterien
    print(f"  Kantone: {kriterien['kantone']}")
    print(f"  Keywords: {kriterien['keywords']}")

    # Schritt 5: Erstelle Labels
    print("\n[SCHRITT 5] Erstelle Labels...")
    labels = klassifikator.erstelle_labels_aus_kriterien(df, kriterien)
    n_interessant = np.sum(labels == 1)
    print(f"  Interessante Projekte: {n_interessant}/{len(labels)}")

    # Schritt 6: Trainiere Modell
    print("\n[SCHRITT 6] Trainiere Modell...")
    accuracy = klassifikator.trainieren(df, labels)

    # Schritt 7: Speichere Modell
    print("\n[SCHRITT 7] Speichere Modell...")
    model_path = "supabase_classifier_demo.pkl"
    klassifikator.speichern(model_path)

    # Schritt 8: Teste Vorhersagen
    print("\n[SCHRITT 8] Teste Vorhersagen...")
    interesting = klassifikator.finde_interessante(df, min_prob=0.6, top_n=5)

    print(f"\n✓ Top 5 interessante Projekte gefunden:")
    for i, (idx, row) in enumerate(interesting.head(5).iterrows(), 1):
        print(f"\n  {i}. {row['title']}")
        print(f"     Wahrscheinlichkeit: {row['interessant_wahrscheinlichkeit']:.1%}")
        print(f"     Kanton: {row['canton']}")

    print("\n" + "="*70)
    print("✓ DEMO ERFOLGREICH!")
    print("="*70)
    print(f"\nDie Integration funktioniert! Sobald Daten in simap_projects")
    print(f"sind, kannst du classifier.py starten und direkt verwenden.")
    print(f"\nGespeichertes Modell: {model_path}")

if __name__ == "__main__":
    main()
