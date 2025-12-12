# Zwei-Stufen-Filterung - Implementierung

## Überblick

Das Klassifikationssystem arbeitet jetzt mit einem **Zwei-Stufen-Filter**:

1. **STUFE 1: Harte Filter** - Eliminiert definitiv unpassende Projekte
2. **STUFE 2: ML-Evaluation** - Bewertet Keyword-Matches in Titel/Beschreibung

## Wie es funktioniert

### STUFE 1: Harte Filter (`wende_harte_filter_an()`)

Filtert Projekte basierend auf **fixen Kriterien**:

- **Kantone**: Nur spezifische Kantone (z.B. ZH, BE, AG)
- **Projekttypen**: tender (Ausschreibung), direct_award (Direktvergabe), planning_procedure (Planungsverfahren)
- **Auftragsarten**: service (Dienstleistung), construction (Bauwesen), supply (Lieferung)
- **CPV-Codes**: Common Procurement Vocabulary (z.B. 79 = Sicherheitsdienste)
- **Budget**: Min/Max Budget in CHF

**Beispiel**: Wenn du CPV-Code "79" (Sicherheit) angibst, werden **nur** Projekte mit CPV-79 durchgelassen. Alle anderen (Chemie, IT, Bau) werden **sofort eliminiert**.

### STUFE 2: ML-Evaluation (`erstelle_labels_aus_kriterien()`)

Bewertet die **verbleibenden** Projekte anhand von **Keywords**:

- Prüft Titel und Beschreibung auf Keywords
- Verwendet Sentence Transformers (paraphrase-multilingual-MiniLM-L12-v2)
- Trainiert Random Forest Classifier
- Gibt Wahrscheinlichkeit zurück (0% - 100%)

**Beispiel**: Von den gefilterten CPV-79 Projekten werden nur die mit Keywords wie "Sicherheit", "Schutz", "Überwachung" als interessant markiert.

## Geänderte Dateien

### 1. `ml/classifier.py`

#### Neue Methode: `wende_harte_filter_an()` (Zeilen 169-261)

```python
def wende_harte_filter_an(self, df, kriterien):
    """STUFE 1: Harte Filter - Eliminiert Projekte die DEFINITIV nicht passen"""
    filtered = df.copy()

    # Filter 1: Kantone
    if kriterien.get('kantone') and 'canton' in df.columns:
        filtered = filtered[filtered['canton'].isin(kriterien['kantone'])]

    # Filter 2: Projekttypen (tender, direct_award, etc.)
    if kriterien.get('projekt_typen') and 'project_type' in df.columns:
        filtered = filtered[filtered['project_type'].isin(kriterien['projekt_typen'])]

    # Filter 3: Auftragsarten (service, construction, supply)
    if kriterien.get('auftrags_arten') and 'order_type' in df.columns:
        filtered = filtered[filtered['order_type'].isin(kriterien['auftrags_arten'])]

    # Filter 4: CPV-Codes
    if kriterien.get('cpv_codes') and 'cpv_code' in df.columns:
        # Unterstützt sowohl String als auch Dictionary CPV-Formate

    # Filter 5: Budget
    if kriterien.get('min_budget') or kriterien.get('max_budget'):
        # Filtert nach Budget-Bereich

    return filtered
```

#### Geänderte Methode: `finde_interessante()` (Zeilen 335-358)

Wendet jetzt automatisch harte Filter an:

```python
def finde_interessante(self, df, min_prob=0.7, top_n=None):
    # STUFE 1: Harte Filter anwenden
    if self.kriterien_config:
        df_gefiltert = self.wende_harte_filter_an(df, self.kriterien_config)
    else:
        df_gefiltert = df

    # STUFE 2: ML-Vorhersage
    predictions, probabilities = self.vorhersagen(df_gefiltert)
    # ...
```

#### Geänderte Methode: `main()` Training Workflow (Zeilen 714-771)

Training verwendet jetzt gefilterte Daten:

```python
# STUFE 1: Harte Filter anwenden
df_gefiltert = klassifikator.wende_harte_filter_an(df, kriterien)

# STUFE 2: ML-Labels erstellen (nur für Keywords)
labels = klassifikator.erstelle_labels_aus_kriterien(df_gefiltert, kriterien)

# Training mit gefilterten Daten
klassifikator.trainieren(df_gefiltert, labels)
```

### 2. `ml/test_training.py`

Komplett überarbeitet um Zwei-Stufen-Filterung zu demonstrieren:

- Schritt 4: Wendet harte Filter an
- Schritt 5: Erstellt ML-Labels
- Schritt 6: Trainiert mit gefilterten Daten
- Schritt 8: Testet Vorhersagen mit automatischer Filterung

## Beispiel-Workflow: Securitas

```python
kriterien = {
    'kantone': ['ZH', 'BE', 'AG', 'SG', 'VD'],
    'projekt_typen': ['tender'],           # Nur Ausschreibungen
    'auftrags_arten': ['service'],         # Nur Dienstleistungen
    'cpv_codes': ['79'],                   # Nur Sicherheitsdienste
    'keywords': ['Sicherheit', 'Schutz', 'Überwachung', 'Security']
}
```

### Was passiert:

1. **STUFE 1**: Von 4815 Projekten bleiben ~50 nach harten Filtern
   - ❌ Chemie-Projekte (falscher CPV-Code)
   - ❌ Bauprojekte (falsche Auftragsart)
   - ❌ Abgeschlossene Ausschreibungen (falscher Projekttyp)
   - ❌ Kantone ausserhalb der Liste
   - ✅ Nur CPV-79, service, tender, in ZH/BE/AG/SG/VD

2. **STUFE 2**: Von den 50 gefilterten Projekten werden 20 als interessant markiert
   - Keywords "Sicherheit", "Schutz" etc. im Titel/Beschreibung gefunden
   - ML-Modell gibt Wahrscheinlichkeit: 70% - 95%

## Vorteile

### Vorher (alte Version):
- ❌ Chemie-Projekte bei Sicherheits-Keywords
- ❌ Abgeschlossene Ausschreibungen statt aktive Tenders
- ❌ Falsche Projekttypen (construction statt service)
- ❌ ML-Modell musste zu viel "raten"

### Jetzt (Zwei-Stufen-Filter):
- ✅ Nur relevante Projekttypen (tender, service, CPV-79)
- ✅ ML-Modell bewertet nur noch Keywords
- ✅ Keine "intelligenten" Fehler mehr
- ✅ Klare, vorhersagbare Ergebnisse

## Verwendung

### Training:

```bash
cd ml
python classifier.py
```

1. Wähle "1. Neues Modell trainieren"
2. Gib Kriterien ein:
   - Kantone: ZH, BE, AG
   - CPV-Codes: 79 (für Sicherheit)
   - Projekttypen: tender
   - Auftragsarten: service
   - Keywords: Sicherheit, Schutz, Überwachung

3. System wendet automatisch Zwei-Stufen-Filter an

### Test:

```bash
cd ml
python test_training.py
```

Zeigt die Funktionsweise beider Stufen.

## Wichtige Hinweise

1. **Harte Filter sind streng**: Wenn CPV-79 angegeben wird, kommen **nur** CPV-79 Projekte durch
2. **Keywords sind flexibel**: ML-Modell bewertet semantische Ähnlichkeit
3. **Beide Klassen nötig**: Modell braucht interessante UND nicht-interessante Projekte
4. **Spezifische Keywords**: "Sicherheit" ist besser als "Schutz" alleine

## Nächste Schritte

Das System ist jetzt einsatzbereit. Teste es mit:

```bash
python ml/test_training.py
```

Oder verwende das interaktive Training:

```bash
python ml/classifier.py
```
