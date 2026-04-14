"""
ProjektKlassifikator v5 — Monolith

Fixes gegenüber v4:
  1. Split-Before-Fit: TargetEncoder + PCA werden NUR auf Train-Daten gefittet
  2. 3-Way Split: Train (70%) / Calibration (15%) / Test (15%)
  3. Embeddings als Features: 384-dim → PCA 50-dim statt nur Similarity-Scores
  4. CV-Metriken ehrlich als 'uncalibrated' geloggt
  5. Seed-Evaluation auf Test-Split statt auf Trainingsdaten
  6. Alle Magic Numbers als Konstanten am Anfang
"""

import pandas as pd
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_predict
from sklearn.decomposition import PCA
from sklearn.metrics import (
    classification_report, precision_recall_curve, average_precision_score,
    f1_score, precision_score, recall_score, confusion_matrix, roc_auc_score
)
from sentence_transformers import SentenceTransformer
import joblib
import os
import re
import warnings
import sys
import tempfile
import html
from pathlib import Path
from dotenv import load_dotenv
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Set
import json

import dagshub
import mlflow
import mlflow.sklearn

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

env_path = PROJECT_ROOT / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()

sys.path.append(str(Path(__file__).parent / "ML"))
from supabase_api_loader import SupabaseAPILoader, lade_aus_supabase_api, teste_supabase_api
warnings.filterwarnings('ignore')


# =============================================================================
# KONFIGURATION (alle Magic Numbers zentral)
# =============================================================================

DAGSHUB_REPO_OWNER = os.getenv('DAGSHUB_REPO_OWNER', 'Saliousen79')
DAGSHUB_REPO_NAME = os.getenv('DAGSHUB_REPO_NAME', 'ML_SAJF')
MLFLOW_EXPERIMENT_NAME = os.getenv('MLFLOW_EXPERIMENT', 'ProjektKlassifikator')

# Embedding
EMBEDDING_MODEL_NAME = 'intfloat/multilingual-e5-small'
EMBEDDING_DIM = 384
EMBEDDING_BATCH_SIZE = 256

# Text
MAX_CHARS_TITLE = 1500
MAX_CHARS_DESCRIPTION = 1200

# Schema
REQUIRED_COLUMNS = {'title', 'description'}
OPTIONAL_ID_COLUMNS = {'id', 'simap_project_id', 'simap_publication_id'}

CATEGORICAL_FEATURES = [
    'publication_type', 'project_type', 'project_subtype',
    'canton', 'process_type', 'lots_type', 'order_type',
    'construction_type', 'construction_category', 'creation_language'
]

# Training — 3-Way Split
TRAIN_RATIO = 0.70
CALIBRATION_RATIO = 0.15
TEST_RATIO = 0.15

# GBM Defaults
GBM_LEARNING_RATE = 0.05
GBM_SUBSAMPLE = 0.8
GBM_EARLY_STOP_ROUNDS = 15
GBM_VALIDATION_FRACTION = 0.1

# Label Generation
ADAPTIVE_THRESHOLD_HIGH = 0.90
ADAPTIVE_THRESHOLD_LOW = 0.05
ADAPTIVE_FALLBACK_PERCENTILE = 70
FALLBACK_TOP_RATIO = 0.30
FALLBACK_BOTTOM_RATIO = 0.30
MIN_SAMPLES_PER_CLASS = 10
MIN_POSITIVE_RATIO = 0.05

# Features
EMBEDDING_PCA_COMPONENTS = 50
TARGET_ENCODER_SMOOTHING = 10.0

# Prediction
DEFAULT_MIN_PROBABILITY = 0.6
RECOMMENDATION_MIN_PROBABILITY = 0.7
SUPABASE_BATCH_SIZE = 50

# Ground Truth
GROUND_TRUTH_POSITIVE = set()
GROUND_TRUTH_NEGATIVE = set()
GROUND_TRUTH_WEIGHT = 3.0


def init_mlflow():
    try:
        dagshub.init(
            repo_owner=DAGSHUB_REPO_OWNER,
            repo_name=DAGSHUB_REPO_NAME,
            mlflow=True
        )
        mlflow.set_tracking_uri(
            f"https://dagshub.com/{DAGSHUB_REPO_OWNER}/{DAGSHUB_REPO_NAME}.mlflow"
        )
        mlflow.set_experiment(MLFLOW_EXPERIMENT_NAME)
        print(f"MLflow initialized: {DAGSHUB_REPO_OWNER}/{DAGSHUB_REPO_NAME}")
        return True
    except Exception as e:
        print(f"MLflow init failed: {e}")
        return False


# =============================================================================
# TEXT-NORMALISIERUNG
# =============================================================================

def normalisiere_text(text: str, max_chars: int = 1500) -> str:
    if not text or not isinstance(text, str):
        return ""
    text = html.unescape(text)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) > max_chars:
        text = text[:max_chars]
    return text


# =============================================================================
# ID MATCHING
# =============================================================================

def match_ids(df: pd.DataFrame, id_set: Set[str], debug: bool = False) -> pd.Series:
    """
    Robustes ID-Matching: normalisiert (lowercase, strip, führende Nullen entfernen)
    und sucht über mehrere ID-Spalten.
    """
    if not id_set:
        return pd.Series(False, index=df.index)

    normalized_set = set()
    for raw_id in id_set:
        stripped = str(raw_id).strip()
        norm = stripped.lower().lstrip('0') or '0'
        normalized_set.add(norm)
        normalized_set.add(stripped)

    mask = pd.Series(False, index=df.index)
    id_columns_found = []

    for col in ['id', 'simap_project_id', 'simap_publication_id']:
        if col not in df.columns:
            continue
        id_columns_found.append(col)

        col_str = df[col].astype(str).str.strip()
        exact_match = col_str.isin(id_set)
        col_normalized = col_str.str.lower().str.lstrip('0').replace('', '0')
        norm_match = col_normalized.isin(normalized_set)
        mask |= exact_match | norm_match

    if debug:
        print(f"\n  --- ID Matching Debug ---")
        print(f"  ID-Spalten: {id_columns_found}")
        print(f"  Gesuchte IDs ({len(id_set)}): {list(id_set)[:5]}...")
        for col in id_columns_found:
            sample = df[col].astype(str).head(5).tolist()
            print(f"  Beispiele '{col}': {sample}")
        n_matched = mask.sum()
        print(f"  Matches: {n_matched} / {len(id_set)}")

        if n_matched == 0 and id_columns_found:
            print(f"\n  ⚠ KEINE MATCHES! Substring-Suche...")
            for search_id in list(id_set)[:3]:
                for col in id_columns_found:
                    substr = df[col].astype(str).str.contains(
                        str(search_id).strip(), case=False, na=False
                    )
                    if substr.any():
                        examples = df.loc[substr, col].head(3).tolist()
                        print(f"  '{search_id}' Teilmatch in '{col}': {examples}")

    return mask


# =============================================================================
# GROUND TRUTH
# =============================================================================

def lade_ground_truth_aus_datei(pfad: str) -> Set[str]:
    ids = set()
    try:
        with open(pfad, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    ids.add(line)
        print(f"  {len(ids)} IDs aus {pfad} geladen")
    except FileNotFoundError:
        print(f"  Datei {pfad} nicht gefunden – übersprungen")
    return ids


def lade_ground_truth_aus_supabase() -> Tuple[Set[str], Set[str]]:
    import requests

    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_SERVICE_KEY') or os.getenv('SUPABASE_KEY')

    if not supabase_url or not supabase_key:
        return set(), set()

    headers = {
        'apikey': supabase_key,
        'Authorization': f'Bearer {supabase_key}'
    }

    positive, negative = set(), set()

    try:
        url = f"{supabase_url}/rest/v1/seed_labels?select=project_id,is_positive"
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            for row in response.json():
                pid = str(row['project_id'])
                if row['is_positive']:
                    positive.add(pid)
                else:
                    negative.add(pid)
            print(f"  Supabase: {len(positive)} positive, {len(negative)} negative Seeds")
        else:
            print(f"  seed_labels nicht erreichbar ({response.status_code})")
    except Exception as e:
        print(f"  Supabase seed_labels Fehler: {e}")

    return positive, negative


def sammle_ground_truth() -> Tuple[Set[str], Set[str]]:
    print("\n" + "=" * 60)
    print("GROUND TRUTH LADEN")
    print("=" * 60)

    positive = set(GROUND_TRUTH_POSITIVE)
    negative = set(GROUND_TRUTH_NEGATIVE)

    if positive or negative:
        print(f"  Code-Konstanten: {len(positive)} pos, {len(negative)} neg")

    pos_datei = Path(__file__).parent / "seeds_positive.txt"
    neg_datei = Path(__file__).parent / "seeds_negative.txt"
    positive |= lade_ground_truth_aus_datei(str(pos_datei))
    negative |= lade_ground_truth_aus_datei(str(neg_datei))

    sb_pos, sb_neg = lade_ground_truth_aus_supabase()
    positive |= sb_pos
    negative |= sb_neg

    konflikte = positive & negative
    if konflikte:
        print(f"  ⚠ {len(konflikte)} IDs in BEIDEN Listen – werden als POSITIV gewertet")
        negative -= konflikte

    print(f"\n  Total: {len(positive)} positive, {len(negative)} negative Ground Truth")
    return positive, negative


# =============================================================================
# ARCHIVDATEN NORMALISIERUNG
# =============================================================================

def normalisiere_archivdaten(df_archiv: pd.DataFrame) -> pd.DataFrame:
    df = df_archiv.copy()
    _contract_map = {'WORKS': 'construction', 'SERVICES': 'service', 'SUPPLIES': 'supply'}

    if 'xml_cont_name' in df.columns:
        fallback = (df.get('auth_name', pd.Series([''] * len(df), index=df.index)).fillna('')
                    + ' – '
                    + df.get('description', pd.Series([''] * len(df), index=df.index)).fillna('').str[:120])
        df['title'] = df['xml_cont_name'].replace('', None).fillna(fallback)
    elif 'auth_name' in df.columns:
        df['title'] = (df['auth_name'].fillna('')
                       + ' – '
                       + df.get('description', pd.Series([''] * len(df), index=df.index)).fillna('').str[:120])
    elif 'title' not in df.columns:
        df['title'] = ''

    if 'xml_cont_descr' in df.columns:
        df['description'] = df['xml_cont_descr'].replace('', None).fillna(
            df.get('description', pd.Series([''] * len(df), index=df.index)))
    elif 'description' not in df.columns:
        df['description'] = ''

    if 'cpv_code' not in df.columns:
        if 'xml_cpv' in df.columns:
            df['cpv_code'] = df['xml_cpv']
        elif 'cpv' in df.columns:
            df['cpv_code'] = df['cpv']

    if 'order_type' not in df.columns and 'contract_type' in df.columns:
        df['order_type'] = df['contract_type'].map(_contract_map).fillna(
            df['contract_type'].str.lower().fillna(''))

    if 'process_type' not in df.columns:
        src = 'xml_procedure' if 'xml_procedure' in df.columns else 'procedure'
        if src in df.columns:
            df['process_type'] = df[src]

    if 'publication_type' not in df.columns and 'pub_type' in df.columns:
        df['publication_type'] = df['pub_type']

    if 'simap_publication_id' not in df.columns and 'simap_id' in df.columns:
        df['simap_publication_id'] = df['simap_id'].astype(str)
    if 'simap_project_id' not in df.columns and 'project_id' in df.columns:
        df['simap_project_id'] = df['project_id'].astype(str)

    df['data_source'] = 'archiv'
    return df


# =============================================================================
# DATACLASS
# =============================================================================

@dataclass
class FilterKriterien:
    keywords_must: List[str] = field(default_factory=list)
    keywords_should: List[str] = field(default_factory=list)
    keywords_exclude: List[str] = field(default_factory=list)
    kantone: List[str] = field(default_factory=list)
    order_types: List[str] = field(default_factory=list)
    project_types: List[str] = field(default_factory=list)
    cpv_codes: List[str] = field(default_factory=list)
    min_budget: Optional[float] = None
    max_budget: Optional[float] = None
    semantic_threshold_must: float = 0.55
    semantic_threshold_should: float = 0.45
    semantic_threshold_exclude: float = 0.50

    seed_positive_ids: Set[str] = field(default_factory=set)
    seed_negative_ids: Set[str] = field(default_factory=set)
    seed_weight: float = GROUND_TRUTH_WEIGHT

    def to_mlflow_params(self) -> Dict[str, str]:
        return {
            'keywords_must': ', '.join(self.keywords_must),
            'keywords_should': ', '.join(self.keywords_should),
            'keywords_exclude': ', '.join(self.keywords_exclude),
            'kantone': ', '.join(self.kantone),
            'order_types': ', '.join(self.order_types),
            'project_types': ', '.join(self.project_types),
            'cpv_codes': ', '.join(self.cpv_codes),
            'min_budget': str(self.min_budget or ''),
            'max_budget': str(self.max_budget or ''),
            'threshold_must': str(self.semantic_threshold_must),
            'threshold_should': str(self.semantic_threshold_should),
            'threshold_exclude': str(self.semantic_threshold_exclude),
            'n_seed_positive': str(len(self.seed_positive_ids)),
            'n_seed_negative': str(len(self.seed_negative_ids)),
            'seed_weight': str(self.seed_weight),
        }


# =============================================================================
# TARGET ENCODER
# =============================================================================

class TargetEncoder:
    """
    Target Encoding mit Bayesian Smoothing.
    KRITISCH: fit() darf NUR auf Train-Daten aufgerufen werden!
    """

    def __init__(self, smoothing: float = TARGET_ENCODER_SMOOTHING):
        self.smoothing = smoothing
        self.encodings: Dict[str, Dict[str, float]] = {}
        self.global_means: Dict[str, float] = {}
        self._fitted = False

    def fit(self, df: pd.DataFrame, y: np.ndarray, columns: List[str]):
        if len(df) != len(y):
            raise ValueError(f"df ({len(df)}) und y ({len(y)}) haben unterschiedliche Länge")

        global_mean = y.mean()
        for col in columns:
            if col not in df.columns:
                continue
            col_data = df[col].fillna('__MISSING__').astype(str)
            self.global_means[col] = global_mean

            stats = pd.DataFrame({'target': y, 'category': col_data.values})
            agg = stats.groupby('category')['target'].agg(['mean', 'count'])

            encoding = {}
            for cat, row in agg.iterrows():
                smoothed = (
                    (row['count'] * row['mean'] + self.smoothing * global_mean)
                    / (row['count'] + self.smoothing)
                )
                encoding[cat] = smoothed
            self.encodings[col] = encoding

        self._fitted = True

    def transform(self, df: pd.DataFrame, columns: List[str]) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError("TargetEncoder.fit() muss vor transform() aufgerufen werden")

        result = []
        for col in columns:
            if col not in df.columns or col not in self.encodings:
                continue
            col_data = df[col].fillna('__MISSING__').astype(str)
            global_mean = self.global_means.get(col, 0.5)
            encoding = self.encodings[col]
            encoded = col_data.map(encoding).fillna(global_mean).values
            result.append(encoded.reshape(-1, 1))

        if not result:
            return np.zeros((len(df), 0))
        return np.hstack(result)


# =============================================================================
# FEATURE EXTRACTOR (NEU: PCA auf Embeddings)
# =============================================================================

class FeatureExtractor:
    """
    Feature-Extraktion mit sauberem fit/transform.

    Feature-Gruppen:
      1. PCA-reduzierte Dokument-Embeddings (384 → 50 dim)
      2. Semantische Similarity-Scores (ohne Label-Leakage)
      3. Target-encodierte kategorische Features

    fit() NUR auf Train-Daten! transform() auf beliebigen Daten.
    """

    def __init__(self, label_score_column: Optional[str] = None):
        self.label_score_column = label_score_column
        self._pca: Optional[PCA] = None
        self._target_encoder = TargetEncoder(smoothing=TARGET_ENCODER_SMOOTHING)
        self._feature_names: List[str] = []
        self._fitted = False

    def fit(self, df: pd.DataFrame, y: np.ndarray, embeddings: np.ndarray):
        """Fit PCA + TargetEncoder NUR auf Train-Daten."""
        if len(df) != len(y) or len(df) != len(embeddings):
            raise ValueError(
                f"Inkonsistente Längen: df={len(df)}, y={len(y)}, emb={len(embeddings)}")

        # PCA
        n_components = min(EMBEDDING_PCA_COMPONENTS, len(df) - 1, embeddings.shape[1])
        self._pca = PCA(n_components=n_components, random_state=42)
        self._pca.fit(embeddings)
        variance = self._pca.explained_variance_ratio_.sum()
        print(f"  PCA: {embeddings.shape[1]}-dim → {n_components}-dim "
              f"({variance:.1%} Varianz erklärt)")

        # Target Encoder
        available_cats = [c for c in CATEGORICAL_FEATURES if c in df.columns]
        self._target_encoder.fit(df, y, available_cats)
        print(f"  Target Encoder: {len(self._target_encoder.encodings)} kategorische Features")

        # Feature-Namen
        self._feature_names = []
        self._feature_names.extend([f"pca_{i}" for i in range(n_components)])

        semantic_cols = self._get_semantic_columns(df)
        self._feature_names.extend(semantic_cols)

        self._feature_names.extend([
            f"te_{c}" for c in available_cats if c in self._target_encoder.encodings
        ])

        self._fitted = True
        print(f"  Total Features: {len(self._feature_names)}")

    def transform(self, df: pd.DataFrame, embeddings: np.ndarray) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError("FeatureExtractor.fit() muss vor transform() aufgerufen werden")

        features = []

        # PCA Embeddings
        features.append(self._pca.transform(embeddings))

        # Semantische Scores (ohne Leakage)
        semantic_cols = self._get_semantic_columns(df)
        if semantic_cols:
            features.append(df[semantic_cols].fillna(0).values)

        # Kategorische Features
        available_cats = [c for c in CATEGORICAL_FEATURES if c in df.columns]
        cat_features = self._target_encoder.transform(df, available_cats)
        if cat_features.shape[1] > 0:
            features.append(cat_features)

        return np.hstack(features)

    def _get_semantic_columns(self, df: pd.DataFrame) -> List[str]:
        all_semantic = ['_must_max', '_must_mean', '_should_max', '_should_mean', '_exclude_max']
        excluded = set()
        if self.label_score_column:
            excluded.add(self.label_score_column)
            excluded.add(self.label_score_column.replace('_max', '_mean'))

        used = [col for col in all_semantic if col in df.columns and col not in excluded]
        if excluded & set(df.columns):
            print(f"  Leakage-Prevention: {excluded & set(df.columns)} ausgeschlossen")
        return used

    def get_state(self) -> dict:
        return {
            'pca': self._pca,
            'target_encoder': self._target_encoder,
            'feature_names': self._feature_names,
            'label_score_column': self.label_score_column,
            'fitted': self._fitted,
        }

    @classmethod
    def from_state(cls, state: dict) -> 'FeatureExtractor':
        obj = cls(label_score_column=state.get('label_score_column'))
        obj._pca = state['pca']
        obj._target_encoder = state['target_encoder']
        obj._feature_names = state['feature_names']
        obj._fitted = state.get('fitted', True)
        return obj


# =============================================================================
# HAUPTKLASSE
# =============================================================================

class ProjektKlassifikator:
    def __init__(self):
        print("Loading embedding model...")
        self.embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)

        import torch
        if torch.cuda.is_available():
            print("GPU detected")
            self.embedding_model = self.embedding_model.to('cuda')

        self.classifier = None
        self.feature_extractor: Optional[FeatureExtractor] = None
        self.kriterien_config = None
        self._kw_must_emb = None
        self._kw_should_emb = None
        self._kw_exclude_emb = None

    # =========================================================================
    # SCHEMA VALIDATION
    # =========================================================================
    def _validiere_schema(self, df: pd.DataFrame, context: str = ""):
        missing = REQUIRED_COLUMNS - set(df.columns)
        if missing:
            raise ValueError(
                f"Fehlende Pflichtspalten {context}: {missing}. "
                f"Vorhanden: {list(df.columns)[:20]}")

        available_ids = OPTIONAL_ID_COLUMNS & set(df.columns)
        if not available_ids:
            print(f"  ⚠ Keine ID-Spalte gefunden ({OPTIONAL_ID_COLUMNS})")

    # =========================================================================
    # KRITERIEN / EMBEDDINGS
    # =========================================================================
    def set_kriterien(self, kriterien: FilterKriterien):
        self.kriterien_config = kriterien
        print("\nPrecomputing keyword embeddings...")

        if kriterien.keywords_must:
            prefixed = [f"query: {kw}" for kw in kriterien.keywords_must]
            self._kw_must_emb = self.embedding_model.encode(
                prefixed, convert_to_numpy=True, normalize_embeddings=True)
            print(f"  MUST: {len(kriterien.keywords_must)} keywords")

        if kriterien.keywords_should:
            prefixed = [f"query: {kw}" for kw in kriterien.keywords_should]
            self._kw_should_emb = self.embedding_model.encode(
                prefixed, convert_to_numpy=True, normalize_embeddings=True)
            print(f"  SHOULD: {len(kriterien.keywords_should)} keywords")

        if kriterien.keywords_exclude:
            prefixed = [f"query: {kw}" for kw in kriterien.keywords_exclude]
            self._kw_exclude_emb = self.embedding_model.encode(
                prefixed, convert_to_numpy=True, normalize_embeddings=True)
            print(f"  EXCLUDE: {len(kriterien.keywords_exclude)} keywords")

        n_pos = len(kriterien.seed_positive_ids)
        n_neg = len(kriterien.seed_negative_ids)
        if n_pos or n_neg:
            print(f"  SEEDS: {n_pos} positive, {n_neg} negative (weight={kriterien.seed_weight}x)")

    # =========================================================================
    # DATEN VORBEREITEN
    # =========================================================================
    def daten_vorbereiten(self, df):
        df = df.copy()
        self._validiere_schema(df, context="daten_vorbereiten")

        df['title'] = df['title'].fillna('').apply(
            lambda x: normalisiere_text(x, max_chars=MAX_CHARS_TITLE))
        df['description'] = df['description'].fillna('').apply(
            lambda x: normalisiere_text(x, max_chars=MAX_CHARS_DESCRIPTION))

        df['combined_text'] = df['title'] + ' ' + df['title'] + ' ' + df['description']

        for col in CATEGORICAL_FEATURES:
            if col in df.columns:
                df[col] = df[col].fillna('unknown').astype(str)

        return df

    # =========================================================================
    # EMBEDDINGS
    # =========================================================================
    def _berechne_embeddings(self, df: pd.DataFrame) -> np.ndarray:
        texts = [f"passage: {t}" for t in df['combined_text'].tolist()]
        print(f"Computing embeddings for {len(texts)} texts...")
        return self.embedding_model.encode(
            texts, convert_to_numpy=True, normalize_embeddings=True,
            batch_size=EMBEDDING_BATCH_SIZE, show_progress_bar=True)

    # =========================================================================
    # HARTE FILTER
    # =========================================================================
    def wende_harte_filter_an(self, df):
        if self.kriterien_config is None:
            return df

        print("\n" + "=" * 60)
        print("HARD FILTERS")
        print("=" * 60)

        filtered = df.copy()
        original = len(filtered)
        kriterien = self.kriterien_config

        seed_ids = kriterien.seed_positive_ids | kriterien.seed_negative_ids
        seed_mask = match_ids(filtered, seed_ids) if seed_ids else pd.Series(
            False, index=filtered.index)

        if kriterien.order_types and 'order_type' in filtered.columns:
            before = len(filtered)
            order_types_lower = [ot.lower() for ot in kriterien.order_types]
            type_mask = filtered['order_type'].str.lower().isin(order_types_lower)
            filtered = filtered[type_mask | seed_mask.loc[filtered.index]]
            seed_mask = seed_mask.loc[filtered.index]
            print(f"Order Type: {before} -> {len(filtered)}")

        if kriterien.kantone and 'canton' in filtered.columns:
            before = len(filtered)
            kantone_upper = [k.upper() for k in kriterien.kantone]
            canton_mask = filtered['canton'].str.upper().isin(kantone_upper)
            filtered = filtered[canton_mask | seed_mask.loc[filtered.index]]
            seed_mask = seed_mask.loc[filtered.index]
            print(f"Canton: {before} -> {len(filtered)}")

        if kriterien.project_types and 'project_type' in filtered.columns:
            before = len(filtered)
            pt_lower = [pt.lower() for pt in kriterien.project_types]
            pt_mask = filtered['project_type'].str.lower().isin(pt_lower)
            filtered = filtered[pt_mask | seed_mask.loc[filtered.index]]
            seed_mask = seed_mask.loc[filtered.index]
            print(f"Project Type: {before} -> {len(filtered)}")

        if kriterien.cpv_codes and 'cpv_code' in filtered.columns:
            before = len(filtered)
            cpv_mask = pd.Series(False, index=filtered.index)
            for prefix in kriterien.cpv_codes:
                cpv_mask |= filtered['cpv_code'].astype(str).str.startswith(str(prefix))
            filtered = filtered[cpv_mask | seed_mask.loc[filtered.index]]
            seed_mask = seed_mask.loc[filtered.index]
            print(f"CPV Code: {before} -> {len(filtered)}")

        if 'estimated_amount' in filtered.columns:
            if kriterien.min_budget:
                before = len(filtered)
                budget_mask = (
                    (filtered['estimated_amount'] >= kriterien.min_budget)
                    | filtered['estimated_amount'].isna())
                filtered = filtered[budget_mask | seed_mask.loc[filtered.index]]
                seed_mask = seed_mask.loc[filtered.index]
                print(f"Min Budget: {before} -> {len(filtered)}")

            if kriterien.max_budget:
                before = len(filtered)
                budget_mask = (
                    (filtered['estimated_amount'] <= kriterien.max_budget)
                    | filtered['estimated_amount'].isna())
                filtered = filtered[budget_mask | seed_mask.loc[filtered.index]]
                seed_mask = seed_mask.loc[filtered.index]
                print(f"Max Budget: {before} -> {len(filtered)}")

        print(f"\nHard Filter: {original} -> {len(filtered)} "
              f"({len(filtered) / original * 100:.1f}%)")
        return filtered

    # =========================================================================
    # SEMANTIC SCORING
    # =========================================================================
    def berechne_semantic_scores(self, df, embeddings):
        print("\n" + "=" * 60)
        print("SEMANTIC SCORING")
        print("=" * 60)

        df = df.copy()
        df['_must_max'] = 0.0
        df['_must_mean'] = 0.0
        df['_should_max'] = 0.0
        df['_should_mean'] = 0.0
        df['_exclude_max'] = 0.0

        if self._kw_must_emb is not None and len(self._kw_must_emb) > 0:
            sim = np.dot(embeddings, self._kw_must_emb.T)
            df['_must_max'] = np.max(sim, axis=1)
            df['_must_mean'] = np.mean(sim, axis=1)
            print(f"MUST: mean={df['_must_max'].mean():.3f}, std={df['_must_max'].std():.3f}")

        if self._kw_should_emb is not None and len(self._kw_should_emb) > 0:
            sim = np.dot(embeddings, self._kw_should_emb.T)
            df['_should_max'] = np.max(sim, axis=1)
            df['_should_mean'] = np.mean(sim, axis=1)
            print(f"SHOULD: mean={df['_should_max'].mean():.3f}")

        if self._kw_exclude_emb is not None and len(self._kw_exclude_emb) > 0:
            sim = np.dot(embeddings, self._kw_exclude_emb.T)
            df['_exclude_max'] = np.max(sim, axis=1)
            print(f"EXCLUDE: mean={df['_exclude_max'].mean():.3f}")

        return df

    # =========================================================================
    # LABEL GENERATION
    # =========================================================================
    def erstelle_labels(self, df):
        print("\n" + "=" * 60)
        print("LABEL GENERATION")
        print("=" * 60)

        kriterien = self.kriterien_config
        n = len(df)
        labels = np.zeros(n, dtype=int)
        weights = np.ones(n, dtype=float)

        seed_pos = kriterien.seed_positive_ids
        seed_neg = kriterien.seed_negative_ids
        has_seeds = len(seed_pos) > 0 or len(seed_neg) > 0

        seed_mask = pd.Series(False, index=df.index)
        n_seed_pos = 0
        n_seed_neg = 0

        # --- Phase 1: Seed Labels ---
        if has_seeds:
            pos_mask = match_ids(df, seed_pos)
            neg_mask = match_ids(df, seed_neg)

            if pos_mask.sum() == 0 and neg_mask.sum() == 0 and has_seeds:
                print("\n⚠ KEINE Seeds gematched! Debug...")
                if seed_pos:
                    match_ids(df, seed_pos, debug=True)
                if seed_neg:
                    match_ids(df, seed_neg, debug=True)

            for i, idx in enumerate(df.index):
                if pos_mask.loc[idx]:
                    labels[i] = 1
                    weights[i] = kriterien.seed_weight
                    seed_mask.loc[idx] = True
                    n_seed_pos += 1
                elif neg_mask.loc[idx]:
                    labels[i] = 0
                    weights[i] = kriterien.seed_weight
                    seed_mask.loc[idx] = True
                    n_seed_neg += 1

            print(f"Ground Truth Seeds:")
            print(f"  ✓ Positive matched: {n_seed_pos} / {len(seed_pos)}")
            print(f"  ✗ Negative matched: {n_seed_neg} / {len(seed_neg)}")

        # --- Phase 2: Score-Spalte + Adaptiver Threshold ---
        if len(kriterien.keywords_must) > 0:
            self._label_score_column = '_must_max'
            threshold = kriterien.semantic_threshold_must
        elif len(kriterien.keywords_should) > 0:
            self._label_score_column = '_should_max'
            threshold = kriterien.semantic_threshold_should
        else:
            if not has_seeds:
                raise ValueError("Weder Keywords noch Seeds angegeben")
            self._label_score_column = None
            threshold = 0.5

        # Adaptiver Threshold
        if self._label_score_column and self._label_score_column in df.columns:
            scores = df[self._label_score_column].values
            n_above = (scores >= threshold).sum()
            ratio_above = n_above / n

            if ratio_above > ADAPTIVE_THRESHOLD_HIGH:
                adaptive = np.median(scores)
                print(f"\n  ⚠ Fixer Threshold {threshold:.3f} nicht diskriminierend "
                      f"({ratio_above:.0%} darüber)")
                print(f"    → Adaptiver Threshold: {adaptive:.3f} (Median)")
                threshold = adaptive
            elif ratio_above < ADAPTIVE_THRESHOLD_LOW:
                adaptive = np.percentile(scores, ADAPTIVE_FALLBACK_PERCENTILE)
                print(f"\n  ⚠ Fixer Threshold {threshold:.3f} zu hoch "
                      f"(nur {ratio_above:.0%} darüber)")
                print(f"    → Adaptiver Threshold: {adaptive:.3f} "
                      f"({ADAPTIVE_FALLBACK_PERCENTILE}. Perzentil)")
                threshold = adaptive

        # --- Phase 3: Semantische POSITIVE Labels ---
        n_semantic_pos = 0
        if self._label_score_column and self._label_score_column in df.columns:
            for i, idx in enumerate(df.index):
                if seed_mask.loc[idx]:
                    continue
                if df.loc[idx, self._label_score_column] >= threshold:
                    labels[i] = 1
                    n_semantic_pos += 1

        print(f"\nSemantische Positive: {n_semantic_pos} (threshold={threshold:.3f})")

        # --- Phase 4: Exclude ---
        n_excluded = 0
        if '_exclude_max' in df.columns:
            for i, idx in enumerate(df.index):
                if seed_mask.loc[idx]:
                    continue
                exclude_score = df.loc[idx, '_exclude_max']
                pos_score = 0.0
                if self._label_score_column and self._label_score_column in df.columns:
                    pos_score = df.loc[idx, self._label_score_column]
                if (exclude_score >= kriterien.semantic_threshold_exclude
                        and exclude_score > pos_score):
                    labels[i] = 0
                    n_excluded += 1

        print(f"Excluded: {n_excluded}")

        # --- Statistiken ---
        n_positive = labels.sum()
        n_negative = n - n_positive
        print(f"\nLabel-Verteilung:")
        print(f"  Positiv: {n_positive} ({n_positive / n * 100:.1f}%)")
        print(f"  Negativ: {n_negative} ({n_negative / n * 100:.1f}%)")

        if self._label_score_column:
            print(f"\n  Label-Score '{self._label_score_column}' wird aus Features AUSGESCHLOSSEN")

        # --- Guard: Degenerate Labels ---
        min_required = max(MIN_SAMPLES_PER_CLASS, int(n * MIN_POSITIVE_RATIO))
        if n_positive < min_required or n_negative < min_required:
            print(f"\n⚠ Label-Verteilung degeneriert! (min benötigt: {min_required})")

            if self._label_score_column and self._label_score_column in df.columns:
                scores = df[self._label_score_column].values
                print(f"  → Fallback: Top-{FALLBACK_TOP_RATIO:.0%} = Positiv")
                sorted_idx = np.argsort(scores)
                high_cutoff = int(n * (1 - FALLBACK_TOP_RATIO))
                labels = np.zeros(n, dtype=int)
                labels[sorted_idx[high_cutoff:]] = 1

                for i, idx in enumerate(df.index):
                    if seed_mask.loc[idx]:
                        if match_ids(df.iloc[i:i + 1], seed_pos).any():
                            labels[i] = 1
                        else:
                            labels[i] = 0

                print(f"  Adjusted: {labels.sum()} pos, {n - labels.sum()} neg")
            else:
                print(f"  → Fallback: Random Split")
                rng = np.random.RandomState(42)
                labels = (rng.rand(n) > (1 - FALLBACK_TOP_RATIO)).astype(int)
                for i, idx in enumerate(df.index):
                    if seed_mask.loc[idx]:
                        if match_ids(df.iloc[i:i + 1], seed_pos).any():
                            labels[i] = 1
                        else:
                            labels[i] = 0

        self._sample_weights = weights
        self._seed_mask = seed_mask
        return labels

    # =========================================================================
    # TRAINING (FIX: Split-Before-Fit + 3-Way Split)
    # =========================================================================
    def trainieren(self, df, labels, embeddings, model_name=None, model_version="v1.0"):
        """
        Korrekte Training-Pipeline:
          1. 3-Way Stratified Split → Train / Cal / Test
          2. FeatureExtractor.fit() NUR auf Train
          3. GBM fit auf Train
          4. CalibratedClassifierCV(prefit) auf Cal
          5. Evaluation auf unberührtem Test
        """
        print("\n" + "=" * 60)
        print("TRAINING (Split-Before-Fit)")
        print("=" * 60)

        n = len(df)
        y = labels
        sw = self._sample_weights

        # Guard
        if len(np.unique(y)) < 2:
            raise ValueError(
                f"Training braucht 2 Klassen, hat nur {len(np.unique(y))}. "
                f"Seeds/Keywords/Thresholds prüfen.")

        # =====================================================================
        # 1. 3-Way Split: Train / Cal / Test
        # =====================================================================
        indices = np.arange(n)

        # Split 1: Trenne Test ab
        idx_trainval, idx_test, y_trainval, y_test, w_trainval, w_test = train_test_split(
            indices, y, sw, test_size=TEST_RATIO, random_state=42, stratify=y)

        # Split 2: Trenne Cal von Train
        cal_fraction = CALIBRATION_RATIO / (TRAIN_RATIO + CALIBRATION_RATIO)
        idx_train, idx_cal, y_train, y_cal, w_train, w_cal = train_test_split(
            idx_trainval, y_trainval, w_trainval,
            test_size=cal_fraction, random_state=42, stratify=y_trainval)

        print(f"Split: Train={len(idx_train)}, Cal={len(idx_cal)}, Test={len(idx_test)}")
        print(f"Train positives: {y_train.sum()} ({y_train.mean() * 100:.1f}%)")

        for name, y_split in [("Train", y_train), ("Cal", y_cal), ("Test", y_test)]:
            if len(np.unique(y_split)) < 2:
                raise ValueError(f"{name}-Split hat nur {len(np.unique(y_split))} Klasse(n)")

        # =====================================================================
        # 2. FeatureExtractor.fit() NUR auf Train
        # =====================================================================
        df_train = df.iloc[idx_train].reset_index(drop=True)
        emb_train = embeddings[idx_train]

        label_score_col = getattr(self, '_label_score_column', None)
        self.feature_extractor = FeatureExtractor(label_score_column=label_score_col)
        self.feature_extractor.fit(df_train, y_train, emb_train)

        # =====================================================================
        # 3. Transform alle Splits
        # =====================================================================
        X_train = self.feature_extractor.transform(df_train, emb_train)

        df_cal = df.iloc[idx_cal].reset_index(drop=True)
        X_cal = self.feature_extractor.transform(df_cal, embeddings[idx_cal])

        df_test = df.iloc[idx_test].reset_index(drop=True)
        X_test = self.feature_extractor.transform(df_test, embeddings[idx_test])

        print(f"Features: {X_train.shape[1]}")

        # =====================================================================
        # 4. GBM fit auf Train
        # =====================================================================
        n_train = len(X_train)
        gb_params = {
            'n_estimators': min(300, max(50, n_train // 3)),
            'max_depth': 3 if n_train < 500 else (4 if n_train < 2000 else 5),
            'min_samples_split': max(5, n_train // 50),
            'min_samples_leaf': max(3, n_train // 100),
            'subsample': GBM_SUBSAMPLE,
            'learning_rate': GBM_LEARNING_RATE,
            'validation_fraction': GBM_VALIDATION_FRACTION,
            'n_iter_no_change': GBM_EARLY_STOP_ROUNDS,
        }

        print(f"GBM: n_est={gb_params['n_estimators']}, depth={gb_params['max_depth']}")

        base_clf = GradientBoostingClassifier(**gb_params, random_state=42)

        has_weighted = (w_train > 1.0).any()
        if has_weighted:
            base_clf.fit(X_train, y_train, sample_weight=w_train)
            print(f"Seed-weighted samples: {(w_train > 1.0).sum()}")
        else:
            base_clf.fit(X_train, y_train)

        # =====================================================================
        # 5. Kalibrierung auf Cal-Split (prefit)
        # =====================================================================
        n_cal = len(X_cal)
        if n_cal >= 30:
            cal_method = 'isotonic' if n_cal >= 200 else 'sigmoid'
            print(f"Calibration: {cal_method} on {n_cal} samples (prefit)")
            self.classifier = CalibratedClassifierCV(
                estimator=base_clf, method=cal_method, cv='prefit')
            self.classifier.fit(X_cal, y_cal)
        else:
            print(f"⚠ Cal-Split zu klein ({n_cal}) — keine Kalibrierung")
            self.classifier = base_clf

        # =====================================================================
        # 6. Evaluation auf Test
        # =====================================================================
        y_pred = self.classifier.predict(X_test)
        y_prob = self.classifier.predict_proba(X_test)[:, 1]

        accuracy = (y_pred == y_test).mean()
        f1 = f1_score(y_test, y_pred, average='binary')
        prec = precision_score(y_test, y_pred, average='binary', zero_division=0)
        rec = recall_score(y_test, y_pred, average='binary', zero_division=0)
        cm = confusion_matrix(y_test, y_pred)
        ap = average_precision_score(y_test, y_prob)

        precision_arr, recall_arr, thresholds = precision_recall_curve(y_test, y_prob)
        f1_arr = 2 * (precision_arr * recall_arr) / (precision_arr + recall_arr + 1e-8)
        optimal_idx = np.argmax(f1_arr[:-1])
        optimal_threshold = thresholds[optimal_idx] if len(thresholds) > 0 else 0.5

        report_text = classification_report(
            y_test, y_pred, target_names=['Not interesting', 'Interesting'])

        print(f"\nClassification Report (Holdout Test):")
        print(report_text)
        print(f"Average Precision: {ap:.3f}")
        print(f"Optimal threshold: {optimal_threshold:.3f}")

        # =====================================================================
        # 7. CV auf Train (uncalibrated — ehrlich geloggt)
        # =====================================================================
        cv_scores = {}
        print("\n--- Cross-Validation (uncalibrated GBM) ---")
        try:
            n_folds = min(5, max(2, n_train // 30))
            skf = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=42)
            cv_probs = cross_val_predict(
                GradientBoostingClassifier(**gb_params, random_state=42),
                X_train, y_train, cv=skf, method='predict_proba',
                fit_params={'sample_weight': w_train} if has_weighted else {}
            )[:, 1]
            cv_preds = (cv_probs >= 0.5).astype(int)

            cv_scores['cv_accuracy_uncalibrated'] = (cv_preds == y_train).mean()
            cv_scores['cv_f1_uncalibrated'] = f1_score(y_train, cv_preds, average='binary')
            cv_scores['cv_precision_uncalibrated'] = precision_score(
                y_train, cv_preds, average='binary', zero_division=0)
            cv_scores['cv_recall_uncalibrated'] = recall_score(
                y_train, cv_preds, average='binary', zero_division=0)
            if len(np.unique(y_train)) == 2:
                cv_scores['cv_auc_uncalibrated'] = roc_auc_score(y_train, cv_probs)

            for name, val in cv_scores.items():
                print(f"  {name}: {val:.4f}")
        except Exception as e:
            print(f"  CV failed: {e}")

        # =====================================================================
        # 8. Seed Performance auf TEST (nicht Train!)
        # =====================================================================
        seed_accuracy = None
        if hasattr(self, '_seed_mask') and self._seed_mask is not None:
            seed_in_test = []
            for i, orig_idx in enumerate(idx_test):
                if self._seed_mask.iloc[orig_idx]:
                    seed_in_test.append(i)

            if seed_in_test:
                y_seeds = y_test[seed_in_test]
                y_pred_seeds = y_pred[seed_in_test]
                seed_accuracy = (y_pred_seeds == y_seeds).mean()
                print(f"\n--- Seed Performance (Test-Split) ---")
                print(f"Seeds im Test: {len(seed_in_test)}, "
                      f"Korrekt: {(y_pred_seeds == y_seeds).sum()}/{len(seed_in_test)} "
                      f"({seed_accuracy:.1%})")
            else:
                print(f"\n  Keine Seeds im Test-Split")

        # =====================================================================
        # MLFLOW
        # =====================================================================
        try:
            run_name = f"{model_name or 'model'}_{model_version}"
            with mlflow.start_run(run_name=run_name):

                for pname, pval in gb_params.items():
                    mlflow.log_param(f"gb_{pname}", pval)

                mlflow.log_param("calibrated", True)
                mlflow.log_param("split_strategy", "3-way (train/cal/test)")
                mlflow.log_param("embedding_model", EMBEDDING_MODEL_NAME)
                mlflow.log_param("pca_components", EMBEDDING_PCA_COMPONENTS)
                mlflow.log_param("feature_encoding", "target_encoding")
                mlflow.log_param("split_before_fit", True)
                mlflow.log_param("test_size", TEST_RATIO)
                mlflow.log_param("cal_size", CALIBRATION_RATIO)

                if self._label_score_column:
                    mlflow.log_param("excluded_label_feature", self._label_score_column)

                if self.kriterien_config:
                    for k, v in self.kriterien_config.to_mlflow_params().items():
                        mlflow.log_param(f"filter_{k}", (v or "")[:500])

                mlflow.log_param("total_projects", len(df))
                mlflow.log_param("training_samples", len(X_train))
                mlflow.log_param("calibration_samples", len(X_cal))
                mlflow.log_param("test_samples", len(X_test))
                mlflow.log_param("n_features", X_train.shape[1])
                mlflow.log_param("feature_names",
                                 ', '.join(self.feature_extractor._feature_names)[:500])
                mlflow.log_param("model_name", model_name or "unnamed")
                mlflow.log_param("model_version", model_version)

                mlflow.log_metric("accuracy", accuracy)
                mlflow.log_metric("f1_score", f1)
                mlflow.log_metric("precision", prec)
                mlflow.log_metric("recall", rec)
                mlflow.log_metric("average_precision", ap)
                mlflow.log_metric("optimal_threshold", optimal_threshold)

                for name, val in cv_scores.items():
                    mlflow.log_metric(name, val)

                mlflow.log_metric("true_negatives", int(cm[0, 0]))
                mlflow.log_metric("false_positives", int(cm[0, 1]))
                mlflow.log_metric("false_negatives", int(cm[1, 0]))
                mlflow.log_metric("true_positives", int(cm[1, 1]))

                if seed_accuracy is not None:
                    mlflow.log_metric("seed_accuracy_test", seed_accuracy)

                n_seeds = 0
                if self.kriterien_config:
                    n_seeds = (len(self.kriterien_config.seed_positive_ids)
                               + len(self.kriterien_config.seed_negative_ids))
                mlflow.log_metric("n_seeds_total", n_seeds)
                mlflow.log_metric("n_positive_labels", int(y.sum()))
                mlflow.log_metric("n_negative_labels", int(len(y) - y.sum()))

                with tempfile.TemporaryDirectory() as tmpdir:
                    rpath = os.path.join(tmpdir, "classification_report.txt")
                    with open(rpath, 'w') as f:
                        f.write(f"Model: {model_name} {model_version}\n{'=' * 60}\n\n")
                        f.write(report_text)
                        f.write(f"\n\nAccuracy: {accuracy:.4f}\nF1: {f1:.4f}")
                        f.write(f"\nAverage Precision: {ap:.4f}")
                        if seed_accuracy is not None:
                            f.write(f"\nSeed Accuracy (Test): {seed_accuracy:.4f}")
                        f.write(f"\n\n--- CV Scores (uncalibrated GBM) ---\n")
                        for name, val in cv_scores.items():
                            f.write(f"{name}: {val:.4f}\n")
                    mlflow.log_artifact(rpath)

                    if self.kriterien_config:
                        kpath = os.path.join(tmpdir, "kriterien.json")
                        kdict = self.kriterien_config.to_mlflow_params()
                        kdict['seed_positive_ids'] = list(
                            self.kriterien_config.seed_positive_ids)
                        kdict['seed_negative_ids'] = list(
                            self.kriterien_config.seed_negative_ids)
                        with open(kpath, 'w') as f:
                            json.dump(kdict, f, indent=2, ensure_ascii=False)
                        mlflow.log_artifact(kpath)

                    prpath = os.path.join(tmpdir, "precision_recall_curve.csv")
                    pd.DataFrame({
                        'threshold': list(thresholds) + [1.0],
                        'precision': precision_arr,
                        'recall': recall_arr,
                        'f1': f1_arr
                    }).to_csv(prpath, index=False)
                    mlflow.log_artifact(prpath)

                mlflow.sklearn.log_model(
                    self.classifier, "classifier",
                    registered_model_name=f"ProjektKlassifikator-{model_name or 'default'}")

                mlflow.set_tag("model_type", "GradientBoosting")
                mlflow.set_tag("pipeline", "ProjektKlassifikator_v5")
                mlflow.set_tag("has_seeds", str(n_seeds > 0))
                mlflow.set_tag("split_before_fit", "true")
                mlflow.set_tag("uses_embedding_features", "true")

                run_id = mlflow.active_run().info.run_id
                print(f"\n✓ MLflow Run: {run_id}")

        except Exception as e:
            print(f"\n⚠ MLflow failed: {e}")

        # Supabase
        if model_name:
            self.speichern(
                pfad=model_name, zu_supabase=True,
                model_version=model_version, accuracy=accuracy)
            self._erstelle_und_speichere_empfehlungen(
                df, embeddings, model_name, model_version)

        return accuracy

    # =========================================================================
    # VORHERSAGEN / FINDE INTERESSANTE
    # =========================================================================
    def vorhersagen(self, df):
        if self.classifier is None or self.feature_extractor is None:
            raise ValueError("Model not trained/loaded")

        df = self.daten_vorbereiten(df)
        embeddings = self._berechne_embeddings(df)
        df = self.berechne_semantic_scores(df, embeddings)
        X = self.feature_extractor.transform(df, embeddings)
        return self.classifier.predict(X), self.classifier.predict_proba(X)[:, 1]

    def finde_interessante(self, df, min_prob=DEFAULT_MIN_PROBABILITY, top_n=None):
        print("\n" + "=" * 60)
        print("FINDING INTERESTING PROJECTS")
        print("=" * 60)

        if self.classifier is None or self.feature_extractor is None:
            raise ValueError("Model not trained/loaded")

        df = self.daten_vorbereiten(df)
        df_filtered = self.wende_harte_filter_an(df)

        if len(df_filtered) == 0:
            print("No projects after filter")
            return pd.DataFrame()

        df_filtered = df_filtered.reset_index(drop=True)
        embeddings = self._berechne_embeddings(df_filtered)
        df_scored = self.berechne_semantic_scores(df_filtered, embeddings)

        X = self.feature_extractor.transform(df_scored, embeddings)
        probabilities = self.classifier.predict_proba(X)[:, 1]

        df_scored['interessant_wahrscheinlichkeit'] = probabilities
        df_scored['interessant_vorhersage'] = (probabilities >= min_prob).astype(int)

        result = df_scored[df_scored['interessant_wahrscheinlichkeit'] >= min_prob].copy()
        result = result.sort_values('interessant_wahrscheinlichkeit', ascending=False)

        if top_n:
            result = result.head(top_n)

        print(f"\nResult: {len(result)} projects >= {min_prob:.0%}")
        return result

    # =========================================================================
    # SPEICHERN / LADEN
    # =========================================================================
    def speichern(self, pfad, zu_supabase=False, bucket_name="ml_models",
                  model_version="v1.0", accuracy=None):
        if self.classifier is None:
            raise ValueError("No model to save")

        model_data = {
            'classifier': self.classifier,
            'feature_extractor_state': self.feature_extractor.get_state(),
            'kriterien_config': self.kriterien_config,
            'kw_must_emb': self._kw_must_emb,
            'kw_should_emb': self._kw_should_emb,
            'kw_exclude_emb': self._kw_exclude_emb,
            '_label_score_column': getattr(self, '_label_score_column', None),
            'pipeline_version': 'v5',
        }

        if zu_supabase:
            try:
                import requests
                import io
                from datetime import datetime

                buffer = io.BytesIO()
                joblib.dump(model_data, buffer)
                file_content = buffer.getvalue()

                supabase_url = os.getenv('SUPABASE_URL')
                supabase_key = (os.getenv('SUPABASE_SERVICE_KEY')
                                or os.getenv('SUPABASE_KEY'))

                if not supabase_url or not supabase_key:
                    print("SUPABASE credentials not found")
                    return

                storage_path = (f"models/{datetime.now().strftime('%Y-%m-%d')}/"
                                f"{Path(pfad).stem}_{model_version}.pkl")
                upload_url = (f"{supabase_url}/storage/v1/object/"
                              f"{bucket_name}/{storage_path}")

                headers = {
                    'apikey': supabase_key,
                    'Authorization': f'Bearer {supabase_key}',
                    'Content-Type': 'application/octet-stream',
                    'x-upsert': 'true'
                }

                response = requests.post(
                    upload_url, headers=headers, data=file_content, timeout=30)

                if response.status_code in [200, 201]:
                    print(f"Model saved: {storage_path}")
                    self._speichere_modell_metadaten(
                        Path(pfad).stem, model_version, storage_path, accuracy)
                else:
                    print(f"Upload error: {response.status_code}")

            except Exception as e:
                print(f"Error saving: {e}")

    def _speichere_modell_metadaten(self, model_name, model_version,
                                     storage_path, accuracy=None):
        try:
            import requests

            supabase_url = os.getenv('SUPABASE_URL')
            supabase_key = (os.getenv('SUPABASE_SERVICE_KEY')
                            or os.getenv('SUPABASE_KEY'))

            headers = {
                'apikey': supabase_key,
                'Authorization': f'Bearer {supabase_key}',
                'Content-Type': 'application/json',
                'Prefer': 'return=representation'
            }

            url = f"{supabase_url}/rest/v1/ml_modelle"

            kriterien_dict = None
            if self.kriterien_config:
                kriterien_dict = {
                    'keywords_must': self.kriterien_config.keywords_must,
                    'keywords_should': self.kriterien_config.keywords_should,
                    'keywords_exclude': self.kriterien_config.keywords_exclude,
                    'kantone': self.kriterien_config.kantone,
                    'order_types': self.kriterien_config.order_types,
                    'project_types': self.kriterien_config.project_types,
                    'cpv_codes': self.kriterien_config.cpv_codes
                }

            metadata = {
                'model_name': model_name,
                'model_version': model_version,
                'storage_path': storage_path,
                'accuracy': float(accuracy) if accuracy else None,
                'trained_with_projects': getattr(self, '_last_training_size', 0),
                'kriterien': kriterien_dict,
                'is_active': True
            }

            requests.patch(
                url + '?is_active=eq.true',
                headers=headers, json={'is_active': False}, timeout=10)

            response = requests.post(url, headers=headers, json=metadata, timeout=10)

            if response.status_code in [200, 201]:
                print("Metadata saved")
                result = response.json()
                if isinstance(result, list) and len(result) > 0:
                    self._current_model_id = result[0].get('id')
            else:
                print(f"⚠ Metadata: {response.status_code}")

        except Exception as e:
            print(f"Metadata error: {e}")

    # =========================================================================
    # EMPFEHLUNGEN
    # =========================================================================
    def _erstelle_und_speichere_empfehlungen(self, df, embeddings,
                                              model_name, model_version):
        try:
            import requests
            from datetime import datetime

            df_scored = self.berechne_semantic_scores(df.copy(), embeddings)
            X = self.feature_extractor.transform(df_scored, embeddings)
            predictions = self.classifier.predict(X)
            probabilities = self.classifier.predict_proba(X)[:, 1]

            df_emp = df.copy()
            df_emp['prediction'] = predictions
            df_emp['probability'] = probabilities
            df_emp = df_emp[df_emp['probability'] >= RECOMMENDATION_MIN_PROBABILITY]
            df_emp = df_emp.sort_values('probability', ascending=False)

            print(f"Found {len(df_emp)} recommendations")
            if len(df_emp) == 0:
                return

            supabase_url = os.getenv('SUPABASE_URL')
            supabase_key = (os.getenv('SUPABASE_SERVICE_KEY')
                            or os.getenv('SUPABASE_KEY'))
            if not supabase_url or not supabase_key:
                return

            headers = {
                'apikey': supabase_key,
                'Authorization': f'Bearer {supabase_key}',
                'Content-Type': 'application/json',
                'Prefer': 'return=representation'
            }

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            clean_name = re.sub(
                r'[^a-z0-9_]', '',
                model_name.replace('.pkl', '').replace(' ', '_').lower())[:20]
            clean_ver = re.sub(r'[^a-z0-9]', '', model_version.lower())[:5]
            table_name = f"emp_{clean_name}_{clean_ver}_{timestamp}"
            if table_name[0].isdigit():
                table_name = 'tbl_' + table_name

            if not self._erstelle_empfehlungs_tabelle(table_name):
                return

            url = f"{supabase_url}/rest/v1/{table_name}"
            rows = []
            for idx, row in df_emp.iterrows():
                rows.append({
                    'model_name': model_name,
                    'model_version': model_version,
                    'model_id': getattr(self, '_current_model_id', None),
                    'project_id': str(row.get('id', idx)),
                    'simap_project_id': (
                        str(row.get('simap_project_id', ''))
                        if pd.notna(row.get('simap_project_id')) else None),
                    'simap_publication_id': (
                        str(row.get('simap_publication_id', ''))
                        if pd.notna(row.get('simap_publication_id')) else None),
                    'title': str(row.get('title', ''))[:500],
                    'description': str(row.get('description', ''))[:1000],
                    'canton': str(row.get('canton', '')),
                    'project_type': str(row.get('project_type', '')),
                    'cpv_code': str(row.get('cpv_code', '')),
                    'publication_date': row.get('publication_date'),
                    'deadline': row.get('deadline'),
                    'probability': float(row['probability']),
                    'prediction': int(row['prediction']),
                    'created_at': datetime.now().isoformat()
                })

            stats = {'inserted': 0, 'errors': 0}
            for i in range(0, len(rows), SUPABASE_BATCH_SIZE):
                batch = rows[i:i + SUPABASE_BATCH_SIZE]
                try:
                    response = requests.post(
                        url, headers=headers, json=batch, timeout=30)
                    if response.status_code in [200, 201]:
                        stats['inserted'] += len(batch)
                    else:
                        stats['errors'] += len(batch)
                except Exception:
                    stats['errors'] += len(batch)

            print(f"Recommendations: {stats['inserted']} inserted, "
                  f"{stats['errors']} errors")

        except Exception as e:
            print(f"Error: {e}")

    def _erstelle_empfehlungs_tabelle(self, table_name):
        try:
            import requests
            supabase_url = os.getenv('SUPABASE_URL')
            supabase_key = (os.getenv('SUPABASE_SERVICE_KEY')
                            or os.getenv('SUPABASE_KEY'))
            headers = {
                'apikey': supabase_key,
                'Authorization': f'Bearer {supabase_key}',
                'Content-Type': 'application/json'
            }
            url = f"{supabase_url}/rest/v1/rpc/create_empfehlungen_table"
            response = requests.post(
                url, headers=headers, json={'table_name': table_name}, timeout=10)
            if response.status_code in [200, 201, 204]:
                print(f"Table {table_name} created")
                return True
            else:
                print(f"Table creation failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"Error: {e}")
            return False

    def laden(self, pfad, von_supabase=False, bucket_name="ml_models"):
        if von_supabase:
            try:
                import requests
                import io

                supabase_url = os.getenv('SUPABASE_URL')
                supabase_key = os.getenv('SUPABASE_KEY')
                download_url = (f"{supabase_url}/storage/v1/object/"
                                f"{bucket_name}/{pfad}")
                headers = {
                    'apikey': supabase_key,
                    'Authorization': f'Bearer {supabase_key}'
                }
                response = requests.get(download_url, headers=headers, timeout=30)
                if response.status_code != 200:
                    raise Exception(f"Download error: {response.status_code}")
                model_data = joblib.load(io.BytesIO(response.content))
            except Exception as e:
                print(f"Error loading: {e}")
                raise
        else:
            model_data = joblib.load(pfad)

        self.classifier = model_data['classifier']
        self.kriterien_config = model_data.get('kriterien_config')
        self._kw_must_emb = model_data.get('kw_must_emb')
        self._kw_should_emb = model_data.get('kw_should_emb')
        self._kw_exclude_emb = model_data.get('kw_exclude_emb')
        self._label_score_column = model_data.get('_label_score_column')

        # v5 Feature Extractor
        fe_state = model_data.get('feature_extractor_state')
        if fe_state:
            self.feature_extractor = FeatureExtractor.from_state(fe_state)
            print(f"Model loaded (v5, {len(fe_state.get('feature_names', []))} features)")
        else:
            # v4 backward compat — begrenzt
            print("⚠ v4 model detected — neu trainieren für volle v5 Features")
            self.feature_extractor = None

    def lade_daten_von_supabase(self, tage_zurueck=365, kantone=None,
                                 projekt_typen=None, auftrags_arten=None,
                                 limit=20000):
        print(f"\nLoading from Supabase (last {tage_zurueck} days)...")
        try:
            loader = SupabaseAPILoader()
            df = loader.lade_projekte(
                tage_zurueck=tage_zurueck, kantone=kantone,
                projekt_typen=projekt_typen, auftrags_arten=auftrags_arten,
                limit=limit)
            if len(df) > 0:
                print(f"{len(df)} projects loaded")
            return df
        except Exception as e:
            print(f"Error: {e}")
            return pd.DataFrame()

    def lade_archivdaten_von_supabase(self, table_name="simap_archiv",
                                       limit=10000):
        import requests

        print(f"\nLade Archivdaten aus '{table_name}'...")
        supabase_url = os.getenv('SUPABASE_URL')
        supabase_key = (os.getenv('SUPABASE_SERVICE_KEY')
                        or os.getenv('SUPABASE_KEY'))

        if not supabase_url or not supabase_key:
            print("  Keine Supabase-Credentials")
            return pd.DataFrame()

        headers = {
            'apikey': supabase_key,
            'Authorization': f'Bearer {supabase_key}',
            'Content-Type': 'application/json',
        }

        try:
            url = f"{supabase_url}/rest/v1/{table_name}"
            params = {'select': '*', 'limit': limit}
            response = requests.get(
                url, headers=headers, params=params, timeout=30)

            if response.status_code == 200:
                data = response.json()
                if not data:
                    print(f"  Tabelle '{table_name}' leer")
                    return pd.DataFrame()
                df_archiv = pd.DataFrame(data)
                df_norm = normalisiere_archivdaten(df_archiv)
                print(f"  {len(df_norm)} Archiv-Datensätze geladen")
                return df_norm
            else:
                print(f"  Fehler: {response.status_code}")
                return pd.DataFrame()
        except Exception as e:
            print(f"  Fehler: {e}")
            return pd.DataFrame()

    def lade_archivdaten_aus_csv(self, pfad):
        try:
            df_archiv = pd.read_csv(pfad, encoding='utf-8-sig')
            df_norm = normalisiere_archivdaten(df_archiv)
            print(f"  {len(df_norm)} Archiv-Datensätze aus {pfad}")
            return df_norm
        except Exception as e:
            print(f"  Fehler: {e}")
            return pd.DataFrame()

    def speichere_interessante_projekte_zu_supabase(self, df_interessant,
                                                      kriterien=None,
                                                      model_version="v1.0"):
        print(f"\nSaving {len(df_interessant)} projects...")
        if len(df_interessant) == 0:
            return {'inserted': 0, 'skipped': 0, 'errors': 0}

        try:
            import requests
            import json as json_lib
            from datetime import datetime

            supabase_url = os.getenv('SUPABASE_URL')
            supabase_key = (os.getenv('SUPABASE_SERVICE_KEY')
                            or os.getenv('SUPABASE_KEY'))

            headers = {
                'apikey': supabase_key,
                'Authorization': f'Bearer {supabase_key}',
                'Content-Type': 'application/json',
                'Prefer': 'return=representation,resolution=merge-duplicates'
            }

            url = f"{supabase_url}/rest/v1/interessante_projekte"
            stats = {'inserted': 0, 'skipped': 0, 'errors': 0}

            kriterien_dict = None
            if kriterien:
                kriterien_dict = {
                    'keywords_must': kriterien.keywords_must,
                    'keywords_should': kriterien.keywords_should,
                    'keywords_exclude': kriterien.keywords_exclude
                }

            batch = []
            for idx, row in df_interessant.iterrows():
                batch.append({
                    'project_id': str(row.get('id', idx)),
                    'simap_project_id': (
                        str(row.get('simap_project_id', ''))
                        if pd.notna(row.get('simap_project_id')) else None),
                    'simap_publication_id': (
                        str(row.get('simap_publication_id', ''))
                        if pd.notna(row.get('simap_publication_id')) else None),
                    'title': str(row.get('title', '')),
                    'title_de': str(row.get('title_de', row.get('title', ''))),
                    'title_fr': str(row.get('title_fr', '')),
                    'description': str(row.get('description', '')),
                    'description_de': str(row.get('description_de',
                                                   row.get('description', ''))),
                    'description_fr': str(row.get('description_fr', '')),
                    'canton': str(row.get('canton', '')),
                    'cpv_code': str(row.get('cpv_code', '')),
                    'cpv_code_main': str(row.get('cpv_code_main',
                                                  row.get('cpv_code', ''))),
                    'project_type': str(row.get('project_type', '')),
                    'publication_date': row.get('publication_date'),
                    'deadline': row.get('deadline'),
                    'submission_deadline': row.get('submission_deadline'),
                    'estimated_amount': (
                        float(row.get('estimated_amount', 0))
                        if pd.notna(row.get('estimated_amount')) else None),
                    'contract_value': (
                        float(row.get('contract_value', 0))
                        if pd.notna(row.get('contract_value')) else None),
                    'interessant_wahrscheinlichkeit': float(
                        row['interessant_wahrscheinlichkeit']),
                    'model_version': model_version,
                    'kriterien': (json_lib.dumps(kriterien_dict)
                                  if kriterien_dict else None),
                    'url': str(row.get('url', ''))
                })

            for i in range(0, len(batch), SUPABASE_BATCH_SIZE):
                chunk = batch[i:i + SUPABASE_BATCH_SIZE]
                try:
                    response = requests.post(
                        url, headers=headers, json=chunk, timeout=30)
                    if response.status_code in [200, 201]:
                        stats['inserted'] += len(chunk)
                    elif response.status_code == 409:
                        stats['skipped'] += len(chunk)
                    else:
                        stats['errors'] += len(chunk)
                except Exception:
                    stats['errors'] += len(chunk)

            print(f"Inserted: {stats['inserted']}, Skipped: {stats['skipped']}, "
                  f"Errors: {stats['errors']}")
            return stats

        except Exception as e:
            print(f"Error: {e}")
            return {'inserted': 0, 'skipped': 0, 'errors': len(df_interessant)}


# =============================================================================
# INTERAKTIVE EINGABE
# =============================================================================

def interaktive_kriterien_eingabe():
    print("\n" + "=" * 60)
    print("DEFINE CRITERIA")
    print("=" * 60)

    kriterien = FilterKriterien()

    print("\n--- POSITIVE IDs (Pflicht) ---")
    while True:
        pos_input = input("IDs oder Dateipfad: ").strip()
        if pos_input:
            if os.path.isfile(pos_input):
                kriterien.seed_positive_ids = lade_ground_truth_aus_datei(pos_input)
            else:
                kriterien.seed_positive_ids = {
                    x.strip() for x in pos_input.split(',') if x.strip()}
            if kriterien.seed_positive_ids:
                print(f"  ✓ {len(kriterien.seed_positive_ids)} positive Seeds")
                break
        print("  Mindestens eine positive ID nötig!")

    print("\n--- NEGATIVE IDs (Pflicht) ---")
    while True:
        neg_input = input("IDs oder Dateipfad: ").strip()
        if neg_input:
            if os.path.isfile(neg_input):
                kriterien.seed_negative_ids = lade_ground_truth_aus_datei(neg_input)
            else:
                kriterien.seed_negative_ids = {
                    x.strip() for x in neg_input.split(',') if x.strip()}
            if kriterien.seed_negative_ids:
                print(f"  ✓ {len(kriterien.seed_negative_ids)} negative Seeds")
                break
        print("  Mindestens eine negative ID nötig!")

    w = input(f"\nSeed-Gewichtung (1-10, Enter={GROUND_TRUTH_WEIGHT}): ").strip()
    kriterien.seed_weight = float(w) if w else GROUND_TRUTH_WEIGHT

    print("\n--- ORDER TYPES ---")
    print("Options: construction, service, supply")
    order_input = input("Order types: ").strip().lower()
    if order_input:
        kriterien.order_types = [o.strip() for o in order_input.split(',') if o.strip()]

    print("\n--- CPV CODES ---")
    cpv_input = input("CPV prefixes: ").strip()
    if cpv_input:
        kriterien.cpv_codes = [c.strip() for c in cpv_input.split(',') if c.strip()]

    print("\n--- MUST KEYWORDS ---")
    must_input = input("MUST keywords: ").strip()
    if must_input:
        kriterien.keywords_must = [k.strip() for k in must_input.split(',') if k.strip()]

    print("\n--- SHOULD KEYWORDS ---")
    should_input = input("SHOULD keywords: ").strip()
    if should_input:
        kriterien.keywords_should = [k.strip() for k in should_input.split(',') if k.strip()]

    print("\n--- EXCLUDE KEYWORDS ---")
    exclude_input = input("EXCLUDE keywords: ").strip()
    if exclude_input:
        kriterien.keywords_exclude = [k.strip() for k in exclude_input.split(',') if k.strip()]

    print("\n--- CANTONS ---")
    kantone = input("Cantons (ZH,BE,...): ").strip().upper()
    if kantone:
        kriterien.kantone = [k.strip() for k in kantone.split(',') if k.strip()]

    print("\n--- PROJECT TYPES ---")
    pt = input("Project types: ").strip().lower()
    if pt:
        kriterien.project_types = [p.strip() for p in pt.split(',') if p.strip()]

    print("\n--- BUDGET ---")
    mn = input("Min budget (CHF): ").strip()
    if mn:
        kriterien.min_budget = float(mn)
    mx = input("Max budget (CHF): ").strip()
    if mx:
        kriterien.max_budget = float(mx)

    print("\n--- THRESHOLDS ---")
    th = input("MUST threshold (Enter=0.55): ").strip()
    if th:
        kriterien.semantic_threshold_must = float(th)
    te = input("EXCLUDE threshold (Enter=0.50): ").strip()
    if te:
        kriterien.semantic_threshold_exclude = float(te)

    print("\n--- SUMMARY ---")
    print(f"Seeds: {len(kriterien.seed_positive_ids)} pos, "
          f"{len(kriterien.seed_negative_ids)} neg (w={kriterien.seed_weight}x)")
    print(f"Order: {kriterien.order_types}, CPV: {kriterien.cpv_codes}")
    print(f"MUST: {len(kriterien.keywords_must)}, "
          f"SHOULD: {len(kriterien.keywords_should)}, "
          f"EXCLUDE: {len(kriterien.keywords_exclude)}")

    return kriterien


def zeige_ergebnisse(df, max_anzahl=10):
    print("\n" + "=" * 60)
    print(f"TOP {min(max_anzahl, len(df))} RESULTS")
    print("=" * 60)

    for _, row in df.head(max_anzahl).iterrows():
        print(f"\n{'-' * 60}")
        print(f"Title: {row.get('title', 'N/A')}")
        print(f"Prob:  {row['interessant_wahrscheinlichkeit']:.1%}")
        details = []
        for col in ['canton', 'order_type', 'cpv_code']:
            if col in row and pd.notna(row[col]):
                details.append(f"{col}: {row[col]}")
        if details:
            print(" | ".join(details))


def main():
    print("=" * 60)
    print("PROJECT CLASSIFIER v5 (Split-Before-Fit + Embedding Features)")
    print("=" * 60)

    mlflow_ok = init_mlflow()
    if not mlflow_ok:
        print("⚠ Weiter ohne MLflow")

    print("\n1. Train new model")
    print("2. Load model and find projects")
    print("3. Exit")

    wahl = input("\nChoice (1-3): ").strip()
    if wahl == '3':
        return

    print("\nTesting Supabase...")
    if not teste_supabase_api():
        print("Supabase failed")
        return

    klass = ProjektKlassifikator()

    if wahl == '1':
        tage = input("Days for training (default 365): ").strip()
        tage_zurueck = int(tage) if tage else 365

        df = klass.lade_daten_von_supabase(tage_zurueck=tage_zurueck)
        if len(df) == 0:
            print("No data")
            return

        # --- Archivdaten ---
        print("\nArchivdaten einbinden?")
        print("  1. Ja, aus Supabase")
        print("  2. Ja, aus CSV")
        print("  3. Nein")
        archiv_wahl = input("Wahl (1-3, Enter=3): ").strip() or '3'

        if archiv_wahl == '1':
            archiv_table = input("Tabellenname (Enter=simap_archiv): ").strip() or 'simap_archiv'
            df_archiv = klass.lade_archivdaten_von_supabase(table_name=archiv_table)
            if len(df_archiv) > 0:
                df = pd.concat([df, df_archiv], ignore_index=True)
                print(f"  → Kombiniert: {len(df)} Datensätze")
        elif archiv_wahl == '2':
            csv_pfad = input("CSV-Pfad: ").strip()
            if csv_pfad:
                df_archiv = klass.lade_archivdaten_aus_csv(csv_pfad)
                if len(df_archiv) > 0:
                    df = pd.concat([df, df_archiv], ignore_index=True)
                    print(f"  → Kombiniert: {len(df)} Datensätze")

        # ID-Preview
        print("\n" + "=" * 60)
        print("VERFÜGBARE ID-SPALTEN")
        print("=" * 60)
        for col in ['id', 'simap_project_id', 'simap_publication_id']:
            if col in df.columns:
                non_null = df[col].dropna()
                if len(non_null) > 0:
                    examples = non_null.astype(str).head(5).tolist()
                    print(f"  {col}: {len(non_null)} Werte, z.B. {examples}")
        print(f"\n  → Verwende diese IDs als Seeds!")

        kriterien = interaktive_kriterien_eingabe()
        klass.set_kriterien(kriterien)

        # Prepare + Filter + Embed + Score + Label + Train
        df = klass.daten_vorbereiten(df)
        df = klass.wende_harte_filter_an(df)

        if len(df) < 50:
            print(f"Only {len(df)} projects – too few")
            return

        df = df.reset_index(drop=True)

        embeddings = klass._berechne_embeddings(df)
        df_scored = klass.berechne_semantic_scores(df, embeddings)
        labels = klass.erstelle_labels(df_scored)

        model_name = input("Model name (e.g. model.pkl): ").strip() or "model.pkl"
        if not model_name.endswith('.pkl'):
            model_name += '.pkl'
        model_version = input("Version (default v1.0): ").strip() or "v1.0"

        klass._last_training_size = len(df)
        klass.trainieren(
            df_scored, labels, embeddings,
            model_name=model_name, model_version=model_version)

        if input("\nSearch now? (y/n): ").strip().lower() not in ['y', 'j', 'ja', 'yes']:
            return

    elif wahl == '2':
        try:
            import requests
            supabase_url = os.getenv('SUPABASE_URL')
            supabase_key = os.getenv('SUPABASE_KEY')
            list_url = f"{supabase_url}/storage/v1/object/list/ml_models"
            headers = {
                'apikey': supabase_key,
                'Authorization': f'Bearer {supabase_key}'
            }
            response = requests.post(
                list_url, headers=headers, json={"limit": 100}, timeout=10)

            if response.status_code == 200:
                files = response.json()
                models = [f for f in files if f.get('name', '').endswith('.pkl')]
                if models:
                    print("\nModels:")
                    for i, f in enumerate(models, 1):
                        print(f"  [{i}] {f['name']}")
                    sel = input("\nNumber or name: ").strip()
                    if sel.isdigit() and 1 <= int(sel) <= len(models):
                        mname = models[int(sel) - 1]['name']
                    else:
                        mname = sel if sel.endswith('.pkl') else sel + '.pkl'
                    klass.laden(mname, von_supabase=True)
                else:
                    print("No models found")
                    return
            else:
                print("Error listing models")
                return
        except Exception as e:
            print(f"Error: {e}")
            return

    # --- Prediction ---
    tage = input("\nDays for prediction (default 30): ").strip()
    tage_zurueck = int(tage) if tage else 30

    df_pred = klass.lade_daten_von_supabase(tage_zurueck=tage_zurueck)

    if 'submission_deadline' in df_pred.columns:
        df_pred['submission_deadline'] = pd.to_datetime(
            df_pred['submission_deadline'], errors='coerce', utc=True)
        df_pred = df_pred[df_pred['submission_deadline'] >= pd.Timestamp.now(tz='UTC')]
        print(f"{len(df_pred)} projects with open deadline")

    min_prob = float(input("Min probability (default 0.6): ").strip() or 0.6)
    top_n_input = input("Max results (Enter=all): ").strip()
    top_n = int(top_n_input) if top_n_input else None

    interesting = klass.finde_interessante(df_pred, min_prob=min_prob, top_n=top_n)

    if len(interesting) > 0:
        zeige_ergebnisse(interesting)

        out = input("\nSave CSV: ").strip()
        if out:
            if not out.endswith('.csv'):
                out += '.csv'
            interesting.to_csv(out, sep='\t', index=False)
            print(f"Saved: {out}")

        if input("\nSave to Supabase? (y/n): ").strip().lower() in ['y', 'j']:
            klass.speichere_interessante_projekte_zu_supabase(
                interesting, kriterien=klass.kriterien_config)
    else:
        print("\nNo interesting projects found")


if __name__ == "__main__":
    main()