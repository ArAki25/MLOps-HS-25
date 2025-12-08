# SIMAP Data Pipeline

Automatisierte Pipeline zum Exportieren von Schweizer öffentlichen Ausschreibungsdaten von [SIMAP.ch](https://www.simap.ch) und Import in Supabase.

## Features

- **Stündliche Aktualisierung** via GitHub Actions
- **SIMAP API Client** mit Retry-Logik und Rate-Limiting
- **Supabase Integration** für persistente Datenhaltung
- **Web-UI** zur Anzeige der Ausschreibungen
- **ML-Klassifikator** für Projekttyp-Vorhersagen
- **Flexible Filter** nach Kantonen, Sprachen, Prozesstypen

## Schnellstart

### Installation

```bash
# Repository klonen
git clone <repository-url>
cd MLOps-HS-25

# Dependencies installieren
pip install -r requirements.txt

# .env konfigurieren (optional für DB)
cp .env.example .env
# DATABASE_URL eintragen
```

### Daten exportieren

```bash
# Letzte 2 Tage exportieren und in DB importieren
python scripts/update_db.py --days 2

# Nur CSV exportieren (ohne DB)
python scripts/update_db.py --days 30 --dry-run

# Ab bestimmtem Datum
python scripts/update_db.py --start 2024-01-01
```

### Daten laden

```bash
# Alle Daten aus DB laden
python scripts/load_data.py

# Mit Filtern
python scripts/load_data.py --type filtered --cantons ZH BE --limit 100

# Nur Awards
python scripts/load_data.py --type awards
```

### Web-UI starten

```bash
cd ui
python app.py
# Öffne http://127.0.0.1:5000
# Login: admin@musterfirma.ch / admin123
```

## Projektstruktur

```
MLOps-HS-25/
├── .github/workflows/
│   └── hourly_update.yml    # Stündliche Aktualisierung
├── simap/                   # SIMAP API Client
│   ├── api.py              # HTTP Client mit Retry
│   ├── exporter.py         # CSV Export
│   └── extract.py          # Datenextraktion
├── database/                # Datenbank-Module
│   ├── connection.py       # DB-Verbindung
│   ├── importer.py         # CSV -> DB Import
│   └── loader.py           # DB -> DataFrame
├── ui/                      # Flask Web-UI
│   ├── app.py              # Flask App
│   ├── models.py           # Datenmodelle
│   ├── static/             # CSS
│   └── templates/          # HTML Templates
├── ml/                      # Machine Learning
│   └── classifier.py       # RF Klassifikator
├── scripts/                 # CLI-Scripts
│   ├── update_db.py        # Haupt-Update-Script
│   └── load_data.py        # Daten-Lade-Script
├── docs/                    # Dokumentation
│   └── DATABASE_SETUP.md   # DB Setup Guide
├── sql/
│   └── schema.sql          # DB Schema
├── config.py               # Zentrale Konfiguration
├── requirements.txt
└── README.md
```

## Konfiguration

Alle Einstellungen können in `config.py` oder via Umgebungsvariablen angepasst werden:

```python
# Kantone
DEFAULT_CANTONS = ["ZH", "BE", "LU", ...]

# Sprachen
DEFAULT_LANGUAGES = ["de", "en"]

# Prozesstypen
DEFAULT_PROCESS_TYPES = ["open", "selective"]

# Zeitraum
DEFAULT_DAYS_BACK = 30
```

## GitHub Actions

Der Workflow `.github/workflows/hourly_update.yml` führt stündlich Updates durch:

- **Schedule**: Jede Stunde zur 15. Minute
- **Manueller Trigger**: Mit konfigurierbarem `days_back` Parameter
- **Error Handling**: Erstellt GitHub Issue bei Fehlern
- **Caching**: pip Dependencies werden gecached

### Setup

1. GitHub Secret `DATABASE_URL` setzen:
   - Repository → Settings → Secrets → New repository secret
   - Name: `DATABASE_URL`
   - Value: Supabase Connection String

## API Nutzung

### SIMAP Client

```python
from simap import SimapClient, export_to_csv

# Client direkt nutzen
client = SimapClient()
for project in client.get_projects({"newestPublicationFrom": "2024-01-01"}):
    print(project['title'])

# CSV exportieren
export_to_csv(
    output_file="data/projects.csv",
    days_back=7,
    cantons=["ZH", "BE"],
    languages=["de"]
)
```

### Database Loader

```python
from database import load_all_data, load_with_filters

# Alle Daten laden
df = load_all_data(limit=1000)

# Mit Filtern
df = load_with_filters(
    cantons=['ZH', 'BE'],
    publication_types=['tender'],
    min_amount=100000
)
```

## Datenbank-Schema

Die Tabelle `simap_projects` enthält 40+ Felder:

| Kategorie | Felder |
|-----------|--------|
| IDs | `project_id`, `publication_id`, `project_number` |
| Basis | `title`, `description`, `publication_date`, `publication_type` |
| Ort | `canton`, `city`, `postal_code`, `country` |
| Preise | `estimated_amount`, `award_amount` |
| Award | `winner_name`, `award_decision_date`, `number_of_submissions` |
| Klassifizierung | `cpv_code`, `bkp_codes`, `order_type` |

Siehe [sql/schema.sql](sql/schema.sql) für das vollständige Schema.

## ML-Klassifikator

```python
from ml.classifier import predict_project_info

# Klassifikator trainieren
python ml/classifier.py

# Vorhersagen
result = predict_project_info(df_new_projects)
print(result[['order_type_pred', 'size_bucket_pred']])
```

## Troubleshooting

### DATABASE_URL nicht gefunden
```bash
# .env Datei erstellen
echo 'DATABASE_URL="..."' > .env
```

### psycopg2 nicht installiert
```bash
pip install psycopg2-binary
```

### Rate Limiting
Der API Client hat eingebaute Retry-Logik. Bei häufigen 429-Fehlern `API_DELAY` erhöhen:
```python
# In config.py
API_DELAY = 0.5  # Sekunden zwischen Requests
```

## Lizenz

Dieses Projekt ist für Bildungszwecke (FHNW MLOps HS25) erstellt.
