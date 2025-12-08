"""
ML-Klassifikator für SIMAP-Projekte.

Trainiert zwei Random Forest Klassifikatoren:
1. order_type: Klassifiziert die Art des Auftrags
2. size_bucket: Klassifiziert die Projektgrösse (klein/mittel/gross)

Verwendung:
    python ml/classifier.py  # Trainiert die Modelle
    
    # Oder als Modul:
    from ml.classifier import predict_project_info
    result = predict_project_info(df_input)
"""
import os
import sys
import re

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

# Füge Parent-Verzeichnis zum Path hinzu für Imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Globale Klassifikatoren (werden beim Training gesetzt)
_order_type_classifier = None
_size_classifier = None


def parse_value(x):
    """Parst Geldbeträge aus verschiedenen Formaten."""
    if pd.isna(x):
        return np.nan
    s = str(x)
    s = s.replace("CHF", "").replace("'", "").replace("'", "").replace(" ", "")
    s = re.sub(r"[^0-9.]", "", s)
    try:
        return float(s)
    except (ValueError, TypeError):
        return np.nan


def load_training_data(csv_path: str = None) -> pd.DataFrame:
    """
    Lädt Trainingsdaten aus CSV oder Datenbank.
    
    Args:
        csv_path: Pfad zur CSV-Datei. Wenn None, wird versucht aus DB zu laden.
    
    Returns:
        DataFrame mit Trainingsdaten
    """
    if csv_path and os.path.exists(csv_path):
        print(f"Lade Daten aus: {csv_path}")
        return pd.read_csv(csv_path)
    
    # Versuche aus Datenbank zu laden
    try:
        from database import load_all_data
        print("Lade Daten aus Supabase...")
        df = load_all_data(limit=10000)
        if not df.empty:
            return df
    except Exception as e:
        print(f"Konnte nicht aus DB laden: {e}")
    
    # Fallback: Standard-Pfade prüfen
    default_paths = [
        "data/simap_projects.csv",
        "../data/simap_projects.csv",
    ]
    
    for path in default_paths:
        if os.path.exists(path):
            print(f"Lade Daten aus: {path}")
            return pd.read_csv(path)
    
    raise FileNotFoundError(
        "Keine Trainingsdaten gefunden! Bitte führe zuerst "
        "'python scripts/update_db.py' aus oder stelle eine CSV-Datei bereit."
    )


def prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    """Bereitet Features für das Training vor."""
    df = df.copy()
    
    # Text-Feature erstellen
    df["text_attribute"] = (
        df["title"].fillna("") + " " + df["description"].fillna("")
    ).str.lower()
    
    # order_type bereinigen
    df = df.dropna(subset=["order_type"])
    df = df[df["order_type"] != "unknown"]
    
    # Projekt-Wert extrahieren
    df["value_raw"] = df.get("estimated_amount", pd.Series()).fillna(
        df.get("award_amount", pd.Series())
    )
    df["project_value_chf"] = df["value_raw"].apply(parse_value)
    
    return df


def train_order_type_classifier(df: pd.DataFrame):
    """Trainiert den Order-Type Klassifikator."""
    global _order_type_classifier
    
    print("\n--- Training Order-Type Klassifikator ---")
    
    y = df["order_type"]
    X = df[["text_attribute", "country", "canton", "process_type", "project_type"]].fillna("")
    
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.15, random_state=42, stratify=y
    )
    
    preprocessor = ColumnTransformer(
        transformers=[
            ("text", TfidfVectorizer(max_features=15000), "text_attribute"),
            ("cat", OneHotEncoder(handle_unknown="ignore"), 
             ["country", "canton", "process_type", "project_type"]),
        ],
        remainder="drop"
    )
    
    model = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)
    
    _order_type_classifier = Pipeline(steps=[
        ("preprocessor", preprocessor),
        ("classifier", model)
    ])
    
    print("Trainiere...")
    _order_type_classifier.fit(X_train, y_train)
    
    y_pred = _order_type_classifier.predict(X_test)
    print("\nKlassifikationsreport (Order-Type):")
    print(classification_report(y_test, y_pred))
    
    return _order_type_classifier


def train_size_classifier(df: pd.DataFrame):
    """Trainiert den Projektgrössen-Klassifikator."""
    global _size_classifier
    
    print("\n--- Training Size-Bucket Klassifikator ---")
    
    # Size-Buckets erstellen
    q1, q2 = df["project_value_chf"].quantile([0.45, 0.70])
    
    def size_class(v):
        if np.isnan(v):
            return "unknown"
        if v <= q1:
            return "klein"
        if v <= q2:
            return "mittel"
        return "gross"
    
    df["size_bucket"] = df["project_value_chf"].apply(size_class)
    print(f"Size-Bucket Verteilung:\n{df['size_bucket'].value_counts()}")
    
    # Nur bekannte Grössen
    df_size = df[df["size_bucket"] != "unknown"]
    
    if len(df_size) < 100:
        print("Nicht genug Daten mit bekannter Projektgrösse für Training!")
        return None
    
    X = df_size[["text_attribute", "country", "canton", "process_type", "project_type"]].fillna("")
    y = df_size["size_bucket"]
    
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.15, random_state=42, stratify=y
    )
    
    preprocessor = ColumnTransformer(
        transformers=[
            ("text", TfidfVectorizer(max_features=15000), "text_attribute"),
            ("cat", OneHotEncoder(handle_unknown="ignore"),
             ["country", "canton", "process_type", "project_type"]),
        ],
        remainder="drop"
    )
    
    model = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)
    
    _size_classifier = Pipeline(steps=[
        ("preprocessor", preprocessor),
        ("classifier", model)
    ])
    
    print("Trainiere...")
    _size_classifier.fit(X_train, y_train)
    
    y_pred = _size_classifier.predict(X_test)
    print("\nKlassifikationsreport (Size-Bucket):")
    print(classification_report(y_test, y_pred))
    
    return _size_classifier


def predict_project_info(df_input: pd.DataFrame) -> pd.DataFrame:
    """
    Vorhersage für neue Projekte.
    
    Args:
        df_input: DataFrame mit den Spalten:
            - text_attribute (oder title + description)
            - country, canton, process_type, project_type
    
    Returns:
        DataFrame mit order_type_pred und size_bucket_pred
    """
    global _order_type_classifier, _size_classifier
    
    if _order_type_classifier is None or _size_classifier is None:
        raise RuntimeError(
            "Klassifikatoren nicht trainiert! "
            "Führe zuerst 'python ml/classifier.py' aus."
        )
    
    # Features vorbereiten falls nötig
    df = df_input.copy()
    if "text_attribute" not in df.columns:
        df["text_attribute"] = (
            df.get("title", "").fillna("") + " " + 
            df.get("description", "").fillna("")
        ).str.lower()
    
    # Features auswählen
    features = df[["text_attribute", "country", "canton", "process_type", "project_type"]].fillna("")
    
    # Vorhersagen
    order_type_pred = _order_type_classifier.predict(features)
    size_bucket_pred = _size_classifier.predict(features)
    
    return pd.DataFrame({
        "order_type_pred": order_type_pred,
        "size_bucket_pred": size_bucket_pred
    })


def main():
    """Hauptfunktion zum Training der Klassifikatoren."""
    print("=" * 60)
    print("SIMAP ML-Klassifikator Training")
    print("=" * 60)
    
    # Daten laden
    df = load_training_data()
    print(f"\nGeladene Daten: {df.shape}")
    
    # Features vorbereiten
    df = prepare_features(df)
    print(f"Nach Vorbereitung: {df.shape}")
    
    if len(df) < 100:
        print("Nicht genug Daten für Training!")
        return
    
    # Klassifikatoren trainieren
    train_order_type_classifier(df)
    train_size_classifier(df)
    
    print("\n" + "=" * 60)
    print("✓ Training abgeschlossen!")
    print("=" * 60)


if __name__ == "__main__":
    main()

