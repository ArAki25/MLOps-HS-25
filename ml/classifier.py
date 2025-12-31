import pandas as pd
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import classification_report, precision_recall_curve, average_precision_score
from sentence_transformers import SentenceTransformer
import joblib
import os
import warnings
import sys
from pathlib import Path
from dotenv import load_dotenv
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

env_path = PROJECT_ROOT / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()

sys.path.append(str(Path(__file__).parent / "algorithm"))
from supabase_api_loader import SupabaseAPILoader, lade_aus_supabase_api, teste_supabase_api
from supabase_storage_handler import SupabaseStorageHandler, lade_modell_von_storage, speichere_modell_zu_storage
warnings.filterwarnings('ignore')


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


class ProjektKlassifikator:
    def __init__(self):
        print("Loading embedding model...")
        self.embedding_model = SentenceTransformer('intfloat/multilingual-e5-small')

        import torch
        if torch.cuda.is_available():
            print("GPU detected")
            self.embedding_model = self.embedding_model.to('cuda')

        self.classifier = None
        self.label_encoders = {}
        self.kriterien_config = None
        self._kw_must_emb = None
        self._kw_should_emb = None
        self._kw_exclude_emb = None
        self._embedding_cache = {}

        self.categorical_features = [
            'publication_type', 'project_type', 'project_subtype',
            'canton', 'process_type', 'lots_type', 'order_type',
            'construction_type', 'construction_category', 'creation_language'
        ]

    def set_kriterien(self, kriterien: FilterKriterien):
        self.kriterien_config = kriterien
        print("\nPrecomputing keyword embeddings...")

        if kriterien.keywords_must:
            self._kw_must_emb = self.embedding_model.encode(
                kriterien.keywords_must,
                convert_to_numpy=True,
                normalize_embeddings=True
            )
            print(f"  MUST: {len(kriterien.keywords_must)} keywords")

        if kriterien.keywords_should:
            self._kw_should_emb = self.embedding_model.encode(
                kriterien.keywords_should,
                convert_to_numpy=True,
                normalize_embeddings=True
            )
            print(f"  SHOULD: {len(kriterien.keywords_should)} keywords")

        if kriterien.keywords_exclude:
            self._kw_exclude_emb = self.embedding_model.encode(
                kriterien.keywords_exclude,
                convert_to_numpy=True,
                normalize_embeddings=True
            )
            print(f"  EXCLUDE: {len(kriterien.keywords_exclude)} keywords")

    def daten_vorbereiten(self, df):
        df = df.copy()
        df['title'] = df['title'].fillna('')
        df['description'] = df['description'].fillna('')
        df['combined_text'] = df['title'] + ' ' + df['description']

        for col in self.categorical_features:
            if col in df.columns:
                df[col] = df[col].fillna('unknown').astype(str)

        return df

    def wende_harte_filter_an(self, df):
        if self.kriterien_config is None:
            return df

        print("\n" + "="*60)
        print("HARD FILTERS")
        print("="*60)

        filtered = df.copy()
        original = len(filtered)
        kriterien = self.kriterien_config

        if kriterien.order_types and 'order_type' in filtered.columns:
            before = len(filtered)
            order_types_lower = [ot.lower() for ot in kriterien.order_types]
            filtered = filtered[filtered['order_type'].str.lower().isin(order_types_lower)]
            print(f"Order Type: {before} -> {len(filtered)} (filter: {kriterien.order_types})")

        if kriterien.kantone and 'canton' in filtered.columns:
            before = len(filtered)
            kantone_upper = [k.upper() for k in kriterien.kantone]
            filtered = filtered[filtered['canton'].str.upper().isin(kantone_upper)]
            print(f"Canton: {before} -> {len(filtered)}")

        if kriterien.project_types and 'project_type' in filtered.columns:
            before = len(filtered)
            project_types_lower = [pt.lower() for pt in kriterien.project_types]
            filtered = filtered[filtered['project_type'].str.lower().isin(project_types_lower)]
            print(f"Project Type: {before} -> {len(filtered)}")

        if kriterien.cpv_codes and 'cpv_code' in filtered.columns:
            before = len(filtered)
            cpv_mask = pd.Series(False, index=filtered.index)
            for prefix in kriterien.cpv_codes:
                cpv_mask |= filtered['cpv_code'].astype(str).str.startswith(str(prefix))
            filtered = filtered[cpv_mask]
            print(f"CPV Code: {before} -> {len(filtered)}")

        if 'estimated_amount' in filtered.columns:
            if kriterien.min_budget:
                before = len(filtered)
                filtered = filtered[
                    (filtered['estimated_amount'] >= kriterien.min_budget) |
                    (filtered['estimated_amount'].isna())
                ]
                print(f"Min Budget: {before} -> {len(filtered)}")

            if kriterien.max_budget:
                before = len(filtered)
                filtered = filtered[
                    (filtered['estimated_amount'] <= kriterien.max_budget) |
                    (filtered['estimated_amount'].isna())
                ]
                print(f"Max Budget: {before} -> {len(filtered)}")

        print(f"\nHard Filter Result: {original} -> {len(filtered)} ({len(filtered)/original*100:.1f}%)")
        return filtered

    def berechne_semantic_scores(self, df):
        print("\n" + "="*60)
        print("SEMANTIC SCORING")
        print("="*60)

        df = df.copy()
        texts = df['combined_text'].tolist()

        print(f"Computing embeddings for {len(texts)} texts...")
        text_embeddings = self.embedding_model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            batch_size=256,
            show_progress_bar=True
        )

        df['_must_max'] = 0.0
        df['_must_mean'] = 0.0
        df['_should_max'] = 0.0
        df['_should_mean'] = 0.0
        df['_exclude_max'] = 0.0

        if self._kw_must_emb is not None and len(self._kw_must_emb) > 0:
            similarities = np.dot(text_embeddings, self._kw_must_emb.T)
            df['_must_max'] = np.max(similarities, axis=1)
            df['_must_mean'] = np.mean(similarities, axis=1)
            print(f"MUST scores: mean={df['_must_max'].mean():.3f}, std={df['_must_max'].std():.3f}")

        if self._kw_should_emb is not None and len(self._kw_should_emb) > 0:
            similarities = np.dot(text_embeddings, self._kw_should_emb.T)
            df['_should_max'] = np.max(similarities, axis=1)
            df['_should_mean'] = np.mean(similarities, axis=1)
            print(f"SHOULD scores: mean={df['_should_max'].mean():.3f}")

        if self._kw_exclude_emb is not None and len(self._kw_exclude_emb) > 0:
            similarities = np.dot(text_embeddings, self._kw_exclude_emb.T)
            df['_exclude_max'] = np.max(similarities, axis=1)
            print(f"EXCLUDE scores: mean={df['_exclude_max'].mean():.3f}")

        return df

    def erstelle_labels(self, df):
        print("\n" + "="*60)
        print("LABEL GENERATION")
        print("="*60)

        kriterien = self.kriterien_config
        labels = np.zeros(len(df), dtype=int)

        exclude_mask = df['_exclude_max'] >= kriterien.semantic_threshold_exclude
        n_excluded = exclude_mask.sum()
        print(f"Excluded by EXCLUDE keywords: {n_excluded}")

        if len(kriterien.keywords_must) > 0:
            positive_mask = (df['_must_max'] >= kriterien.semantic_threshold_must) & ~exclude_mask
        elif len(kriterien.keywords_should) > 0:
            positive_mask = (df['_should_max'] >= kriterien.semantic_threshold_should) & ~exclude_mask
        else:
            raise ValueError("Keywords required for label generation")

        labels[positive_mask] = 1

        n_positive = labels.sum()
        n_negative = len(labels) - n_positive

        print(f"Positive (interesting): {n_positive} ({n_positive/len(labels)*100:.1f}%)")
        print(f"Negative (not interesting): {n_negative} ({n_negative/len(labels)*100:.1f}%)")

        if n_positive < 10 or n_negative < 10:
            print("\nAuto-adjusting labels due to imbalance...")
            scores = df['_must_max'].values if len(kriterien.keywords_must) > 0 else df['_should_max'].values
            sorted_indices = np.argsort(scores)

            threshold_low = int(len(sorted_indices) * 0.3)
            threshold_high = int(len(sorted_indices) * 0.7)

            labels = np.zeros(len(df), dtype=int)
            labels[sorted_indices[threshold_high:]] = 1
            labels[sorted_indices[:threshold_low]] = 0

            for idx in sorted_indices[threshold_low:threshold_high]:
                if exclude_mask.iloc[idx]:
                    labels[idx] = 0

            n_positive = labels.sum()
            n_negative = len(labels) - n_positive
            print(f"Adjusted: {n_positive} positive, {n_negative} negative")

        return labels

    def erstelle_features(self, df, fit=True):
        features = []

        semantic_features = df[[
            '_must_max', '_must_mean',
            '_should_max', '_should_mean',
            '_exclude_max'
        ]].fillna(0).values
        features.append(semantic_features)

        interaction = (df['_must_max'] * (1 - df['_exclude_max'])).values.reshape(-1, 1)
        features.append(interaction)

        for col in self.categorical_features:
            if col not in df.columns:
                continue

            col_data = df[col].fillna('unknown').astype(str)

            if fit:
                le = LabelEncoder()
                le.fit(list(col_data.unique()) + ['unknown'])
                self.label_encoders[col] = le

            if col in self.label_encoders:
                le = self.label_encoders[col]
                encoded = []
                for val in col_data:
                    try:
                        encoded.append(le.transform([val])[0])
                    except ValueError:
                        encoded.append(le.transform(['unknown'])[0])

                n_classes = len(le.classes_)
                one_hot = np.zeros((len(df), n_classes))
                for i, val in enumerate(encoded):
                    one_hot[i, val] = 1
                features.append(one_hot)

        return np.hstack(features)

    def trainieren(self, df, labels, model_name=None, model_version="v1.0"):
        print("\n" + "="*60)
        print("TRAINING")
        print("="*60)

        df = self.daten_vorbereiten(df)
        X = self.erstelle_features(df, fit=True)
        y = labels

        self._last_training_size = len(df)
        self._training_df = df.copy()

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.15, random_state=42, stratify=y
        )

        print(f"Train: {len(X_train)}, Test: {len(X_test)}")
        print(f"Train positives: {y_train.sum()} ({y_train.mean()*100:.1f}%)")

        base_clf = GradientBoostingClassifier(
            n_estimators=150,
            max_depth=5,
            min_samples_split=10,
            min_samples_leaf=5,
            subsample=0.8,
            random_state=42,
            validation_fraction=0.1,
            n_iter_no_change=10
        )

        if len(X_train) > 100:
            print("Using calibrated classifier...")
            self.classifier = CalibratedClassifierCV(base_clf, method='isotonic', cv=3)
        else:
            self.classifier = base_clf

        self.classifier.fit(X_train, y_train)

        y_pred = self.classifier.predict(X_test)
        y_prob = self.classifier.predict_proba(X_test)[:, 1]

        print("\nClassification Report:")
        print(classification_report(y_test, y_pred, target_names=['Not interesting', 'Interesting']))

        precision, recall, thresholds = precision_recall_curve(y_test, y_prob)
        ap = average_precision_score(y_test, y_prob)
        print(f"Average Precision: {ap:.3f}")

        f1_scores = 2 * (precision * recall) / (precision + recall + 1e-8)
        optimal_idx = np.argmax(f1_scores[:-1])
        optimal_threshold = thresholds[optimal_idx]
        print(f"Optimal threshold: {optimal_threshold:.3f}")

        accuracy = (y_pred == y_test).mean()

        if model_name:
            self.speichern(
                pfad=model_name,
                zu_supabase=True,
                model_version=model_version,
                accuracy=accuracy
            )
            self._erstelle_und_speichere_empfehlungen(model_name, model_version)

        return accuracy

    def vorhersagen(self, df):
        if self.classifier is None:
            raise ValueError("Model must be trained or loaded first")

        df = self.daten_vorbereiten(df)
        df = self.berechne_semantic_scores(df)
        X = self.erstelle_features(df, fit=False)

        predictions = self.classifier.predict(X)
        probabilities = self.classifier.predict_proba(X)[:, 1]

        return predictions, probabilities

    def finde_interessante(self, df, min_prob=0.6, top_n=None):
        print("\n" + "="*60)
        print("FINDING INTERESTING PROJECTS")
        print("="*60)

        df = self.daten_vorbereiten(df)

        df_filtered = self.wende_harte_filter_an(df)

        if len(df_filtered) == 0:
            print("No projects after hard filter")
            return pd.DataFrame()

        df_scored = self.berechne_semantic_scores(df_filtered)

        X = self.erstelle_features(df_scored, fit=False)
        probabilities = self.classifier.predict_proba(X)[:, 1]

        df_scored['interessant_wahrscheinlichkeit'] = probabilities
        df_scored['interessant_vorhersage'] = (probabilities >= min_prob).astype(int)

        result = df_scored[df_scored['interessant_wahrscheinlichkeit'] >= min_prob].copy()
        result = result.sort_values('interessant_wahrscheinlichkeit', ascending=False)

        if top_n:
            result = result.head(top_n)

        print(f"\nResult: {len(result)} projects with probability >= {min_prob:.0%}")

        return result

    def speichern(self, pfad, zu_supabase=False, bucket_name="ml_models", model_version="v1.0", accuracy=None):
        if self.classifier is None:
            raise ValueError("No model to save")

        model_data = {
            'classifier': self.classifier,
            'label_encoders': self.label_encoders,
            'kriterien_config': self.kriterien_config,
            'kw_must_emb': self._kw_must_emb,
            'kw_should_emb': self._kw_should_emb,
            'kw_exclude_emb': self._kw_exclude_emb
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
                supabase_key = os.getenv('SUPABASE_SERVICE_KEY') or os.getenv('SUPABASE_KEY')

                if not supabase_url or not supabase_key:
                    print("SUPABASE credentials not found")
                    return

                storage_path = f"models/{datetime.now().strftime('%Y-%m-%d')}/{Path(pfad).stem}_{model_version}.pkl"
                upload_url = f"{supabase_url}/storage/v1/object/{bucket_name}/{storage_path}"

                headers = {
                    'apikey': supabase_key,
                    'Authorization': f'Bearer {supabase_key}',
                    'Content-Type': 'application/octet-stream',
                    'x-upsert': 'true'
                }

                response = requests.post(upload_url, headers=headers, data=file_content, timeout=30)

                if response.status_code in [200, 201]:
                    print(f"Model saved to Supabase: {storage_path}")
                    self._speichere_modell_metadaten(Path(pfad).stem, model_version, storage_path, accuracy)
                else:
                    print(f"Upload error: {response.status_code}")

            except Exception as e:
                print(f"Error saving to Supabase: {e}")

    def _speichere_modell_metadaten(self, model_name, model_version, storage_path, accuracy=None):
        try:
            import requests

            supabase_url = os.getenv('SUPABASE_URL')
            supabase_key = os.getenv('SUPABASE_SERVICE_KEY') or os.getenv('SUPABASE_KEY')

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
                headers=headers,
                json={'is_active': False},
                timeout=10
            )

            response = requests.post(url, headers=headers, json=metadata, timeout=10)

            if response.status_code in [200, 201]:
                print("Model metadata saved")
                result = response.json()
                if isinstance(result, list) and len(result) > 0:
                    self._current_model_id = result[0].get('id')

        except Exception as e:
            print(f"Error saving metadata: {e}")

    def _erstelle_und_speichere_empfehlungen(self, model_name, model_version):
        try:
            import requests
            from datetime import datetime
            import re

            if not hasattr(self, '_training_df') or self._training_df is None:
                return

            predictions, probabilities = self.vorhersagen(self._training_df)

            min_probability = 0.7
            df_empfehlungen = self._training_df.copy()
            df_empfehlungen['prediction'] = predictions
            df_empfehlungen['probability'] = probabilities
            df_empfehlungen = df_empfehlungen[df_empfehlungen['probability'] >= min_probability]
            df_empfehlungen = df_empfehlungen.sort_values('probability', ascending=False)

            print(f"Found {len(df_empfehlungen)} recommendations")

            if len(df_empfehlungen) == 0:
                return

            supabase_url = os.getenv('SUPABASE_URL')
            supabase_key = os.getenv('SUPABASE_SERVICE_KEY') or os.getenv('SUPABASE_KEY')

            if not supabase_url or not supabase_key:
                return

            headers = {
                'apikey': supabase_key,
                'Authorization': f'Bearer {supabase_key}',
                'Content-Type': 'application/json',
                'Prefer': 'return=representation'
            }

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            clean_model_name = model_name.replace('.pkl', '').replace(' ', '_').replace('-', '_').lower()
            clean_model_name = re.sub(r'[^a-z0-9_]', '', clean_model_name)[:20]
            clean_version = model_version.replace('.', '').replace('_', '').replace(' ', '').lower()[:5]

            table_name = f"emp_{clean_model_name}_{clean_version}_{timestamp}"
            if table_name[0].isdigit():
                table_name = 'tbl_' + table_name

            if not self._erstelle_empfehlungs_tabelle(table_name):
                return

            url = f"{supabase_url}/rest/v1/{table_name}"
            stats = {'inserted': 0, 'errors': 0}

            for idx, row in df_empfehlungen.iterrows():
                data = {
                    'model_name': model_name,
                    'model_version': model_version,
                    'model_id': getattr(self, '_current_model_id', None),
                    'project_id': str(row.get('id', idx)),
                    'simap_project_id': str(row.get('simap_project_id', '')) if pd.notna(row.get('simap_project_id')) else None,
                    'simap_publication_id': str(row.get('simap_publication_id', '')) if pd.notna(row.get('simap_publication_id')) else None,
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
                }

                try:
                    response = requests.post(url, headers=headers, json=data, timeout=10)
                    if response.status_code in [200, 201]:
                        stats['inserted'] += 1
                    else:
                        stats['errors'] += 1
                except:
                    stats['errors'] += 1

            print(f"Recommendations saved: {stats['inserted']}, errors: {stats['errors']}")

        except Exception as e:
            print(f"Error creating recommendations: {e}")

    def _erstelle_empfehlungs_tabelle(self, table_name):
        try:
            import requests

            supabase_url = os.getenv('SUPABASE_URL')
            supabase_key = os.getenv('SUPABASE_SERVICE_KEY') or os.getenv('SUPABASE_KEY')

            headers = {
                'apikey': supabase_key,
                'Authorization': f'Bearer {supabase_key}',
                'Content-Type': 'application/json'
            }

            url = f"{supabase_url}/rest/v1/rpc/create_empfehlungen_table"
            response = requests.post(url, headers=headers, json={'table_name': table_name}, timeout=10)

            if response.status_code in [200, 201, 204]:
                print(f"Table {table_name} created")
                return True
            else:
                print(f"Table creation failed: {response.status_code}")
                return False

        except Exception as e:
            print(f"Error creating table: {e}")
            return False

    def laden(self, pfad, von_supabase=False, bucket_name="ml_models"):
        if von_supabase:
            try:
                import requests
                import io

                supabase_url = os.getenv('SUPABASE_URL')
                supabase_key = os.getenv('SUPABASE_KEY')

                download_url = f"{supabase_url}/storage/v1/object/{bucket_name}/{pfad}"

                headers = {
                    'apikey': supabase_key,
                    'Authorization': f'Bearer {supabase_key}'
                }

                response = requests.get(download_url, headers=headers, timeout=30)

                if response.status_code != 200:
                    raise Exception(f"Download error: {response.status_code}")

                model_data = joblib.load(io.BytesIO(response.content))

            except Exception as e:
                print(f"Error loading from Supabase: {e}")
                raise
        else:
            model_data = joblib.load(pfad)

        self.classifier = model_data['classifier']
        self.label_encoders = model_data['label_encoders']
        self.kriterien_config = model_data.get('kriterien_config')
        self._kw_must_emb = model_data.get('kw_must_emb')
        self._kw_should_emb = model_data.get('kw_should_emb')
        self._kw_exclude_emb = model_data.get('kw_exclude_emb')

        print(f"Model loaded")

    def lade_daten_von_supabase(self, tage_zurueck=365, kantone=None, projekt_typen=None, auftrags_arten=None, limit=20000):
        print(f"\nLoading data from Supabase (last {tage_zurueck} days)...")

        try:
            loader = SupabaseAPILoader()
            df = loader.lade_projekte(
                tage_zurueck=tage_zurueck,
                kantone=kantone,
                projekt_typen=projekt_typen,
                auftrags_arten=auftrags_arten,
                limit=limit
            )

            if len(df) > 0:
                print(f"{len(df)} projects loaded")

            return df
        except Exception as e:
            print(f"Error loading: {e}")
            return pd.DataFrame()

    def speichere_interessante_projekte_zu_supabase(self, df_interessant, kriterien=None, model_version="v1.0"):
        print(f"\nSaving {len(df_interessant)} projects to Supabase...")

        if len(df_interessant) == 0:
            return {'inserted': 0, 'skipped': 0, 'errors': 0}

        try:
            import requests
            import json
            from datetime import datetime

            supabase_url = os.getenv('SUPABASE_URL')
            supabase_key = os.getenv('SUPABASE_SERVICE_KEY') or os.getenv('SUPABASE_KEY')

            headers = {
                'apikey': supabase_key,
                'Authorization': f'Bearer {supabase_key}',
                'Content-Type': 'application/json',
                'Prefer': 'return=representation'
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

            for idx, row in df_interessant.iterrows():
                data = {
                    'project_id': str(row.get('id', idx)),
                    'simap_project_id': str(row.get('simap_project_id', '')) if pd.notna(row.get('simap_project_id')) else None,
                    'simap_publication_id': str(row.get('simap_publication_id', '')) if pd.notna(row.get('simap_publication_id')) else None,
                    'title': str(row.get('title', '')),
                    'title_de': str(row.get('title_de', row.get('title', ''))),
                    'title_fr': str(row.get('title_fr', '')),
                    'description': str(row.get('description', '')),
                    'description_de': str(row.get('description_de', row.get('description', ''))),
                    'description_fr': str(row.get('description_fr', '')),
                    'canton': str(row.get('canton', '')),
                    'cpv_code': str(row.get('cpv_code', '')),
                    'cpv_code_main': str(row.get('cpv_code_main', row.get('cpv_code', ''))),
                    'project_type': str(row.get('project_type', '')),
                    'publication_date': row.get('publication_date'),
                    'deadline': row.get('deadline'),
                    'submission_deadline': row.get('submission_deadline'),
                    'estimated_amount': float(row.get('estimated_amount', 0)) if pd.notna(row.get('estimated_amount')) else None,
                    'contract_value': float(row.get('contract_value', 0)) if pd.notna(row.get('contract_value')) else None,
                    'interessant_wahrscheinlichkeit': float(row['interessant_wahrscheinlichkeit']),
                    'model_version': model_version,
                    'kriterien': json.dumps(kriterien_dict) if kriterien_dict else None,
                    'url': str(row.get('url', ''))
                }

                try:
                    response = requests.post(url, headers=headers, json=data, timeout=10)
                    if response.status_code in [200, 201]:
                        stats['inserted'] += 1
                    elif response.status_code == 409:
                        stats['skipped'] += 1
                    else:
                        stats['errors'] += 1
                except:
                    stats['errors'] += 1

            print(f"Inserted: {stats['inserted']}, Skipped: {stats['skipped']}, Errors: {stats['errors']}")
            return stats

        except Exception as e:
            print(f"Error: {e}")
            return {'inserted': 0, 'skipped': 0, 'errors': len(df_interessant)}


def interaktive_kriterien_eingabe():
    print("\n" + "="*60)
    print("DEFINE CRITERIA")
    print("="*60)

    kriterien = FilterKriterien()

    print("\n--- ORDER TYPES ---")
    print("Options: construction, service, supply")
    print("This is the most important filter to prevent wrong results")
    order_input = input("Order types (comma-separated): ").strip().lower()
    if order_input:
        kriterien.order_types = [o.strip() for o in order_input.split(',') if o.strip()]
        print(f"Set: {kriterien.order_types}")

    print("\n--- CPV CODES ---")
    print("Examples: 45 (Construction), 72 (IT), 71 (Engineering)")
    cpv_input = input("CPV prefixes (comma-separated): ").strip()
    if cpv_input:
        kriterien.cpv_codes = [c.strip() for c in cpv_input.split(',') if c.strip()]
        print(f"Set: {kriterien.cpv_codes}")

    print("\n--- MUST KEYWORDS ---")
    print("Projects must match at least one of these semantically")
    must_input = input("MUST keywords (comma-separated): ").strip()
    if must_input:
        kriterien.keywords_must = [k.strip() for k in must_input.split(',') if k.strip()]
        print(f"Set: {len(kriterien.keywords_must)} keywords")

    print("\n--- SHOULD KEYWORDS (optional) ---")
    print("Bonus score if matched")
    should_input = input("SHOULD keywords (comma-separated): ").strip()
    if should_input:
        kriterien.keywords_should = [k.strip() for k in should_input.split(',') if k.strip()]
        print(f"Set: {len(kriterien.keywords_should)} keywords")

    print("\n--- EXCLUDE KEYWORDS ---")
    print("Projects matching these are excluded")
    exclude_input = input("EXCLUDE keywords (comma-separated): ").strip()
    if exclude_input:
        kriterien.keywords_exclude = [k.strip() for k in exclude_input.split(',') if k.strip()]
        print(f"Set: {len(kriterien.keywords_exclude)} keywords")

    print("\n--- CANTONS (optional) ---")
    kantone_input = input("Cantons (e.g. ZH,BE,AG): ").strip().upper()
    if kantone_input:
        kriterien.kantone = [k.strip() for k in kantone_input.split(',') if k.strip()]
        print(f"Set: {kriterien.kantone}")

    print("\n--- PROJECT TYPES (optional) ---")
    print("Options: tender, direct_award, planning_procedure")
    projekt_input = input("Project types: ").strip().lower()
    if projekt_input:
        kriterien.project_types = [p.strip() for p in projekt_input.split(',') if p.strip()]
        print(f"Set: {kriterien.project_types}")

    print("\n--- BUDGET (optional) ---")
    min_budget = input("Min budget (CHF): ").strip()
    if min_budget:
        kriterien.min_budget = float(min_budget)

    max_budget = input("Max budget (CHF): ").strip()
    if max_budget:
        kriterien.max_budget = float(max_budget)

    print("\n--- THRESHOLDS ---")
    print("Default: MUST=0.55, EXCLUDE=0.50")
    th_must = input("MUST threshold (0.4-0.7, Enter=0.55): ").strip()
    if th_must:
        kriterien.semantic_threshold_must = float(th_must)

    th_exclude = input("EXCLUDE threshold (0.4-0.6, Enter=0.50): ").strip()
    if th_exclude:
        kriterien.semantic_threshold_exclude = float(th_exclude)

    print("\n--- SUMMARY ---")
    print(f"Order Types: {kriterien.order_types}")
    print(f"CPV Codes: {kriterien.cpv_codes}")
    print(f"MUST Keywords: {len(kriterien.keywords_must)}")
    print(f"SHOULD Keywords: {len(kriterien.keywords_should)}")
    print(f"EXCLUDE Keywords: {len(kriterien.keywords_exclude)}")
    print(f"Cantons: {kriterien.kantone}")
    print(f"Project Types: {kriterien.project_types}")
    print(f"Budget: {kriterien.min_budget} - {kriterien.max_budget}")
    print(f"Thresholds: MUST={kriterien.semantic_threshold_must}, EXCLUDE={kriterien.semantic_threshold_exclude}")

    return kriterien


def zeige_ergebnisse(df, max_anzahl=10):
    print("\n" + "="*60)
    print(f"TOP {min(max_anzahl, len(df))} RESULTS")
    print("="*60)

    for idx, row in df.head(max_anzahl).iterrows():
        print(f"\n{'-'*60}")
        print(f"Title: {row.get('title', 'N/A')}")
        print(f"Probability: {row['interessant_wahrscheinlichkeit']:.1%}")

        details = []
        if 'canton' in row and pd.notna(row['canton']):
            details.append(f"Canton: {row['canton']}")
        if 'order_type' in row and pd.notna(row['order_type']):
            details.append(f"Type: {row['order_type']}")
        if 'cpv_code' in row and pd.notna(row['cpv_code']):
            details.append(f"CPV: {row['cpv_code']}")

        if details:
            print(" | ".join(details))


def main():
    print("="*60)
    print("PROJECT CLASSIFIER")
    print("="*60)

    print("\n1. Train new model")
    print("2. Load model and find projects")
    print("3. Exit")

    wahl = input("\nChoice (1-3): ").strip()

    if wahl == '3':
        return

    print("\nTesting Supabase connection...")
    if not teste_supabase_api():
        print("Supabase connection failed")
        return

    klassifikator = ProjektKlassifikator()

    if wahl == '1':
        tage = input("Days to load for training (default 365): ").strip()
        tage_zurueck = int(tage) if tage else 365

        df = klassifikator.lade_daten_von_supabase(tage_zurueck=tage_zurueck)

        if len(df) == 0:
            print("No data loaded")
            return

        kriterien = interaktive_kriterien_eingabe()
        klassifikator.set_kriterien(kriterien)

        df = klassifikator.daten_vorbereiten(df)
        df_filtered = klassifikator.wende_harte_filter_an(df)

        if len(df_filtered) < 50:
            print(f"Only {len(df_filtered)} projects after filter - too few for training")
            return

        df_scored = klassifikator.berechne_semantic_scores(df_filtered)
        labels = klassifikator.erstelle_labels(df_scored)

        model_name = input("Model name (e.g. my_model.pkl): ").strip()
        if not model_name:
            model_name = "model.pkl"
        if not model_name.endswith('.pkl'):
            model_name += '.pkl'

        model_version = input("Model version (default v1.0): ").strip()
        if not model_version:
            model_version = "v1.0"

        klassifikator.trainieren(df_scored, labels, model_name=model_name, model_version=model_version)

        print("\nSearch for projects now? (y/n)")
        if input("> ").strip().lower() not in ['y', 'yes', 'j', 'ja']:
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

            response = requests.post(list_url, headers=headers, json={"limit": 100}, timeout=10)

            if response.status_code == 200:
                files = response.json()
                models = [f for f in files if f.get('name', '').endswith('.pkl')]

                if models:
                    print("\nAvailable models:")
                    for i, f in enumerate(models, 1):
                        print(f"  [{i}] {f['name']}")

                    auswahl = input("\nModel number or name: ").strip()

                    if auswahl.isdigit() and 1 <= int(auswahl) <= len(models):
                        model_name = models[int(auswahl) - 1]['name']
                    else:
                        model_name = auswahl
                        if not model_name.endswith('.pkl'):
                            model_name += '.pkl'

                    klassifikator.laden(model_name, von_supabase=True)
                else:
                    print("No models found - train a model first")
                    return
            else:
                print("Error listing models")
                return

        except Exception as e:
            print(f"Error: {e}")
            return

    tage = input("\nDays to load for prediction (default 30): ").strip()
    tage_zurueck = int(tage) if tage else 30

    df = klassifikator.lade_daten_von_supabase(tage_zurueck=tage_zurueck)

    if 'submission_deadline' in df.columns:
        df['submission_deadline'] = pd.to_datetime(df['submission_deadline'], errors='coerce')
        heute = pd.Timestamp.now(tz='UTC')
        df = df[df['submission_deadline'] >= heute]
        print(f"{len(df)} projects with open deadline")

    min_prob = input("Minimum probability (0.0-1.0, default 0.6): ").strip()
    min_prob = float(min_prob) if min_prob else 0.6

    top_n = input("Max results (empty = all): ").strip()
    top_n = int(top_n) if top_n else None

    interesting = klassifikator.finde_interessante(df, min_prob=min_prob, top_n=top_n)

    if len(interesting) > 0:
        zeige_ergebnisse(interesting)

        output_file = input("\nSave as CSV (e.g. results.csv): ").strip()
        if output_file:
            if not output_file.endswith('.csv'):
                output_file += '.csv'
            interesting.to_csv(output_file, sep='\t', index=False)
            print(f"Saved: {output_file}")

        print("\nSave to Supabase? (y/n)")
        if input("> ").strip().lower() in ['y', 'yes', 'j', 'ja']:
            klassifikator.speichere_interessante_projekte_zu_supabase(
                interesting,
                kriterien=klassifikator.kriterien_config
            )
    else:
        print("\nNo interesting projects found")
        print("Try lowering min_prob or adjusting criteria")


if __name__ == "__main__":
    main()