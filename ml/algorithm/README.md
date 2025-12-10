# SIMAP Projekt-Klassifikator

ML-basierte Identifikation interessanter Ausschreibungen mit Supabase-Integration.

## 🚀 Quick Start

### 1. Environment Setup

```bash
# .env Datei erstellen
cp ../../.env.example ../../.env

# .env bearbeiten und DATABASE_URL eintragen
# DATABASE_URL=postgresql://postgres:DEIN_PASSWORT@db.xyz.supabase.co:5432/postgres
```

### 2. Dependencies installieren

```bash
# Im Projekt-Root
pip install -r requirements.txt
```

> **Hinweis**: Installation kann einige Minuten dauern (PyTorch, sentence-transformers)

### 3. Model testen

```bash
# Test-Suite ausführen
python ml/algorithm/test_model.py
```

**Das Test-Script prüft:**
- ✅ .env Konfiguration
- ✅ Supabase-Verbindung
- ✅ Daten laden
- ✅ Model Initialisierung
- ✅ Feature-Erstellung
- ✅ Filter-Funktionen

### 4. Model verwenden

```bash
# Interaktives Programm starten
python ml/algorithm/model.py
```

## 📖 Verwendung

### Interaktiver Modus

```bash
python ml/algorithm/model.py
```

Das Programm führt dich durch:
1. **Datenquelle wählen** (Supabase oder CSV)
2. **Kriterien definieren** (Kantone, Keywords, Budget, etc.)
3. **Model trainieren** oder gespeichertes Model laden
4. **Interessante Projekte finden**
5. **Ergebnisse exportieren**

### Programmatische Verwendung

```python
from ml.algorithm.model import SupabaseLoader, ProjektKlassifikator

# 1. Daten aus Supabase laden
with SupabaseLoader() as db:
    df = db.lade_projekte(
        tage_zurueck=10,
        kantone=['ZH', 'BE'],  # optional
    )

# 2. Model initialisieren
klassifikator = ProjektKlassifikator()

# 3. Kriterien definieren
kriterien = {
    'kantone': ['ZH', 'BE', 'GR'],
    'keywords': ['brücke', 'tunnel', 'sanierung'],
    'min_budget': 100000,
    'projekt_typen': ['tender']
}
klassifikator.kriterien_config = kriterien

# 4. Labels erstellen und trainieren
labels = klassifikator.erstelle_labels_aus_kriterien(df, kriterien)
klassifikator.trainieren(df, labels)

# 5. Model speichern
klassifikator.speichern('mein_modell.pkl')

# 6. Interessante Projekte finden
interessante = klassifikator.finde_interessante(df, min_prob=0.7)
print(f"Gefunden: {len(interessante)} interessante Projekte")
```

## 🔧 Konfiguration

### Supabase Connection

Die `DATABASE_URL` findest du hier:
1. Gehe zu [supabase.com](https://supabase.com)
2. Öffne dein Projekt
3. Settings → Database → Connection String → URI
4. Kopiere die URL und ersetze `[YOUR-PASSWORD]`

### Kriterien

**Verfügbare Kriterien:**
- `kantone`: Liste von Kantonen (z.B. `['ZH', 'BE']`)
- `projekt_typen`: `['tender', 'direct_award', 'planning_procedure']`
- `auftrags_arten`: `['construction', 'service', 'supply']`
- `keywords`: Liste von Suchbegriffen/Projekttiteln
- `min_budget`: Minimales Budget in CHF
- `max_budget`: Maximales Budget in CHF
- `cpv_codes`: CPV-Branchencodes (z.B. `['45', '71']`)

## 📊 Model Features

### Text Embeddings
- Nutzt `sentence-transformers` für semantische Textanalyse
- Model: `paraphrase-multilingual-MiniLM-L12-v2`
- Unterstützt Deutsch, Französisch, Italienisch

### Keyword-Matching
- Intelligentes Keyword-Scoring
- Exakte Titel-Matches: sehr hoch gewichtet
- Phrasen: hoch gewichtet
- Einzelwörter: moderat gewichtet

### Random Forest Classifier
- 222 Bäume (optimal für diesen Use-Case)
- Class-balancing für unbalancierte Daten
- Feature-Kombination: Embeddings + Kategorien + Keywords

## 🐛 Troubleshooting

### `DATABASE_URL nicht gefunden`
→ Erstelle eine `.env` Datei im Projekt-Root mit `DATABASE_URL=...`

### `Verbindung fehlgeschlagen`
→ Prüfe Passwort, Internetverbindung und Supabase-Status

### `Keine Projekte gefunden`
→ Erhöhe `tage_zurueck` oder prüfe ob Daten in Supabase vorhanden sind

### `Model braucht zu lange`
→ Reduziere Datenmenge mit Filtern beim Laden oder nutze weniger Daten zum Training

### `Zu wenige interessante Projekte`
→ Erweitere deine Kriterien (mehr Keywords, mehr Kantone)

## 📁 Dateistruktur

```
ml/algorithm/
├── model.py          # Hauptprogramm (Klassifikator + Supabase)
├── test_model.py     # Test-Suite
└── README.md         # Diese Datei
```

## 🔄 Workflow

```
┌─────────────────┐
│  Supabase DB    │
│  (PostgreSQL)   │
└────────┬────────┘
         │ SupabaseLoader
         │ .lade_projekte()
         ▼
┌─────────────────┐
│  DataFrame      │
│  (Pandas)       │
└────────┬────────┘
         │ ProjektKlassifikator
         │ .erstelle_labels_aus_kriterien()
         ▼
┌─────────────────┐
│  Labels         │
│  (0/1 Array)    │
└────────┬────────┘
         │ .trainieren()
         ▼
┌─────────────────┐
│  Trained Model  │
│  (RandomForest) │
└────────┬────────┘
         │ .finde_interessante()
         ▼
┌─────────────────┐
│  Results        │
│  (CSV Export)   │
└─────────────────┘
```

## 💡 Tipps

1. **Erste Schritte**: Starte mit `test_model.py` um alles zu prüfen
2. **Training**: Braucht mindestens 20-30 positive Beispiele
3. **Keywords**: Je spezifischer, desto besser (z.B. "Sanierung Brücke" statt nur "Brücke")
4. **Performance**: Filter schon beim Laden anwenden (schneller als nachträgliches Filtern)
5. **Model Speichern**: Gespeicherte Models können wiederverwendet werden

## 📝 Beispiel Session

```bash
# 1. Test
$ python ml/algorithm/test_model.py
✓ DATABASE_URL gefunden
✓ Verbindung zu Supabase hergestellt
✓ 156 Projekte geladen
✓ Model erfolgreich initialisiert
✓ ALLE KRITISCHEN TESTS BESTANDEN!

# 2. Training
$ python ml/algorithm/model.py
> Wählen Sie (1-3): 1
> Wählen Sie (1-2): 1
> Wie viele Tage zurück laden? 30
✓ 456 Projekte aus Supabase geladen

# Kriterien eingeben...
> Kantone: ZH,BE
> Keywords: brücke,tunnel,sanierung

✓ Labels erstellt: 45 interessant (9.9%)
✓ Training abgeschlossen
✓ Accuracy: 89.2%

# 3. Model verwenden
> Minimale Wahrscheinlichkeit: 0.7
✓ 23 Projekte gefunden

TOP 10 INTERESSANTE PROJEKTE
──────────────────────────────
Titel: Sanierung Brücke XY
Match-Score: 94.2% | Keyword-Score: 8.5 ⭐
...
```

## 🆘 Support

Bei Problemen:
1. Führe `test_model.py` aus und prüfe welcher Test fehlschlägt
2. Prüfe die Fehlermeldung
3. Konsultiere Troubleshooting-Sektion oben
