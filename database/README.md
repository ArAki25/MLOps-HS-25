# Database Loader - SIMAP Daten für Machine Learning

Dieser Ordner enthält alle Funktionen zum Laden von SIMAP-Daten aus der Supabase-Datenbank direkt in Pandas DataFrames für dein Machine Learning Modell.

## 📦 Komponenten

- **`loader.py`** - Hauptmodul mit allen Loader-Funktionen
- **`__init__.py`** - Öffentliche API
- **`example_load.py`** - Beispiele für verschiedene Anwendungsfälle

## 🚀 Schnelstart

### 1. Dependencies installieren

```bash
pip install -r ../requirements.txt
```

### 2. .env Datei konfigurieren

```bash
# .env
DATABASE_URL=postgresql://user:password@db.supabase.co/postgres
```

### 3. Daten laden

```python
from database import load_all_data, load_with_filters

# Alle Daten (limitiert)
df = load_all_data(limit=5000)

# Mit Filtern
df = load_with_filters(
    cantons=['ZH', 'BE'],
    publication_types=['award'],
    min_amount=100000,
    limit=10000
)
```

## 📊 Verfügbare Funktionen

### Einfache Loader

#### `load_all_data(limit=None)`
Lädt alle Projekte mit optionalem Limit.

```python
df = load_all_data(limit=10000)
```

#### `load_by_canton(canton, limit=None)`
Lädt Daten für einen bestimmten Kanton.

```python
df_zh = load_by_canton('ZH')
df_bs = load_by_canton('BS', limit=1000)
```

#### `load_by_publication_type(pub_type, limit=None)`
Lädt Daten nach Publikationstyp.

```python
df_tender = load_by_publication_type('tender')     # Ausschreibungen
df_awards = load_by_publication_type('award')       # Zuschläge
```

#### `load_by_date_range(start_date, end_date=None, limit=None)`
Lädt Daten innerhalb eines Datumsbereichs.

```python
from datetime import datetime, timedelta

# Letzte 30 Tage
start = datetime.now() - timedelta(days=30)
df = load_by_date_range(start)

# Spezifischer Zeitraum
start = datetime(2024, 1, 1)
end = datetime(2024, 12, 31)
df = load_by_date_range(start, end)
```

#### `load_award_data(limit=None)`
Lädt nur Projekte mit Zuschlag-Informationen.

```python
df_awards = load_award_data(limit=5000)
```

### Flexible Filter

#### `load_with_filters(...)`
Die Hauptfunktion für komplexe Anfragen.

```python
df = load_with_filters(
    cantons=['ZH', 'BL', 'BS'],                    # Kantone
    publication_types=['tender', 'award'],         # Publikationstypen
    process_types=['open', 'selective'],           # Prozesstypen
    languages=['de', 'en'],                        # Sprachen
    min_amount=50000,                              # Min. Betrag
    max_amount=500000,                             # Max. Betrag
    limit=10000                                    # Limit
)
```

### Statistiken

#### `get_statistics()`
Gibt Statistiken über die Datenbank.

```python
from database.loader import get_statistics

stats = get_statistics()
print(f"Totale Projekte: {stats['total_projects']}")
print(f"Mit Awards: {stats['with_awards']}")
print(f"Summe Ausschreibungen: CHF {stats['total_estimated_amount']:,.0f}")
```

## 💡 Praktische Beispiele

### Beispiel 1: Alle Awards >CHF 100'000

```python
from database import load_with_filters

df = load_with_filters(
    publication_types=['award'],
    min_amount=100000,
    limit=5000
)

print(f"Anzahl: {len(df)}")
print(f"Durchschnitt: CHF {df['award_amount'].mean():,.0f}")
```

### Beispiel 2: Offene Ausschreibungen in Zürich

```python
df = load_with_filters(
    cantons=['ZH'],
    publication_types=['tender'],
    process_types=['open'],
    limit=3000
)

print(df[['title', 'estimated_amount', 'submission_deadline']].head())
```

### Beispiel 3: Daten für ML-Training vorbereiten

```python
from database import load_with_filters
import pandas as pd

# Daten laden
df = load_with_filters(
    publication_types=['award'],
    min_amount=10000,
    limit=10000
)

# Numerische Features auswählen
numeric_features = ['estimated_amount', 'number_of_submissions', 'award_amount']
X = df[numeric_features].fillna(0)

# Target
y = df['award_amount']

# Mit scikit-learn trainieren
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)
model = RandomForestRegressor()
model.fit(X_train, y_train)
```

### Beispiel 4: Daten mit verschiedenen Quellen kombinieren

```python
from database import load_by_canton
import pandas as pd

# Daten für mehrere Kantone laden und kombinieren
dfs = []
for canton in ['ZH', 'BE', 'BS', 'BL', 'AG']:
    df = load_by_canton(canton, limit=1000)
    dfs.append(df)

df_combined = pd.concat(dfs, ignore_index=True)
print(f"Kombiniertes Dataset: {len(df_combined)} Zeilen")
```

## 🔍 Verfügbare Spalten

Das DataFrame enthält folgende Spalten:

### Identifikation
- `project_id` - Projekt-ID
- `publication_id` - Publikations-ID
- `project_number` - Projektnummer
- `publication_number` - Publikationsnummer

### Projektinformation
- `title` - Titel
- `description` - Beschreibung
- `publication_date` - Publikationsdatum
- `publication_type` - Art (tender, award, cancellation)
- `project_type` - Projekttyp
- `project_subtype` - Projektsubtyp

### Standort
- `canton` - Kanton
- `city` - Stadt
- `postal_code` - Postleitzahl
- `country` - Land

### Finanziell
- `estimated_amount` - Geschätzte Summe
- `estimated_currency` - Währung
- `award_amount` - Zuschlag-Summe
- `award_currency` - Zuschlag-Währung

### Prozess
- `submission_deadline` - Submission Frist
- `process_type` - Prozesstyp (open, selective, invitation)
- `lots_type` - Los-Typ
- `number_of_submissions` - Anzahl Einreichungen

### Winner/Award
- `award_decision_date` - Zuschlag-Datum
- `winner_name` - Name des Gewinners
- `winner_city` - Stadt des Gewinners
- `winner_canton` - Kanton des Gewinners
- `winner_country` - Land des Gewinners

### Klassifizierung
- `cpv_code` - CPV-Code
- `additional_cpv_codes` - Zusätzliche CPV-Codes
- `bkp_codes` - BKP-Codes
- `npk_codes` - NPK-Codes

### Sonstiges
- `contracting_authority` - Auftraggeber
- `order_type` - Bestelltyp
- `construction_type` - Bautyp
- `creation_language` - Sprache
- `created_at` - Erstellt am
- `updated_at` - Aktualisiert am

## ⚙️ Erweiterte Konfiguration

### Größere Datenmengen laden

Wenn du mit großeren Datenmengen arbeiten möchtest, kann du Batching verwenden:

```python
from database import load_all_data

# Lade in Chunks
chunk_size = 50000
dfs = []

for offset in range(0, 500000, chunk_size):
    df = load_all_data(limit=chunk_size)
    dfs.append(df)

df_all = pd.concat(dfs, ignore_index=True)
```

### Performance-Tipps

1. **Filtere früh**: Verwende Filter in `load_with_filters()` statt später
2. **Nutze Limits**: Beginne mit kleineren Limits zum Testen
3. **Selektiere Spalten**: Wenn möglich nur die benötigten Spalten laden
4. **Cache Ergebnisse**: Speichere größere DataFrames lokal

```python
# Speichern
df.to_parquet('data_cache.parquet')
df.to_csv('data_cache.csv', index=False)

# Laden
df = pd.read_parquet('data_cache.parquet')
df = pd.read_csv('data_cache.csv')
```

## 📝 Fehlerbehandlung

```python
from database import load_with_filters
import logging

logging.basicConfig(level=logging.INFO)

try:
    df = load_with_filters(
        cantons=['ZH'],
        limit=1000
    )
except ValueError as e:
    print(f"Konfigurationsfehler: {e}")
except Exception as e:
    print(f"Fehler beim Laden: {e}")
```

## 🧪 Beispiele ausführen

```bash
# Alle Beispiele anschauen
python database/example_load.py
```

Dies zeigt alle verfügbaren Funktionen mit praktischen Beispielen.

## 📚 Weitere Ressourcen

- [Supabase Dokumentation](https://supabase.com)
- [Pandas Dokumentation](https://pandas.pydata.org)
- [scikit-learn](https://scikit-learn.org) - Für Machine Learning

## ⚠️ Wichtig

- **Stelle sicher, dass `DATABASE_URL` in deiner `.env` Datei gesetzt ist**
- Große DataFrames können viel Speicher verbrauchen
- Bei Performance-Problemen verwende Limits und Filter
- Verwende `get_statistics()` um die Datenbankgröße zu verstehen

---

**Viel Erfolg mit deinem ML-Projekt! 🚀**
