import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import classification_report, accuracy_score
from sentence_transformers import SentenceTransformer
import joblib
import os
import warnings
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from typing import Optional, List
from dotenv import load_dotenv

warnings.filterwarnings('ignore')

# Lade Umgebungsvariablen
load_dotenv()


class SupabaseLoader:
    """Lädt Daten direkt aus Supabase PostgreSQL"""

    def __init__(self, database_url: Optional[str] = None):
        self.database_url = database_url or os.getenv('DATABASE_URL')
        if not self.database_url:
            raise ValueError(
                "❌ DATABASE_URL nicht gefunden!\n"
                "Bitte .env Datei mit DATABASE_URL erstellen."
            )
        self.conn = None

    def verbinden(self):
        """Stellt Verbindung zu Supabase her"""
        try:
            self.conn = psycopg2.connect(self.database_url)
            print("✓ Verbindung zu Supabase hergestellt")
            return True
        except Exception as e:
            print(f"❌ Fehler beim Verbinden: {e}")
            return False

    def trennen(self):
        """Schließt Verbindung"""
        if self.conn:
            self.conn.close()
            print("✓ Verbindung getrennt")

    def lade_projekte(self,
                     tage_zurueck: int = 10,
                     kantone: Optional[List[str]] = None,
                     projekt_typen: Optional[List[str]] = None,
                     auftrags_arten: Optional[List[str]] = None) -> pd.DataFrame:
        """
        Lädt Projekte aus Supabase mit optionalen Filtern

        Args:
            tage_zurueck: Anzahl Tage zurück (default: 10)
            kantone: Liste von Kantonen (z.B. ['ZH', 'BE'])
            projekt_typen: Liste von Projekttypen
            auftrags_arten: Liste von Auftragsarten

        Returns:
            DataFrame mit Projekten
        """
        try:
            if not self.conn:
                self.verbinden()

            # Berechne Start-Datum
            start_datum = (datetime.now() - timedelta(days=tage_zurueck)).strftime('%Y-%m-%d')

            # Basis-Query
            query = """
                SELECT
                    id,
                    title,
                    description,
                    publication_type,
                    project_type,
                    project_subtype,
                    canton,
                    process_type,
                    lots_type,
                    order_type,
                    construction_type,
                    construction_category,
                    creation_language,
                    estimated_amount,
                    cpv_code,
                    submission_deadline,
                    publication_date,
                    created_at,
                    updated_at
                FROM projects
                WHERE publication_date >= %s
            """

            params = [start_datum]

            # Optionale Filter
            if kantone:
                query += " AND canton = ANY(%s)"
                params.append(kantone)

            if projekt_typen:
                query += " AND project_type = ANY(%s)"
                params.append(projekt_typen)

            if auftrags_arten:
                query += " AND order_type = ANY(%s)"
                params.append(auftrags_arten)

            query += " ORDER BY publication_date DESC"

            print(f"Lade Projekte aus Supabase (letzte {tage_zurueck} Tage)...")
            df = pd.read_sql_query(query, self.conn, params=params)
            print(f"✓ {len(df)} Projekte geladen")

            return df

        except Exception as e:
            print(f"❌ Fehler beim Laden: {e}")
            return pd.DataFrame()

    def __enter__(self):
        self.verbinden()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.trennen()


class ProjektKlassifikator:


    def __init__(self):
        print("Lade Embedding-Modell")
        self.embedding_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
        self.rf_classifier = None
        self.label_encoders = {}
        self.kriterien_config = {}  # Speichert die Kriterien
        self.categorical_features = [
            'publication_type', 'project_type', 'project_subtype',
            'canton', 'process_type', 'lots_type', 'order_type',
            'construction_type', 'construction_category', 'creation_language'
        ]

    def daten_vorbereiten(self, df):
        """Bereitet Daten vor"""
        df = df.copy()
        df['title'] = df['title'].fillna('')
        df['description'] = df['description'].fillna('')
        df['combined_text'] = df['title'] + ' ' + df['description']

        for col in self.categorical_features:
            if col in df.columns:
                df[col] = df[col].fillna('unknown').astype(str)

        return df

    def erstelle_embeddings(self, texts):
        """Erstellt Text-Embeddings"""
        print(f"Erstelle Embeddings für {len(texts)} Texte...")
        return self.embedding_model.encode(texts, show_progress_bar=True, batch_size=32)

    def encodiere_kategorien(self, df, fit=True):
        """One-Hot-Encoding für kategoriale Features"""
        encoded_features = []

        for col in self.categorical_features:
            if col not in df.columns:
                continue

            if fit:
                le = LabelEncoder()
                unique_vals = list(df[col].unique()) + ['unknown']
                le.fit(unique_vals)
                self.label_encoders[col] = le

            le = self.label_encoders[col]
            encoded = []
            for val in df[col]:
                try:
                    encoded.append(le.transform([val])[0])
                except:
                    encoded.append(le.transform(['unknown'])[0])

            n_classes = len(le.classes_)
            one_hot = np.zeros((len(encoded), n_classes))
            for i, val in enumerate(encoded):
                one_hot[i, val] = 1

            encoded_features.append(one_hot)

        return np.hstack(encoded_features) if encoded_features else np.array([]).reshape(len(df), 0)

    def berechne_keyword_score(self, text, keywords):
        """
        Berechnet einen Keyword-Matching-Score mit Gewichtung
        - Exakte Titel-Treffer: sehr hohe Gewichtung
        - Phrasen-Treffer: hohe Gewichtung
        - Einzelwort-Treffer: moderate Gewichtung
        """
        if not keywords:
            return 0.0

        text_lower = text.lower()
        score = 0.0

        for keyword in keywords:
            keyword_lower = keyword.lower()

            # Exakter Treffer (ganzer Titel/Phrase) - sehr hohe Gewichtung
            if keyword_lower == text_lower:
                score += 10.0
            # Phrase komplett enthalten - hohe Gewichtung
            elif keyword_lower in text_lower:
                # Längere Phrasen bekommen mehr Gewicht
                phrase_length = len(keyword_lower.split())
                score += 5.0 * (1 + phrase_length * 0.3)
            # Einzelne Wörter aus der Phrase - moderate Gewichtung
            else:
                keyword_words = keyword_lower.split()
                if len(keyword_words) > 1:
                    # Mehrwort-Phrase: zähle wie viele Wörter gefunden werden
                    found_words = sum(1 for word in keyword_words if word in text_lower)
                    if found_words > 0:
                        match_ratio = found_words / len(keyword_words)
                        score += 2.0 * match_ratio
                else:
                    # Einzelwort
                    if keyword_lower in text_lower:
                        score += 1.0

        # Normalisiere auf 0-1 Bereich (aber kann höher gehen für sehr gute Matches)
        return min(score / len(keywords), 3.0)

    def erstelle_features(self, df, fit=True):
        """Erstellt komplette Feature-Matrix mit Keyword-Features"""
        embeddings = self.erstelle_embeddings(df['combined_text'].tolist())
        categorical = self.encodiere_kategorien(df, fit=fit)

        # Berechne Keyword-Scores als zusätzliche Features
        keyword_features = np.zeros((len(df), 2))  # [title_score, description_score]

        if self.kriterien_config.get('keywords'):
            print("Berechne Keyword-Matching-Scores...")
            for i, row in df.iterrows():
                title_score = self.berechne_keyword_score(
                    str(row.get('title', '')),
                    self.kriterien_config['keywords']
                )
                desc_score = self.berechne_keyword_score(
                    str(row.get('description', '')),
                    self.kriterien_config['keywords']
                )
                keyword_features[i] = [title_score, desc_score]

        # Kombiniere alle Features
        if categorical.shape[1] > 0:
            features = np.hstack([embeddings, categorical, keyword_features])
        else:
            features = np.hstack([embeddings, keyword_features])

        print(f"Feature-Matrix: {features.shape}")
        return features

    def erstelle_labels_aus_kriterien(self, df, kriterien):
        """
        Erstellt Labels basierend auf Kriterien-Dictionary
        Keywords bekommen höhere Gewichtung!
        """
        labels = np.zeros(len(df), dtype=int)
        keyword_bonus = np.zeros(len(df), dtype=float)

        # Kantone
        if kriterien.get('kantone') and 'canton' in df.columns:
            labels[df['canton'].isin(kriterien['kantone'])] = 1

        # Projekttypen
        if kriterien.get('projekt_typen') and 'project_type' in df.columns:
            labels[df['project_type'].isin(kriterien['projekt_typen'])] = 1

        # Auftragsarten
        if kriterien.get('auftrags_arten') and 'order_type' in df.columns:
            labels[df['order_type'].isin(kriterien['auftrags_arten'])] = 1

        # Schlüsselwörter - MIT HÖHERER GEWICHTUNG!
        if kriterien.get('keywords'):
            print("\nAnalysiere Keyword-Matches...")
            for idx, row in df.iterrows():
                title_score = self.berechne_keyword_score(
                    str(row.get('title', '')),
                    kriterien['keywords']
                )
                desc_score = self.berechne_keyword_score(
                    str(row.get('description', '')),
                    kriterien['keywords']
                )

                total_score = title_score * 2.0 + desc_score  # Titel doppelt gewichtet
                keyword_bonus[idx] = total_score

                # Wenn guter Match (Score > 1.0), als interessant markieren
                if total_score > 1.0:
                    labels[idx] = 1

            # Zeige Statistik
            high_matches = np.sum(keyword_bonus > 2.0)
            medium_matches = np.sum((keyword_bonus > 1.0) & (keyword_bonus <= 2.0))
            print(f"  Starke Keyword-Matches: {high_matches}")
            print(f"  Mittlere Keyword-Matches: {medium_matches}")

        # Budget
        if 'estimated_amount' in df.columns:
            if kriterien.get('min_budget'):
                labels[df['estimated_amount'] >= kriterien['min_budget']] = 1
            if kriterien.get('max_budget'):
                labels[(df['estimated_amount'] <= kriterien['max_budget']) &
                       (df['estimated_amount'] > 0)] = 1

        # CPV-Codes
        if kriterien.get('cpv_codes') and 'cpv_code' in df.columns:
            for code in kriterien['cpv_codes']:
                labels[df['cpv_code'].astype(str).str.startswith(str(code), na=False)] = 1

        return labels

    def trainieren(self, df, labels):
        """Trainiert das Modell"""
        print("\n" + "="*70)
        print("TRAINING GESTARTET")
        print("="*70)

        df = self.daten_vorbereiten(df)
        X = self.erstelle_features(df, fit=True)
        y = labels

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.1, random_state=42, stratify=y
        )

        print(f"\nTrainings-Set: {X_train.shape[0]} Projekte")
        print(f"Test-Set: {X_test.shape[0]} Projekte")
        print(f"Interessant: {np.sum(y_train == 1)} / Nicht interessant: {np.sum(y_train == 0)}")

        print("\nTrainiere Random Forest Classifier...")
        self.rf_classifier = RandomForestClassifier(
            n_estimators=222,
            max_depth=25,
            min_samples_split=5,
            min_samples_leaf=2,
            random_state=42,
            n_jobs=-1,
            class_weight='balanced'
        )
        self.rf_classifier.fit(X_train, y_train)

        y_pred = self.rf_classifier.predict(X_test)
        accuracy = accuracy_score(y_test, y_pred)

        print("\n" + "="*70)
        print("TRAINING ABGESCHLOSSEN")
        print("="*70)
        print(f"\nAccuracy: {accuracy:.2%}")
        print("\nClassification Report:")
        print(classification_report(y_test, y_pred,
                                   target_names=['Nicht interessant', 'Interessant']))

        return accuracy

    def vorhersagen(self, df):
        """Macht Vorhersagen"""
        if self.rf_classifier is None:
            raise ValueError("Modell muss erst trainiert oder geladen werden!")

        df = self.daten_vorbereiten(df)
        X = self.erstelle_features(df, fit=False)
        predictions = self.rf_classifier.predict(X)
        probabilities = self.rf_classifier.predict_proba(X)[:, 1]
        return predictions, probabilities

    def finde_interessante(self, df, min_prob=0.7, top_n=None):
        """Findet interessante Projekte"""
        predictions, probabilities = self.vorhersagen(df)

        result_df = df.copy()
        result_df['interessant_vorhersage'] = predictions
        result_df['interessant_wahrscheinlichkeit'] = probabilities

        # Berechne auch Keyword-Scores für die Anzeige
        if self.kriterien_config.get('keywords'):
            keyword_scores = []
            for idx, row in result_df.iterrows():
                title_score = self.berechne_keyword_score(
                    str(row.get('title', '')),
                    self.kriterien_config['keywords']
                )
                desc_score = self.berechne_keyword_score(
                    str(row.get('description', '')),
                    self.kriterien_config['keywords']
                )
                keyword_scores.append(title_score * 2.0 + desc_score)

            result_df['keyword_match_score'] = keyword_scores

        interesting = result_df[result_df['interessant_wahrscheinlichkeit'] >= min_prob]
        interesting = interesting.sort_values('interessant_wahrscheinlichkeit', ascending=False)

        if top_n:
            interesting = interesting.head(top_n)

        return interesting

    def speichern(self, pfad):
        """Speichert das Modell"""
        if self.rf_classifier is None:
            raise ValueError("Kein Modell zum Speichern!")

        model_data = {
            'rf_classifier': self.rf_classifier,
            'label_encoders': self.label_encoders,
            'kriterien_config': self.kriterien_config
        }
        joblib.dump(model_data, pfad)
        print(f"✓ Modell gespeichert: {pfad}")

    def laden(self, pfad):
        """Lädt ein gespeichertes Modell"""
        model_data = joblib.load(pfad)
        self.rf_classifier = model_data['rf_classifier']
        self.label_encoders = model_data['label_encoders']
        self.kriterien_config = model_data.get('kriterien_config', {})
        print(f"✓ Modell geladen: {pfad}")


def interaktive_kriterien_eingabe():
    """Interaktive Eingabe der Kriterien"""
    print("\n" + "="*70)
    print("SCHRITT 1: KRITERIEN DEFINIEREN")
    print("="*70)
    print("\nDefinieren Sie, welche Projekte für Sie interessant sind.")
    print("(Leere Eingabe = Kriterium überspringen)\n")

    kriterien = {}

    # Kantone
    print("─" * 70)
    print("KANTONE")
    print("Welche Kantone interessieren Sie?")
    kantone_input = input("Komma-getrennt (z.B. ZH,BE,GR) oder leer: ").strip().upper()
    if kantone_input:
        kriterien['kantone'] = [k.strip() for k in kantone_input.split(',') if k.strip()]
        print(f"✓ Kantone: {', '.join(kriterien['kantone'])}")

    # Projekttypen
    print("\n" + "─" * 70)
    print("PROJEKTTYPEN")
    print("Optionen: tender (Ausschreibung), direct_award (Direktvergabe), planning_procedure (Planungsverfahren)")
    projekt_input = input("Komma-getrennt oder leer: ").strip().lower()
    if projekt_input:
        kriterien['projekt_typen'] = [p.strip() for p in projekt_input.split(',') if p.strip()]
        print(f"✓ Projekttypen: {', '.join(kriterien['projekt_typen'])}")

    # Auftragsarten
    print("\n" + "─" * 70)
    print("AUFTRAGSARTEN")
    print("Optionen: construction (Bau), service (Dienstleistung), supply (Lieferung)")
    auftrags_input = input("Komma-getrennt oder leer: ").strip().lower()
    if auftrags_input:
        kriterien['auftrags_arten'] = [a.strip() for a in auftrags_input.split(',') if a.strip()]
        print(f"✓ Auftragsarten: {', '.join(kriterien['auftrags_arten'])}")

    # Schlüsselwörter
    print("\n" + "─" * 70)
    print("SCHLÜSSELWÖRTER / PROJEKT-TITEL (⭐ WICHTIG!)")
    print("\nGeben Sie Projekte ein, die Sie bereits haben oder gerne möchten:")
    print("\n📋 Trennzeichen-Optionen:")
    print("  1. Komma (,):        brücke,tunnel,Sanierung Hauptstrasse")
    print("  2. Semikolon (;):    brücke;tunnel;Sanierung Hauptstrasse")
    print("  3. Neue Zeile:       Jeder Eintrag auf eigener Zeile (Ende mit leerer Zeile)")

    trennung = input("\nWelche Trennung? (1=Komma, 2=Semikolon, 3=Zeilen, Enter=Komma): ").strip()

    kriterien['keywords'] = []

    if trennung == '3':
        print("\nGeben Sie Keywords/Titel ein (leere Zeile zum Beenden):")
        while True:
            line = input("  > ").strip()
            if not line:
                break
            kriterien['keywords'].append(line)
    else:
        if trennung == '2':
            separator = ';'
            print("\nEingabe (Semikolon-getrennt):")
        else:
            separator = ','
            print("\nEingabe (Komma-getrennt):")

        keywords_input = input("> ").strip()

        if keywords_input:
            current = ""
            in_quotes = False

            for char in keywords_input:
                if char in ['"', "'"]:
                    in_quotes = not in_quotes
                elif char == separator and not in_quotes:
                    if current.strip():
                        kriterien['keywords'].append(current.strip())
                    current = ""
                else:
                    current += char

            if current.strip():
                kriterien['keywords'].append(current.strip())

    if kriterien['keywords']:
        print(f"\n✓ {len(kriterien['keywords'])} Schlüsselwörter/Phrasen erfasst:")
        for i, kw in enumerate(kriterien['keywords'], 1):
            print(f"    {i}. '{kw}'")

    # Budget
    print("\n" + "─" * 70)
    print("BUDGET-BEREICH")
    min_budget = input("Minimales Budget (CHF) oder leer: ").strip()
    if min_budget:
        try:
            kriterien['min_budget'] = float(min_budget)
            print(f"✓ Min. Budget: CHF {kriterien['min_budget']:,.0f}")
        except:
            print("⚠ Ungültige Eingabe, übersprungen")

    max_budget = input("Maximales Budget (CHF) oder leer: ").strip()
    if max_budget:
        try:
            kriterien['max_budget'] = float(max_budget)
            print(f"✓ Max. Budget: CHF {kriterien['max_budget']:,.0f}")
        except:
            print("⚠ Ungültige Eingabe, übersprungen")

    # CPV-Codes
    print("\n" + "─" * 70)
    print("CPV-CODES (Branchencodes)")
    print("Beispiele: 45 (Bau), 71 (Ingenieur), 72 (IT)")
    cpv_input = input("Komma-getrennt oder leer: ").strip()
    if cpv_input:
        kriterien['cpv_codes'] = [c.strip() for c in cpv_input.split(',') if c.strip()]
        print(f"✓ CPV-Codes: {', '.join(kriterien['cpv_codes'])}")

    return kriterien


def interaktive_filter_eingabe():
    """Interaktive Eingabe zusätzlicher Filter"""
    print("\n" + "="*70)
    print("ZUSÄTZLICHE FILTER (nach ML-Vorhersage)")
    print("="*70)
    print("\nMöchten Sie zusätzliche Filter anwenden? (j/n)")

    if input("> ").strip().lower() not in ['j', 'ja', 'y', 'yes']:
        return {'aktiv': False}

    filter_config = {'aktiv': True}

    print("\nFilter nach Kantonen?")
    kantone = input("Komma-getrennt oder leer: ").strip().upper()
    if kantone:
        filter_config['kantone'] = [k.strip() for k in kantone.split(',') if k.strip()]

    print("\nFilter nach Projekttypen?")
    typen = input("Komma-getrennt oder leer: ").strip().lower()
    if typen:
        filter_config['projekt_typen'] = [t.strip() for t in typen.split(',') if t.strip()]

    print("\nFilter nach Auftragsarten?")
    arten = input("Komma-getrennt oder leer: ").strip().lower()
    if arten:
        filter_config['auftrags_arten'] = [a.strip() for a in arten.split(',') if a.strip()]

    print("\nFilter nach Schlüsselwörtern?")
    keywords = input("Komma-getrennt oder leer: ").strip().lower()
    if keywords:
        filter_config['keywords'] = [k.strip() for k in keywords.split(',') if k.strip()]

    return filter_config


def wende_filter_an(df, filter_config):
    """Wendet zusätzliche Filter an"""
    if not filter_config.get('aktiv', False):
        return df

    filtered = df.copy()
    original_count = len(filtered)

    if filter_config.get('kantone') and 'canton' in filtered.columns:
        filtered = filtered[filtered['canton'].isin(filter_config['kantone'])]
        print(f"  Nach Kanton-Filter: {len(filtered)} ({len(filtered)-original_count:+d})")

    if filter_config.get('projekt_typen') and 'project_type' in filtered.columns:
        filtered = filtered[filtered['project_type'].isin(filter_config['projekt_typen'])]
        print(f"  Nach Projekttyp-Filter: {len(filtered)}")

    if filter_config.get('auftrags_arten') and 'order_type' in filtered.columns:
        filtered = filtered[filtered['order_type'].isin(filter_config['auftrags_arten'])]
        print(f"  Nach Auftragsart-Filter: {len(filtered)}")

    if filter_config.get('keywords'):
        keyword_mask = pd.Series([False] * len(filtered), index=filtered.index)
        for keyword in filter_config['keywords']:
            if 'title' in filtered.columns:
                keyword_mask |= filtered['title'].str.contains(keyword, case=False, na=False)
            if 'description' in filtered.columns:
                keyword_mask |= filtered['description'].str.contains(keyword, case=False, na=False)
        filtered = filtered[keyword_mask]
        print(f"  Nach Keyword-Filter: {len(filtered)}")

    return filtered


def zeige_ergebnisse(df, max_anzahl=10):
    """Zeigt Ergebnisse an"""
    print("\n" + "="*70)
    print(f"TOP {min(max_anzahl, len(df))} INTERESSANTE PROJEKTE")
    print("="*70)

    for idx, row in df.head(max_anzahl).iterrows():
        print(f"\n{'─'*70}")
        print(f"Titel: {row.get('title', 'N/A')}")
        print(f"Match-Score: {row['interessant_wahrscheinlichkeit']:.1%}", end='')

        if 'keyword_match_score' in row and row['keyword_match_score'] > 0:
            print(f" | Keyword-Score: {row['keyword_match_score']:.1f} ⭐")
        else:
            print()

        details = []
        if 'canton' in row and pd.notna(row['canton']):
            details.append(f"Kanton: {row['canton']}")
        if 'project_type' in row and pd.notna(row['project_type']):
            details.append(f"Typ: {row['project_type']}")
        if 'order_type' in row and pd.notna(row['order_type']):
            details.append(f"Art: {row['order_type']}")
        if 'submission_deadline' in row and pd.notna(row['submission_deadline']):
            details.append(f"Deadline: {row['submission_deadline']}")
        if 'estimated_amount' in row and pd.notna(row['estimated_amount']):
            details.append(f"Budget: CHF {row['estimated_amount']:,.0f}")

        if details:
            print(" | ".join(details))

        if 'description' in row and pd.notna(row['description']):
            desc = str(row['description'])[:150]
            print(f"Beschreibung: {desc}...")


def main():
    """Hauptprogramm"""
    print("="*70)
    print("PROJEKT-KLASSIFIKATOR - SUPABASE VERSION")
    print("="*70)
    print("ML-basierte Identifikation interessanter Ausschreibungen")
    print("📊 NEU: Daten direkt aus Supabase!")
    print()

    # ========================================================================
    # HAUPTMENÜ
    # ========================================================================
    print("\n" + "="*70)
    print("HAUPTMENÜ")
    print("="*70)
    print("1. Neues Modell trainieren (mit Supabase-Daten)")
    print("2. Gespeichertes Modell laden und Projekte finden")
    print("3. Beenden")

    wahl = input("\nWählen Sie (1-3): ").strip()

    if wahl == '3':
        print("\nAuf Wiedersehen!")
        return

    # ========================================================================
    # DATENQUELLE WÄHLEN
    # ========================================================================
    print("\n" + "="*70)
    print("DATENQUELLE WÄHLEN")
    print("="*70)
    print("1. Aus Supabase laden (empfohlen)")
    print("2. Aus CSV-Datei laden (legacy)")

    datenquelle = input("\nWählen Sie (1-2, default=1): ").strip() or '1'

    df = None

    if datenquelle == '1':
        # Aus Supabase laden
        print("\n" + "="*70)
        print("SUPABASE DATEN LADEN")
        print("="*70)

        try:
            loader = SupabaseLoader()

            tage_input = input("Wie viele Tage zurück laden? (default=10): ").strip()
            tage_zurueck = int(tage_input) if tage_input else 10

            print("\n💡 Tipp: Sie können die Daten bereits beim Laden filtern (schneller)")
            print("Oder leer lassen für alle Daten.")

            pre_kantone_input = input("Kantone filtern (z.B. ZH,BE) oder leer: ").strip().upper()
            pre_kantone = [k.strip() for k in pre_kantone_input.split(',') if k.strip()] if pre_kantone_input else None

            with loader:
                df = loader.lade_projekte(
                    tage_zurueck=tage_zurueck,
                    kantone=pre_kantone
                )

            if len(df) == 0:
                print("\n❌ Keine Daten gefunden!")
                return

            print(f"✓ {len(df)} Projekte aus Supabase geladen")

        except Exception as e:
            print(f"\n❌ Fehler beim Laden aus Supabase: {e}")
            print("\nTipp: Überprüfen Sie Ihre .env Datei und DATABASE_URL")
            return

    else:
        # Aus CSV laden (legacy)
        print("\n" + "="*70)
        print("CSV-DATEI LADEN")
        print("="*70)

        csv_pfad = input("Pfad zur CSV-Datei: ").strip()
        if not csv_pfad:
            csv_pfad = "simap_last10d.csv"

        if not os.path.exists(csv_pfad):
            print(f"\n❌ FEHLER: Datei nicht gefunden: {csv_pfad}")
            return

        print("\nLade Daten...")
        try:
            try:
                df = pd.read_csv(csv_pfad, sep='\t')
            except:
                df = pd.read_csv(csv_pfad, sep=',')
        except Exception as e:
            print(f"\n❌ FEHLER beim Laden: {e}")
            return

        print(f"✓ {len(df)} Projekte geladen")

    print(f"✓ Verfügbare Spalten: {', '.join(df.columns.tolist()[:5])}...")

    # ========================================================================
    # WORKFLOW 1: NEUES MODELL TRAINIEREN
    # ========================================================================
    if wahl == '1':
        klassifikator = ProjektKlassifikator()

        kriterien = interaktive_kriterien_eingabe()
        klassifikator.kriterien_config = kriterien

        print("\n" + "="*70)
        print("LABELS ERSTELLEN")
        print("="*70)

        labels = klassifikator.erstelle_labels_aus_kriterien(df, kriterien)

        n_interessant = np.sum(labels == 1)
        n_nicht = np.sum(labels == 0)

        print(f"\n✓ Interessant: {n_interessant} ({n_interessant/len(labels)*100:.1f}%)")
        print(f"✓ Nicht interessant: {n_nicht} ({n_nicht/len(labels)*100:.1f}%)")

        if n_interessant < 20:
            print("\n⚠️  WARNUNG: Sehr wenige interessante Projekte!")
            print("Das Modell braucht mindestens 20-30 positive Beispiele.")
            print("\nMöchten Sie trotzdem fortfahren? (j/n)")
            if input("> ").strip().lower() not in ['j', 'ja', 'y', 'yes']:
                return

        klassifikator.trainieren(df, labels)

        print("\n" + "="*70)
        print("MODELL SPEICHERN")
        print("="*70)
        save_path = input("Speichern unter (z.B. mein_modell.pkl): ").strip()
        if save_path:
            if not save_path.endswith('.pkl'):
                save_path += '.pkl'
            klassifikator.speichern(save_path)

        print("\nMöchten Sie direkt interessante Projekte suchen? (j/n)")
        if input("> ").strip().lower() not in ['j', 'ja', 'y', 'yes']:
            print("\nFertig! Starten Sie das Programm erneut mit Option 2.")
            return

    # ========================================================================
    # WORKFLOW 2: MODELL LADEN
    # ========================================================================
    elif wahl == '2':
        print("\n" + "="*70)
        print("MODELL LADEN")
        print("="*70)

        model_path = input("Pfad zum Modell (z.B. mein_modell.pkl): ").strip()

        if not os.path.exists(model_path):
            print(f"\n❌ FEHLER: Modell nicht gefunden: {model_path}")
            return

        klassifikator = ProjektKlassifikator()
        klassifikator.laden(model_path)

        if klassifikator.kriterien_config:
            print("\nGespeicherte Kriterien:")
            for key, value in klassifikator.kriterien_config.items():
                print(f"  {key}: {value}")

    else:
        print("\n❌ Ungültige Auswahl")
        return

    # ========================================================================
    # INTERESSANTE PROJEKTE FINDEN
    # ========================================================================
    print("\n" + "="*70)
    print("PROJEKTE SUCHEN")
    print("="*70)

    min_prob_input = input("Minimale Wahrscheinlichkeit (0.0-1.0, default 0.7): ").strip()
    min_prob = float(min_prob_input) if min_prob_input else 0.7

    top_n_input = input("Maximale Anzahl Ergebnisse (leer = alle): ").strip()
    top_n = int(top_n_input) if top_n_input else None

    print("\nSuche interessante Projekte...")
    interesting = klassifikator.finde_interessante(df, min_prob=min_prob, top_n=top_n)

    print(f"✓ {len(interesting)} Projekte mit Wahrscheinlichkeit >= {min_prob:.0%} gefunden")

    filter_config = interaktive_filter_eingabe()

    if filter_config.get('aktiv'):
        print("\nWende Filter an...")
        interesting = wende_filter_an(interesting, filter_config)
        print(f"✓ {len(interesting)} Projekte nach Filterung")

    # ========================================================================
    # ERGEBNISSE ANZEIGEN UND SPEICHERN
    # ========================================================================
    if len(interesting) > 0:
        zeige_ergebnisse(interesting, max_anzahl=10)

        print("\n" + "="*70)
        print("ERGEBNISSE SPEICHERN")
        print("="*70)

        output_file = input("Speichern unter (z.B. ergebnisse.csv): ").strip()
        if not output_file:
            output_file = "interessante_projekte.csv"

        if not output_file.endswith('.csv'):
            output_file += '.csv'

        interesting.to_csv(output_file, sep='\t', index=False)
        print(f"\n✓ {len(interesting)} Projekte gespeichert: {output_file}")
    else:
        print("\n⚠️  Keine Projekte gefunden!")
        print("\nTipps:")
        print("- Minimale Wahrscheinlichkeit senken")
        print("- Filter lockern")
        print("- Modell mit anderen Kriterien neu trainieren")

    print("\n" + "="*70)
    print("FERTIG!")
    print("="*70)


if __name__ == "__main__":
    main()
