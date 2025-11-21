"""
Database Loader für SIMAP-Daten in Pandas DataFrames.

Dieses Modul bietet einfache Funktionen zum Laden von Daten aus der
Supabase-Datenbank direkt in Pandas DataFrames für das Machine Learning.

Beispiel:
    from database import load_all_data, load_by_canton

    # Alle Daten laden
    df = load_all_data()

    # Mit Filtern
    df_zh = load_by_canton('ZH')
    df_awards = load_award_data()
"""

from .loader import (
    load_all_data,
    load_by_canton,
    load_by_publication_type,
    load_by_date_range,
    load_award_data,
    load_with_filters,
)

__all__ = [
    'load_all_data',
    'load_by_canton',
    'load_by_publication_type',
    'load_by_date_range',
    'load_award_data',
    'load_with_filters',
]
