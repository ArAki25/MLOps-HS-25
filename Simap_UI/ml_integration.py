"""
ml_integration.py - Integration des SIMAP ML-Klassifikators
Angepasst für projects_website Tabelle
"""

import os
import re
import pickle
import numpy as np
import pandas as pd
from typing import Dict

# Versuche sklearn zu importieren, falls nicht verfügbar nutze Fallback
try:
    from sklearn.compose import ColumnTransformer
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics import classification_report
    from sklearn.model_selection import train_test_split
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder

    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    print("⚠️  sklearn nicht verfügbar - verwende Fallback-Modell")

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
    """Lädt Trainingsdaten aus Supabase (projects_website)"""
    try:
        from supabase_database import supabase

        if not supabase:
            print("Supabase nicht initialisiert!")
            return pd.DataFrame()

        print("Lade Daten aus Supabase (projects_website)...")
        response = supabase.table('projects_website') \
            .select('*') \
            .limit(10000) \
            .execute()

        if not response.data:
            print("Keine Daten in Supabase gefunden!")
            return pd.DataFrame()

        df = pd.DataFrame(response.data)
        print(f"✅ {len(df)} Datensätze aus Supabase geladen")
        return df

    except Exception as e:
        print(f"Fehler beim Laden aus Supabase: {e}")
        return pd.DataFrame()


def prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    """Bereitet Features für das Training vor (angepasst für projects_website)."""
    df = df.copy()

    # Text-Feature erstellen aus title_de und description_de
    title = df.get("title_de", pd.Series([""] * len(df))).fillna("")
    description = df.get("description_de", pd.Series([""] * len(df))).fillna("")
    df["text_attribute"] = (title + " " + description).str.lower()

    # Fehlende Spalten mit Defaults füllen
    if "country" not in df.columns:
        df["country"] = "CH"
    if "canton" not in df.columns:
        df["canton"] = "unknown"
    if "process_type" not in df.columns:
        df["process_type"] = "open"
    if "project_type" not in df.columns:
        df["project_type"] = "unknown"

    # order_type bereinigen
    if "order_type" in df.columns:
        df["order_type"] = df["order_type"].fillna("unknown")
    else:
        df["order_type"] = "service"

    # Projekt-Wert extrahieren (award_amount)
    if "award_amount" in df.columns:
        df["project_value_chf"] = pd.to_numeric(df["award_amount"], errors='coerce')
    else:
        df["project_value_chf"] = np.nan

    return df


def train_order_type_classifier(df: pd.DataFrame):
    """Trainiert den Order-Type Klassifikator."""
    global _order_type_classifier

    if not SKLEARN_AVAILABLE:
        print("⚠️  sklearn nicht verfügbar - überspringe Training")
        return None

    print("\n--- Training Order-Type Klassifikator ---")

    if "order_type" not in df.columns or df["order_type"].isna().all():
        print("⚠️  Keine order_type Daten verfügbar - überspringe Training")
        return None

    # Filtere valide Daten
    df_valid = df[df["order_type"].notna() & (df["order_type"] != "unknown")]

    if len(df_valid) < 10:
        print("⚠️  Zu wenig Daten für Order-Type Training")
        return None

    y = df_valid["order_type"]
    X = df_valid[["text_attribute", "country", "canton", "process_type", "project_type"]].fillna("")

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

    if not SKLEARN_AVAILABLE:
        print("⚠️  sklearn nicht verfügbar - überspringe Training")
        return None

    print("\n--- Training Size-Bucket Klassifikator ---")

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

    if not SKLEARN_AVAILABLE:
        print("⚠️  sklearn nicht verfügbar - verwende Fallback")
        _model_trained = False
        return False

    print("=" * 60)
    print("SIMAP ML-Modell Training")
    print("=" * 60)

    df = load_training_data_from_supabase()

    if df.empty:
        print("⚠️  Keine Trainingsdaten verfügbar!")
        print("Verwende Fallback-Modell...")
        _model_trained = False
        return False

    df = prepare_features(df)
    print(f"\nVorbereitete Daten: {df.shape}")

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

    if not SKLEARN_AVAILABLE:
        return False

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
    Funktioniert mit beiden Datenformaten (Frontend und DB)
    """
    # Erstelle DataFrame mit einem Eintrag
    df = pd.DataFrame([{
        "title_de": data.get("titel") or data.get("title_de", ""),
        "description_de": data.get("beschreibung") or data.get("description_de", ""),
        "country": data.get("country", "CH"),
        "canton": data.get("canton", "unknown"),
        "process_type": data.get("process_type", "open"),
        "project_type": data.get("kategorie") or data.get("project_type", "unknown")
    }])

    df = prepare_features(df)

    result = {
        "relevanz": calculate_relevanz(data),
        "order_type": data.get("order_type", "service"),
        "size_bucket": "mittel"
    }

    # Vorhersagen mit ML-Modellen (falls trainiert)
    if _model_trained and _order_type_classifier and SKLEARN_AVAILABLE:
        try:
            features = df[["text_attribute", "country", "canton", "process_type", "project_type"]].fillna("")
            result["order_type"] = _order_type_classifier.predict(features)[0]
        except Exception as e:
            print(f"Order-Type Prediction Fehler: {e}")

    if _model_trained and _size_classifier and SKLEARN_AVAILABLE:
        try:
            features = df[["text_attribute", "country", "canton", "process_type", "project_type"]].fillna("")
            result["size_bucket"] = _size_classifier.predict(features)[0]
        except Exception as e:
            print(f"Size Prediction Fehler: {e}")

    return result


def calculate_relevanz(data: Dict) -> int:
    """
    Berechnet Relevanz-Score (0-100) für eine Ausschreibung
    Funktioniert mit beiden Datenformaten
    """
    score = 50  # Basis

    # Text-basierte Scores
    titel = (data.get("titel") or data.get("title_de") or "").lower()
    beschreibung = (data.get("beschreibung") or data.get("description_de") or "").lower()
    kategorie = (data.get("kategorie") or data.get("project_type") or "").lower()
    order_type = (data.get("order_type") or "").lower()

    # IT/Software Keywords
    it_keywords = ["it", "software", "digital", "entwicklung", "cloud", "system", "crm", "erp", "daten", "informatik"]
    for keyword in it_keywords:
        if keyword in titel:
            score += 15
        elif keyword in beschreibung:
            score += 5

    # Bau Keywords
    bau_keywords = ["bau", "sanierung", "renovation", "umbau", "neubau", "architektur", "planung"]
    for keyword in bau_keywords:
        if keyword in titel:
            score += 10
        elif keyword in beschreibung:
            score += 3

    # Order-Type Bonus
    if order_type == "service":
        score += 5
    elif order_type == "construction":
        score += 3

    # Kategorie-Bonus
    if "tender" in kategorie:
        score += 5

    # Projektgrösse (falls vorhanden)
    wert = data.get("wert") or data.get("award_amount") or ""
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

    if not SKLEARN_AVAILABLE:
        print("⚠️  sklearn nicht installiert - verwende Fallback-Relevanzberechnung")
        return False

    # Versuche Modelle zu laden
    if load_models():
        print("✅ Modelle erfolgreich geladen!")
        return True

    # Falls keine Modelle vorhanden, verwende Fallback
    print("\nKeine gespeicherten Modelle gefunden.")
    print("Verwende regelbasierte Relevanzberechnung als Fallback.")

    # Optional: Training starten (kann lange dauern)
    # success = train_models()
    # if success:
    #     save_models()

    return False


if __name__ == "__main__":
    initialize_ml_system()