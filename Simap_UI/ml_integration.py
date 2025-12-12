"""
ml_integration.py - Integration des SIMAP ML-Klassifikators
Basiert auf dem Code deines KI-Kollegen

Angepasst für die Web-Integration
"""

import os
import re
import pickle
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from typing import Dict

# Globale Klassifikatoren
_order_type_classifier = None
_size_classifier = None
_model_trained = False


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


def load_training_data_from_supabase() -> pd.DataFrame:
    """Lädt Trainingsdaten aus Supabase"""
    try:
        from Simap_UI.supabase_database import supabase, get_all_ausschreibungen

        print("Lade Daten aus Supabase...")
        data = get_all_ausschreibungen(limit=10000)

        if not data:
            print("Keine Daten in Supabase gefunden!")
            return pd.DataFrame()

        df = pd.DataFrame(data)
        print(f"✅ {len(df)} Datensätze aus Supabase geladen")
        return df

    except Exception as e:
        print(f"Fehler beim Laden aus Supabase: {e}")
        return pd.DataFrame()


def prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    """Bereitet Features für das Training vor."""
    df = df.copy()

    # Text-Feature erstellen
    df["text_attribute"] = (
            df["titel"].fillna("") + " " + df["beschreibung"].fillna("")
    ).str.lower()

    # Fehlende Spalten mit Defaults füllen
    if "country" not in df.columns:
        df["country"] = "CH"
    if "canton" not in df.columns:
        df["canton"] = "unknown"
    if "process_type" not in df.columns:
        df["process_type"] = "open"
    if "project_type" not in df.columns:
        df["project_type"] = df["kategorie"].fillna("unknown")

    # order_type bereinigen (falls vorhanden)
    if "order_type" in df.columns:
        df = df.dropna(subset=["order_type"])
        df = df[df["order_type"] != "unknown"]
    else:
        # Erstelle order_type basierend auf Kategorie
        df["order_type"] = "service"  # Default

    # Projekt-Wert extrahieren
    if "wert" in df.columns:
        df["project_value_chf"] = df["wert"].apply(parse_value)
    else:
        df["project_value_chf"] = np.nan

    return df


def train_order_type_classifier(df: pd.DataFrame):
    """Trainiert den Order-Type Klassifikator."""
    global _order_type_classifier

    print("\n--- Training Order-Type Klassifikator ---")

    if "order_type" not in df.columns or df["order_type"].isna().all():
        print("⚠️  Keine order_type Daten verfügbar - überspringe Training")
        return None

    y = df["order_type"]
    X = df[["text_attribute", "country", "canton", "process_type", "project_type"]].fillna("")

    if len(y) < 10:
        print("⚠️  Zu wenig Daten für Order-Type Training")
        return None

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.15, random_state=42
    )

    preprocessor = ColumnTransformer(
        transformers=[
            ("text", TfidfVectorizer(max_features=5000), "text_attribute"),
            ("cat", OneHotEncoder(handle_unknown="ignore"),
             ["country", "canton", "process_type", "project_type"]),
        ],
        remainder="drop"
    )

    model = RandomForestClassifier(n_estimators=50, random_state=42, n_jobs=-1)

    _order_type_classifier = Pipeline(steps=[
        ("preprocessor", preprocessor),
        ("classifier", model)
    ])

    print("Trainiere Order-Type Modell...")
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
    valid_values = df["project_value_chf"].dropna()

    if len(valid_values) < 10:
        print("⚠️  Zu wenig Daten mit Projektwert - überspringe Size Training")
        return None

    q1, q2 = valid_values.quantile([0.33, 0.66])

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

    if len(df_size) < 10:
        print("⚠️  Nicht genug Daten mit bekannter Projektgrösse")
        return None

    X = df_size[["text_attribute", "country", "canton", "process_type", "project_type"]].fillna("")
    y = df_size["size_bucket"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.15, random_state=42
    )

    preprocessor = ColumnTransformer(
        transformers=[
            ("text", TfidfVectorizer(max_features=5000), "text_attribute"),
            ("cat", OneHotEncoder(handle_unknown="ignore"),
             ["country", "canton", "process_type", "project_type"]),
        ],
        remainder="drop"
    )

    model = RandomForestClassifier(n_estimators=50, random_state=42, n_jobs=-1)

    _size_classifier = Pipeline(steps=[
        ("preprocessor", preprocessor),
        ("classifier", model)
    ])

    print("Trainiere Size-Bucket Modell...")
    _size_classifier.fit(X_train, y_train)

    y_pred = _size_classifier.predict(X_test)
    print("\nKlassifikationsreport (Size-Bucket):")
    print(classification_report(y_test, y_pred))

    return _size_classifier


def train_models():
    """Trainiert beide Modelle mit Supabase-Daten"""
    global _model_trained

    print("=" * 60)
    print("SIMAP ML-Modell Training")
    print("=" * 60)

    # Daten aus Supabase laden
    df = load_training_data_from_supabase()

    if df.empty:
        print("⚠️  Keine Trainingsdaten verfügbar!")
        print("Verwende Fallback-Modell...")
        _model_trained = False
        return False

    # Features vorbereiten
    df = prepare_features(df)
    print(f"\nVorbereitete Daten: {df.shape}")

    # Modelle trainieren
    train_order_type_classifier(df)
    train_size_classifier(df)

    _model_trained = True

    print("\n" + "=" * 60)
    print("✅ Training abgeschlossen!")
    print("=" * 60)

    return True


def save_models(path: str = "models/"):
    """Speichere trainierte Modelle"""
    if not os.path.exists(path):
        os.makedirs(path)

    if _order_type_classifier:
        with open(f"{path}order_type_model.pkl", "wb") as f:
            pickle.dump(_order_type_classifier, f)
        print(f"✅ Order-Type Modell gespeichert: {path}order_type_model.pkl")

    if _size_classifier:
        with open(f"{path}size_model.pkl", "wb") as f:
            pickle.dump(_size_classifier, f)
        print(f"✅ Size Modell gespeichert: {path}size_model.pkl")


def load_models(path: str = "models/"):
    """Lade gespeicherte Modelle"""
    global _order_type_classifier, _size_classifier, _model_trained

    try:
        order_path = f"{path}order_type_model.pkl"
        size_path = f"{path}size_model.pkl"

        if os.path.exists(order_path):
            with open(order_path, "rb") as f:
                _order_type_classifier = pickle.load(f)
            print(f"✅ Order-Type Modell geladen: {order_path}")

        if os.path.exists(size_path):
            with open(size_path, "rb") as f:
                _size_classifier = pickle.load(f)
            print(f"✅ Size Modell geladen: {size_path}")

        _model_trained = True
        return True
    except Exception as e:
        print(f"❌ Fehler beim Laden der Modelle: {e}")
        _model_trained = False
        return False


def predict_ausschreibung(data: Dict) -> Dict:
    """
    Vorhersage für eine einzelne Ausschreibung

    Args:
        data: Dictionary mit:
            - titel: String
            - beschreibung: String
            - kategorie: String (optional)
            - wert: String (optional)

    Returns:
        Dictionary mit predictions
    """
    # Erstelle DataFrame mit einem Eintrag
    df = pd.DataFrame([{
        "titel": data.get("titel", ""),
        "beschreibung": data.get("beschreibung", ""),
        "kategorie": data.get("kategorie", ""),
        "country": "CH",
        "canton": "unknown",
        "process_type": "open",
        "project_type": data.get("kategorie", "unknown")
    }])

    df = prepare_features(df)

    result = {
        "relevanz": calculate_relevanz(data),
        "order_type": "service",
        "size_bucket": "mittel"
    }

    # Vorhersagen mit ML-Modellen (falls trainiert)
    if _model_trained and _order_type_classifier:
        try:
            features = df[["text_attribute", "country", "canton", "process_type", "project_type"]].fillna("")
            result["order_type"] = _order_type_classifier.predict(features)[0]
        except:
            pass

    if _model_trained and _size_classifier:
        try:
            features = df[["text_attribute", "country", "canton", "process_type", "project_type"]].fillna("")
            result["size_bucket"] = _size_classifier.predict(features)[0]
        except:
            pass

    return result


def calculate_relevanz(data: Dict) -> int:
    """
    Berechnet Relevanz-Score (0-100) für eine Ausschreibung

    Verwendet regel-basierte Logik + ML wenn verfügbar
    """
    score = 50  # Basis

    # Text-basierte Scores
    titel = data.get("titel", "").lower()
    beschreibung = data.get("beschreibung", "").lower()
    kategorie = data.get("kategorie", "").lower()

    # IT/Software Keywords
    it_keywords = ["it", "software", "digital", "entwicklung", "cloud", "system", "crm", "erp"]
    for keyword in it_keywords:
        if keyword in titel:
            score += 15
        elif keyword in beschreibung:
            score += 5

    # Kategorie-Bonus
    if any(k in kategorie for k in ["it", "software", "cloud"]):
        score += 20

    # Projektgrösse (falls vorhanden)
    wert = data.get("wert", "")
    if wert:
        value = parse_value(wert)
        if not np.isnan(value):
            if value > 100000:
                score += 10
            if value > 500000:
                score += 5

    # Beschreibungslänge
    if len(beschreibung) > 100:
        score += 5

    return max(0, min(100, score))


def initialize_ml_system():
    """
    Initialisiert das ML-System
    Versucht gespeicherte Modelle zu laden, sonst Training
    """
    print("=" * 60)
    print("Initialisiere ML-System...")
    print("=" * 60)

    # Versuche Modelle zu laden
    if load_models():
        print("✅ Modelle erfolgreich geladen!")
        return True

    # Falls keine Modelle vorhanden, trainiere neue
    print("\nKeine gespeicherten Modelle gefunden. Starte Training...")
    success = train_models()

    if success:
        save_models()

    return success


if __name__ == "__main__":
    # Training starten
    initialize_ml_system()