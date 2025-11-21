"""
Beispiel-Skript zum Laden von SIMAP-Daten für ML-Training.

Dieses Skript zeigt verschiedene Möglichkeiten, Daten aus der
Supabase-Datenbank zu laden und für das Machine Learning zu verwenden.
"""

import logging
from datetime import datetime, timedelta
from database import (
    load_all_data,
    load_by_canton,
    load_by_publication_type,
    load_by_date_range,
    load_award_data,
    load_with_filters,
)
from database.loader import get_statistics

# Logging konfigurieren
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def example_1_basic_loading():
    """Beispiel 1: Einfaches Laden aller Daten"""
    print("\n" + "=" * 60)
    print("BEISPIEL 1: Alle Daten laden")
    print("=" * 60)

    # Alle Daten laden (limitiert auf 1000)
    df = load_all_data(limit=1000)

    print(f"\nDataFrame-Form: {df.shape}")
    print(f"Spalten: {list(df.columns)[:5]}...")
    print(f"\nErste 5 Zeilen:")
    print(df.head())

    return df


def example_2_canton_loading():
    """Beispiel 2: Daten nach Kanton filtern"""
    print("\n" + "=" * 60)
    print("BEISPIEL 2: Daten nach Kanton laden")
    print("=" * 60)

    # Zürich Daten
    df_zh = load_by_canton('ZH', limit=500)
    print(f"\nZürich Projekte: {len(df_zh)}")
    print(f"Kantone im Dataset: {df_zh['canton'].unique()}")

    # Mehrere Kantone (mit Custom-Filter)
    df_multiple = load_with_filters(cantons=['ZH', 'BL', 'BS'])
    print(f"\nZH, BL, BS Projekte: {len(df_multiple)}")

    return df_zh, df_multiple


def example_3_publication_types():
    """Beispiel 3: Nach Publikationstyp filtern"""
    print("\n" + "=" * 60)
    print("BEISPIEL 3: Nach Publikationstyp")
    print("=" * 60)

    # Nur Ausschreibungen
    df_tender = load_by_publication_type('tender', limit=1000)
    print(f"\nAusschreibungen (tender): {len(df_tender)}")

    # Nur Awards
    df_awards = load_award_data(limit=500)
    print(f"Zuschläge (award): {len(df_awards)}")
    print(f"Spalten mit Award-Info: {[col for col in df_awards.columns if 'award' in col.lower()]}")

    return df_tender, df_awards


def example_4_date_range():
    """Beispiel 4: Daten nach Datum filtern"""
    print("\n" + "=" * 60)
    print("BEISPIEL 4: Datum-Bereich laden")
    print("=" * 60)

    # Letzte 30 Tage
    start_30d = datetime.now() - timedelta(days=30)
    df_30d = load_by_date_range(start_30d)
    print(f"\nProjekte in letzten 30 Tagen: {len(df_30d)}")

    # Spezifisches Jahr
    start_2024 = datetime(2024, 1, 1)
    end_2024 = datetime(2024, 12, 31)
    df_2024 = load_by_date_range(start_2024, end_2024)
    print(f"Projekte in 2024: {len(df_2024)}")

    return df_30d, df_2024


def example_5_advanced_filters():
    """Beispiel 5: Komplexe Filter kombinieren"""
    print("\n" + "=" * 60)
    print("BEISPIEL 5: Komplexe Filter")
    print("=" * 60)

    # Große offene Ausschreibungen in deutschsprachigen Kantonen
    df_big = load_with_filters(
        cantons=['ZH', 'BE', 'SG', 'AG'],
        publication_types=['tender'],
        process_types=['open'],
        languages=['de'],
        min_amount=100000,
        limit=5000
    )
    print(f"\nGroße Ausschreibungen (>CHF 100k): {len(df_big)}")
    if len(df_big) > 0:
        print(f"Durchschnittliche Summe: CHF {df_big['estimated_amount'].mean():,.0f}")
        print(f"Max Summe: CHF {df_big['estimated_amount'].max():,.0f}")

    # Awards mit bekannten Gewinnern
    df_awards_known = load_with_filters(
        publication_types=['award'],
        min_amount=50000,
        limit=1000
    )
    print(f"\nAwards über CHF 50k mit Gewinner: {len(df_awards_known)}")
    if len(df_awards_known) > 0:
        print(f"Durchschn. Award-Summe: CHF {df_awards_known['award_amount'].mean():,.0f}")

    return df_big, df_awards_known


def example_6_statistics():
    """Beispiel 6: Datenbankstatistiken"""
    print("\n" + "=" * 60)
    print("BEISPIEL 6: Datenbankstatistiken")
    print("=" * 60)

    stats = get_statistics()

    print(f"\nGesamte Projekte: {stats.get('total_projects', 0):,}")
    print(f"Einzigartige Kantone: {stats.get('unique_cantons', 0)}")
    print(f"Publikationstypen: {stats.get('unique_publication_types', 0)}")
    print(f"Projekte mit Awards: {stats.get('with_awards', 0):,}")
    print(f"Summe Ausschreibungen: CHF {stats.get('total_estimated_amount', 0):,.0f}")
    print(f"Summe Awards: CHF {stats.get('total_award_amount', 0):,.0f}")

    return stats


def example_7_data_for_ml():
    """Beispiel 7: Daten für ML vorbereiten"""
    print("\n" + "=" * 60)
    print("BEISPIEL 7: ML-Training mit geladenem DataFrame")
    print("=" * 60)

    # Daten laden
    df = load_with_filters(
        publication_types=['award'],
        min_amount=10000,
        limit=5000
    )

    print(f"\nDataset-Größe: {df.shape}")
    print(f"Speichergröße: {df.memory_usage(deep=True).sum() / 1024**2:.2f} MB")

    # Datentypen anschauen
    print(f"\nDatentypen:")
    print(df.dtypes)

    # Fehlende Werte
    print(f"\nFehlende Werte (Top 10):")
    missing = df.isnull().sum()
    print(missing[missing > 0].nlargest(10))

    # Numerische Features für ML
    numeric_columns = df.select_dtypes(include=['int64', 'float64']).columns.tolist()
    print(f"\nNumerische Features: {numeric_columns}")

    # Text-Features für NLP
    text_columns = df.select_dtypes(include=['object']).columns.tolist()
    print(f"Text-Features: {text_columns[:5]}...")

    return df


def main():
    """Führt alle Beispiele aus"""
    try:
        print("\n" + "=" * 60)
        print("SIMAP DATENBANK LOADER - BEISPIELE")
        print("=" * 60)

        # Beispiele ausführen
        example_1_basic_loading()
        example_2_canton_loading()
        example_3_publication_types()
        example_4_date_range()
        example_5_advanced_filters()
        example_6_statistics()
        df_ml = example_7_data_for_ml()

        # Finale Ausgabe
        print("\n" + "=" * 60)
        print("ALLE BEISPIELE FERTIG!")
        print("=" * 60)
        print("\nFür dein ML-Training verwendest du z.B.:")
        print("  df = load_with_filters(...)")
        print("  X = df[['estimated_amount', 'number_of_submissions', ...]].fillna(0)")
        print("  y = df['award_amount']")
        print("  model.fit(X, y)")

    except Exception as e:
        logger.error(f"Fehler: {e}", exc_info=True)


if __name__ == "__main__":
    main()
