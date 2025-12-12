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
import sys
from pathlib import Path

# Füge den ml/algorithm Pfad hinzu
sys.path.append(str(Path(__file__).parent / "algorithm"))
from supabase_api_loader import SupabaseAPILoader, lade_aus_supabase_api, teste_supabase_api
from supabase_storage_handler import SupabaseStorageHandler, lade_modell_von_storage, speichere_modell_zu_storage
warnings.filterwarnings('ignore')


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
        """Erstellt komplette Feature-Matrix mit starker Gewichtung auf Keywords und CPV"""
        embeddings = self.erstelle_embeddings(df['combined_text'].tolist())
        categorical = self.encodiere_kategorien(df, fit=fit)

        # Berechne Keyword-Scores als zusätzliche Features
        keyword_features = np.zeros((len(df), 2))  # [title_score, description_score]

        if self.kriterien_config.get('keywords'):
            print("Berechne Keyword-Matching-Scores...")
            for i, (idx, row) in enumerate(df.iterrows()):
                title_score = self.berechne_keyword_score(
                    str(row.get('title', '')),
                    self.kriterien_config['keywords']
                )
                desc_score = self.berechne_keyword_score(
                    str(row.get('description', '')),
                    self.kriterien_config['keywords']
                )
                keyword_features[i] = [title_score, desc_score]

        # WICHTIG: Gewichte die Features unterschiedlich!
        # Embeddings (semantisches Verständnis) - Gewicht: 0.3
        embeddings_weighted = embeddings * 0.3

        # Kategoriale Features (CPV-Codes, Kantone, etc.) - Gewicht: 2.0 (sehr wichtig!)
        if categorical.shape[1] > 0:
            categorical_weighted = categorical * 2.0
        else:
            categorical_weighted = categorical

        # Keywords - Gewicht: 5.0 (am wichtigsten!)
        keyword_features_weighted = keyword_features * 5.0

        # Kombiniere alle Features
        if categorical.shape[1] > 0:
            features = np.hstack([embeddings_weighted, categorical_weighted, keyword_features_weighted])
        else:
            features = np.hstack([embeddings_weighted, keyword_features_weighted])

        print(f"Feature-Matrix: {features.shape}")
        print(f"  Embeddings (30% Gewicht), Kategorien (200% Gewicht), Keywords (500% Gewicht)")
        return features

    def wende_harte_filter_an(self, df, kriterien):
        """
        STUFE 1: Harte Filter - Eliminiert Projekte die DEFINITIV nicht passen
        Returns: Gefiltertes DataFrame
        """
        print("\n" + "="*70)
        print("STUFE 1: HARTE FILTER")
        print("="*70)

        filtered = df.copy()
        original_count = len(filtered)

        # FILTER 1: Kantone (HART)
        if kriterien.get('kantone') and 'canton' in df.columns:
            filtered = filtered[filtered['canton'].isin(kriterien['kantone'])]
            print(f"✓ Kanton-Filter: {len(filtered)}/{original_count} Projekte übrig")

        # FILTER 2: Projekttypen (HART) - z.B. nur "tender"
        if kriterien.get('projekt_typen') and 'project_type' in df.columns:
            filtered = filtered[filtered['project_type'].isin(kriterien['projekt_typen'])]
            print(f"✓ Projekttyp-Filter: {len(filtered)}/{original_count} Projekte übrig")

        # FILTER 3: Auftragsarten (HART) - z.B. nur "service"
        if kriterien.get('auftrags_arten') and 'order_type' in df.columns:
            filtered = filtered[filtered['order_type'].isin(kriterien['auftrags_arten'])]
            print(f"✓ Auftragsart-Filter: {len(filtered)}/{original_count} Projekte übrig")

        # FILTER 4: CPV-Codes (HART) - z.B. nur "79"
        if kriterien.get('cpv_codes') and 'cpv_code' in df.columns:
            cpv_mask = pd.Series([False] * len(filtered), index=filtered.index)
            for code in kriterien['cpv_codes']:
                # Prüfe ob cpv_code ein Dictionary ist (nested structure)
                if filtered['cpv_code'].dtype == 'object':
                    # Versuche als String oder Dictionary zu behandeln
                    cpv_mask |= filtered['cpv_code'].astype(str).str.contains(str(code), na=False)
                else:
                    cpv_mask |= filtered['cpv_code'].astype(str).str.startswith(str(code), na=False)
            filtered = filtered[cpv_mask]
            print(f"✓ CPV-Code-Filter: {len(filtered)}/{original_count} Projekte übrig")

        # FILTER 5: Budget (HART)
        if 'estimated_amount' in df.columns:
            if kriterien.get('min_budget'):
                filtered = filtered[filtered['estimated_amount'] >= kriterien['min_budget']]
                print(f"✓ Min-Budget-Filter: {len(filtered)}/{original_count} Projekte übrig")
            if kriterien.get('max_budget'):
                filtered = filtered[(filtered['estimated_amount'] <= kriterien['max_budget']) 
                                  (filtered['estimated_amount'] > 0)]
                print(f"✓ Max-Budget-Filter: {len(filtered)}/{original_count} Projekte übrig")

        print(f"\n→ {len(filtered)}/{original_count} Projekte nach harten Filtern")
        return filtered

    def erstelle_labels_aus_kriterien(self, df, kriterien):
        """
        STUFE 2: ML-Labels - NUR für Keywords/Text-Matching
        Wird auf BEREITS GEFILTERTE Daten angewendet!
        """
        labels = np.zeros(len(df), dtype=int)

        # NUR Keywords für ML-Bewertung - Rest wurde schon hart gefiltert!
        if kriterien.get('keywords'):
            print("\n" + "="*70)
            print("STUFE 2: ML-BEWERTUNG (Keywords in Titel/Beschreibung)")
            print("="*70)

            keyword_scores = []
            for i, (idx, row) in enumerate(df.iterrows()):
                title_score = self.berechne_keyword_score(
                    str(row.get('title', '')),
                    kriterien['keywords']
                )
                desc_score = self.berechne_keyword_score(
                    str(row.get('description', '')),
                    kriterien['keywords']
                )

                total_score = title_score * 2.0 + desc_score
                keyword_scores.append(total_score)

                # Wenn guter Keyword-Match, als interessant markieren
                if total_score > 0.5:  # Schwelle gesenkt - Rest wurde ja schon gefiltert
                    labels[i] = 1  # Verwende i (0-basierter Index) statt idx (DataFrame-Index)

            # Statistik
            n_matched = np.sum(labels == 1)
            n_total = len(labels)
            print(f"  Keywords gefunden in: {n_matched}/{n_total} Projekten ({n_matched/n_total*100:.1f}%)")
        else:
            # Keine Keywords? Dann alles als interessant markieren (wurde ja hart gefiltert)
            labels = np.ones(len(df), dtype=int)

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
            n_estimators=222,  # Mehr Bäume für bessere Performance
            max_depth=25,
            min_samples_split=5,
            min_samples_leaf=2,
            random_state=42,
            n_jobs=-1,
            class_weight='balanced'  # Wichtig für unbalancierte Daten
        )
        self.rf_classifier.fit(X_train, y_train)

        y_pred = self.rf_classifier.predict(X_test)
        accuracy = accuracy_score(y_test, y_pred)

        print("\n" + "="*70)
        print("TRAINING ABGESCHLOSSEN")
        print("="*70)
        print(f"\nAccuracy: {accuracy:.2%}")

        # Classification Report nur wenn beide Klassen vorhanden
        unique_classes = np.unique(np.concatenate([y_test, y_pred]))
        if len(unique_classes) >= 2:
            print("\nClassification Report:")
            print(classification_report(y_test, y_pred,
                                       target_names=['Nicht interessant', 'Interessant']))
        else:
            print("\n⚠️  Nur eine Klasse im Test-Set - Classification Report übersprungen")
            print(f"   Vorhandene Klasse: {'Interessant' if unique_classes[0] == 1 else 'Nicht interessant'}")

        return accuracy

    def vorhersagen(self, df):
        """Macht Vorhersagen"""
        if self.rf_classifier is None:
            raise ValueError("Modell muss erst trainiert oder geladen werden!")

        df = self.daten_vorbereiten(df)
        X = self.erstelle_features(df, fit=False)
        predictions = self.rf_classifier.predict(X)

        # Prüfe ob beide Klassen vorhanden sind
        proba = self.rf_classifier.predict_proba(X)
        if proba.shape[1] == 2:
            # Normal: beide Klassen (0 und 1)
            probabilities = proba[:, 1]
        else:
            # Nur eine Klasse trainiert - verwende diese Wahrscheinlichkeit
            probabilities = proba[:, 0]
            print("\n⚠️  Warnung: Modell kennt nur eine Klasse!")
            print("    Empfehlung: Trainiere das Modell neu mit spezifischeren Kriterien.")

        return predictions, probabilities

    def finde_interessante(self, df, min_prob=0.7, top_n=None):
        """
        Findet interessante Projekte mit 2-Stufen-Filterung:
        1. Harte Filter (CPV, Kanton, Typ, etc.)
        2. ML-Vorhersage (Keywords/Text-Match)
        """
        print("\n[STUFE 1] Wende harte Filter an...")
        if self.kriterien_config:
            df_gefiltert = self.wende_harte_filter_an(df, self.kriterien_config)
            print(f"  {len(df)} → {len(df_gefiltert)} Projekte (nach harten Filtern)")
        else:
            df_gefiltert = df
            print("  (Keine Kriterien gespeichert - überspringe harte Filter)")

        if len(df_gefiltert) == 0:
            print("  ⚠️  Keine Projekte nach harten Filtern - Kriterien zu streng!")
            return pd.DataFrame()

        print("\n[STUFE 2] Führe ML-Vorhersage durch...")
        predictions, probabilities = self.vorhersagen(df_gefiltert)

        result_df = df_gefiltert.copy()
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

    def speichern(self, pfad, zu_supabase=False, bucket_name="models"):
        """
        Speichert das Modell lokal oder zu Supabase Storage

        Args:
            pfad: Lokaler Pfad oder Remote-Pfad (z.B. "production/model_v1.pkl")
            zu_supabase: True = zu Supabase Storage hochladen, False = lokal speichern
            bucket_name: Supabase Bucket Name (default: "models")
        """
        if self.rf_classifier is None:
            raise ValueError("Kein Modell zum Speichern!")

        model_data = {
            'rf_classifier': self.rf_classifier,
            'label_encoders': self.label_encoders,
            'kriterien_config': self.kriterien_config
        }

        if zu_supabase:
            # Speichere direkt zu Supabase Storage
            if speichere_modell_zu_storage(model_data, pfad, bucket_name):
                print(f"✓ Modell zu Supabase Storage gespeichert: {bucket_name}/{pfad}")
            else:
                raise Exception("Fehler beim Speichern zu Supabase Storage")
        else:
            # Speichere lokal
            joblib.dump(model_data, pfad)
            print(f"✓ Modell lokal gespeichert: {pfad}")

    def laden(self, pfad, von_supabase=False, bucket_name="models"):
        """
        Lädt ein gespeichertes Modell von lokal oder Supabase Storage

        Args:
            pfad: Lokaler Pfad oder Remote-Pfad (z.B. "production/model_v1.pkl")
            von_supabase: True = von Supabase Storage laden, False = lokal laden
            bucket_name: Supabase Bucket Name (default: "models")
        """
        if von_supabase:
            # Lade von Supabase Storage
            model_data = lade_modell_von_storage(pfad, bucket_name)
            if model_data is None:
                raise Exception("Fehler beim Laden von Supabase Storage")
            print(f"✓ Modell von Supabase Storage geladen: {bucket_name}/{pfad}")
        else:
            # Lade lokal
            model_data = joblib.load(pfad)
            print(f"✓ Modell lokal geladen: {pfad}")

        self.rf_classifier = model_data['rf_classifier']
        self.label_encoders = model_data['label_encoders']
        self.kriterien_config = model_data.get('kriterien_config', {})

    def lade_daten_von_supabase(self, tage_zurueck=10, kantone=None, projekt_typen=None, auftrags_arten=None):
        """Lädt Daten direkt aus Supabase"""
        print(f"\nLade Daten aus Supabase (letzte {tage_zurueck} Tage)...")

        try:
            loader = SupabaseAPILoader()
            df = loader.lade_projekte(
                tage_zurueck=tage_zurueck,
                kantone=kantone,
                projekt_typen=projekt_typen,
                auftrags_arten=auftrags_arten
            )

            if len(df) > 0:
                print(f"✓ {len(df)} Projekte aus Supabase geladen")
            else:
                print("⚠ Keine Projekte gefunden")

            return df
        except Exception as e:
            print(f"❌ Fehler beim Laden aus Supabase: {e}")
            return pd.DataFrame()


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

    # Schlüsselwörter - VERBESSERT!
    print("\n" + "─" * 70)
    print("SCHLÜSSELWÖRTER / PROJEKT-TITEL (⭐ WICHTIG!)")
    print("\nGeben Sie Projekte ein, die Sie bereits haben oder gerne möchten:")
    print("\n📋 Trennzeichen-Optionen:")
    print("  1. Komma (,):        brücke,tunnel,Sanierung Hauptstrasse")
    print("  2. Semikolon (;):    brücke;tunnel;Sanierung Hauptstrasse")
    print("  3. Neue Zeile:       Jeder Eintrag auf eigener Zeile (Ende mit leerer Zeile)")
    print("  4. Mit Quotes ('):   brücke,'Sanierung, Umbau Brücke',tunnel")

    trennung = input("\nWelche Trennung? (1=Komma, 2=Semikolon, 3=Zeilen, Enter=Komma): ").strip()

    kriterien['keywords'] = []

    if trennung == '3':
        # Mehrzeilige Eingabe
        print("\nGeben Sie Keywords/Titel ein (leere Zeile zum Beenden):")
        while True:
            line = input("  > ").strip()
            if not line:
                break
            kriterien['keywords'].append(line)
    else:
        # Einzeilige Eingabe mit Trennzeichen
        if trennung == '2':
            separator = ';'
            print("\nEingabe (Semikolon-getrennt):")
        else:
            separator = ','
            print("\nEingabe (Komma-getrennt):")

        keywords_input = input("> ").strip()

        if keywords_input:
            # Parse mit Quote-Support
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

    # Kantone
    print("\nFilter nach Kantonen?")
    kantone = input("Komma-getrennt oder leer: ").strip().upper()
    if kantone:
        filter_config['kantone'] = [k.strip() for k in kantone.split(',') if k.strip()]

    # Projekttypen
    print("\nFilter nach Projekttypen?")
    typen = input("Komma-getrennt oder leer: ").strip().lower()
    if typen:
        filter_config['projekt_typen'] = [t.strip() for t in typen.split(',') if t.strip()]

    # Auftragsarten
    print("\nFilter nach Auftragsarten?")
    arten = input("Komma-getrennt oder leer: ").strip().lower()
    if arten:
        filter_config['auftrags_arten'] = [a.strip() for a in arten.split(',') if a.strip()]

    # Keywords
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

    # Kantone
    if filter_config.get('kantone') and 'canton' in filtered.columns:
        filtered = filtered[filtered['canton'].isin(filter_config['kantone'])]
        print(f"  Nach Kanton-Filter: {len(filtered)} ({len(filtered)-original_count:+d})")

    # Projekttypen
    if filter_config.get('projekt_typen') and 'project_type' in filtered.columns:
        filtered = filtered[filtered['project_type'].isin(filter_config['projekt_typen'])]
        print(f"  Nach Projekttyp-Filter: {len(filtered)}")

    # Auftragsarten
    if filter_config.get('auftrags_arten') and 'order_type' in filtered.columns:
        filtered = filtered[filtered['order_type'].isin(filter_config['auftrags_arten'])]
        print(f"  Nach Auftragsart-Filter: {len(filtered)}")

    # Keywords
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

        # Zeige Keyword-Score wenn verfügbar
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
    print("PROJEKT-KLASSIFIKATOR - SUPABASE-VERSION")
    print("="*70)
    print("ML-basierte Identifikation interessanter Ausschreibungen")
    print("🎯 Direkte Anbindung an Supabase-Datenbank!")
    print()

    # ========================================================================
    # HAUPTMENÜ
    # ========================================================================
    print("\n" + "="*70)
    print("HAUPTMENÜ")
    print("="*70)
    print("1. Neues Modell trainieren")
    print("2. Gespeichertes Modell laden und Projekte finden")
    print("3. Beenden")

    wahl = input("\nWählen Sie (1-3): ").strip()

    if wahl == '3':
        print("\nAuf Wiedersehen!")
        return

    # ========================================================================
    # DATEN AUS SUPABASE LADEN
    # ========================================================================
    print("\n" + "="*70)
    print("DATEN AUS SUPABASE LADEN")
    print("="*70)

    # Teste Verbindung
    print("\nTeste Supabase-Verbindung...")
    if not teste_supabase_api():
        print("❌ Supabase-Verbindung fehlgeschlagen!")
        print("Bitte prüfe deine .env Datei:")
        print("  SUPABASE_URL=https://xxx.supabase.co")
        print("  SUPABASE_KEY=dein-anon-key")
        return

    tage = input("\nWie viele Tage zurück laden? (default: 10): ").strip()
    tage_zurueck = int(tage) if tage else 10

    # Temporärer Klassifikator zum Laden
    temp_klassifikator = ProjektKlassifikator()
    df = temp_klassifikator.lade_daten_von_supabase(tage_zurueck=tage_zurueck)

    if len(df) == 0:
        print("\n❌ FEHLER: Keine Daten aus Supabase geladen")
        return

    print(f"✓ {len(df)} Projekte geladen")
    print(f"✓ Spalten: {', '.join(df.columns.tolist()[:5])}...")

    # ========================================================================
    # WORKFLOW 1: NEUES MODELL TRAINIEREN
    # ========================================================================
    if wahl == '1':
        klassifikator = ProjektKlassifikator()

        # Kriterien eingeben
        kriterien = interaktive_kriterien_eingabe()
        klassifikator.kriterien_config = kriterien

        # ====================================================================
        # STUFE 1: HARTE FILTER ANWENDEN
        # ====================================================================
        print("\n" + "="*70)
        print("STUFE 1: HARTE FILTER ANWENDEN")
        print("="*70)
        print("Filtere nach: Kanton, Projekttyp, Auftragsart, CPV-Code, Budget")

        df_gefiltert = klassifikator.wende_harte_filter_an(df, kriterien)

        print(f"\n✓ Originale Projekte: {len(df)}")
        print(f"✓ Nach harten Filtern: {len(df_gefiltert)}")
        print(f"✓ Reduziert um: {len(df) - len(df_gefiltert)} Projekte ({(1 - len(df_gefiltert)/len(df))*100:.1f}%)")

        if len(df_gefiltert) < 50:
            print("\n⚠️  WARNUNG: Sehr wenige Projekte nach Filterung!")
            print("Die harten Filter sind sehr streng - das Modell hat wenig Trainingsdaten.")
            print("\nMöchten Sie die Kriterien lockern? (j/n)")
            if input("> ").strip().lower() in ['j', 'ja', 'y', 'yes']:
                return

        # ====================================================================
        # STUFE 2: ML-LABELS ERSTELLEN (nur für Keywords)
        # ====================================================================
        print("\n" + "="*70)
        print("STUFE 2: ML-LABELS ERSTELLEN")
        print("="*70)
        print("Bewerte Titel/Beschreibung anhand von Keywords")

        labels = klassifikator.erstelle_labels_aus_kriterien(df_gefiltert, kriterien)

        n_interessant = np.sum(labels == 1)
        n_nicht = np.sum(labels == 0)

        print(f"\n✓ Interessant (Keywords passen): {n_interessant} ({n_interessant/len(labels)*100:.1f}%)")
        print(f"✓ Nicht interessant (Keywords fehlen): {n_nicht} ({n_nicht/len(labels)*100:.1f}%)")

        if n_interessant < 20:
            print("\n⚠️  WARNUNG: Sehr wenige interessante Projekte!")
            print("Das Modell braucht mindestens 20-30 positive Beispiele.")
            print("\nMöchten Sie trotzdem fortfahren? (j/n)")
            if input("> ").strip().lower() not in ['j', 'ja', 'y', 'yes']:
                return

        if n_nicht < 10:
            print("\n⚠️  WARNUNG: Zu wenige NICHT-interessante Projekte!")
            print("Das Modell braucht beide Klassen zum Trainieren.")
            print("Problem: Deine Keywords sind zu breit - fast alles passt.")
            print("\nTipps:")
            print("- Verwende spezifischere Keywords")
            print("- Kombiniere mehrere Keywords mit UND-Logik")
            print("\nMöchten Sie die Kriterien neu eingeben? (j/n)")
            if input("> ").strip().lower() in ['j', 'ja', 'y', 'yes']:
                return
            print("\nFahre trotzdem fort (kann zu schlechten Ergebnissen führen)...")

        # Training mit gefilterten Daten
        klassifikator.trainieren(df_gefiltert, labels)

        # Modell speichern
        print("\n" + "="*70)
        print("MODELL SPEICHERN")
        print("="*70)
        save_path = input("Speichern unter (z.B. mein_modell.pkl): ").strip()
        if save_path:
            if not save_path.endswith('.pkl'):
                save_path += '.pkl'
            klassifikator.speichern(save_path)

        # Weiter zu Vorhersagen?
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

    # Zusätzliche Filter
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

        # Speichern
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
