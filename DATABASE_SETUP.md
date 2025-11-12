# Supabase Datenbank Setup für SIMAP-Daten

Diese Anleitung zeigt, wie du die SIMAP-Daten in Supabase importierst und automatisierte tägliche Updates einrichtest.

> **💡 Hinweis für Teams**: Diese Integration ist **optional**. Das Tool funktioniert ohne Supabase und exportiert standardmäßig nur CSV-Dateien. Nur wer tägliche Updates oder eine ML-Pipeline mit Datenbank braucht, muss dies einrichten.

## 🚀 Schnellstart

### 1. Dependencies installieren

```bash
pip install -r requirements.txt
```

### 2. .env Datei konfigurieren

Erstelle eine `.env` Datei (diese ist in `.gitignore` und wird **nicht** ins Repository committed):

```bash
# Kopiere das Template
cp .env.example .env

# Bearbeite .env und trage deine Supabase Credentials ein
```

Deine `.env` Datei sollte so aussehen:

```env
DATABASE_URL="user=postgres.xxx password='xxx' host=aws-1-eu-north-1.pooler.supabase.com port=6543 dbname=postgres sslmode=require"
```

**Wo finde ich die DATABASE_URL?**
- Supabase Dashboard → Settings → Database → Connection String
- Verwende "Connection Pooling" (Port 6543), nicht "Direct Connection"

### 3. Ersten Import durchführen

```bash
python main.py
```

Das Script wird:
1. SIMAP-Daten von der API holen
2. CSV exportieren nach `data/simap_projects.csv`
3. Automatisch die Tabelle in Supabase erstellen
4. Die Daten importieren

## 📋 Konfiguration

In [main.py](main.py) kannst du folgende Parameter anpassen:

```python
# Basis-Parameter
OUTPUT_FILE = "data/simap_projects.csv"
DAYS_BACK = 30              # Wie viele Tage zurück
MAX_PAGES = None            # Maximale Anzahl API-Seiten
MAX_PROJECTS = 100          # Maximale Anzahl Projekte

# Datenbank-Konfiguration
EXPORT_TO_CSV = True        # CSV-Export aktivieren
IMPORT_TO_DB = True         # Direkter Import in Supabase
USE_DIRECT_IMPORT = False   # True = API -> DB, False = CSV -> DB

# Filter
PUBLICATION_TYPES = None    # z.B. ["tender", "award"]
CANTONS = None              # z.B. ["ZH", "BE", "GE"]
LANGUAGES = "de"            # z.B. ["de", "fr"]
PROCESS_TYPES = "open"      # z.B. ["open", "selective"]
```

## 🗄️ Datenbank-Schema

Die Tabelle `simap_projects` wird automatisch erstellt mit allen relevanten Feldern:

- **IDs**: `project_id`, `publication_id`
- **Basis-Info**: `title`, `description`, `publication_date`, `publication_type`
- **Ort**: `canton`, `city`, `postal_code`
- **Preise**: `estimated_amount`, `award_amount`
- **Klassifizierung**: `cpv_code`, `bkp_codes`, etc.
- **Metadaten**: `created_at`, `updated_at`

**Primary Key**: `(project_id, publication_id)` - ermöglicht Upserts ohne Duplikate.

### Manuelles Schema-Setup (optional)

Falls du das Schema manuell im Supabase SQL Editor ausführen möchtest:

```bash
# Öffne sql/schema.sql im Supabase Dashboard
# und führe es im SQL Editor aus
```

## 🔄 Automatisierte tägliche Updates

### Option 1: Cron Job (Linux/Mac)

```bash
crontab -e
```

Füge hinzu (täglich um 6:00 Uhr):

```cron
0 6 * * * cd /pfad/zu/projekt && /pfad/zu/python main.py >> logs/import.log 2>&1
```

### Option 2: Windows Task Scheduler

1. Öffne "Task Scheduler"
2. Erstelle neue Aufgabe
3. Trigger: Täglich um 6:00 Uhr
4. Aktion: Programm starten
   - Programm: `C:\pfad\zu\python.exe`
   - Argumente: `main.py`
   - Arbeitsverzeichnis: `C:\Users\Salio\Documents\FH\Github\Projekte\MLOps-HS-25`

### Option 3: GitHub Actions (Cloud)

Erstelle `.github/workflows/daily-import.yml`:

```yaml
name: Daily SIMAP Import

on:
  schedule:
    - cron: '0 6 * * *'  # Täglich um 6:00 UTC
  workflow_dispatch:      # Manueller Trigger

jobs:
  import:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run import
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
        run: python main.py
```

Füge `DATABASE_URL` als Secret in GitHub hinzu:
- Settings → Secrets and variables → Actions → New repository secret

## 🎯 Nur für ML relevante Daten filtern

In [main.py](main.py) kannst du Filter setzen:

```python
# Nur deutschsprachige offene Ausschreibungen
PUBLICATION_TYPES = ["tender"]
LANGUAGES = ["de"]
PROCESS_TYPES = ["open"]

# Nur bestimmte Kantone
CANTONS = ["ZH", "BE", "LU"]

# Nur letzte 7 Tage
DAYS_BACK = 7
```

## 📊 Nützliche SQL-Queries für ML

### Neue Daten der letzten 24h

```sql
SELECT * FROM simap_projects
WHERE publication_date >= NOW() - INTERVAL '24 hours'
ORDER BY publication_date DESC;
```

### Offene Ausschreibungen mit Deadline

```sql
SELECT project_id, title, canton, submission_deadline, estimated_amount
FROM simap_projects
WHERE publication_type = 'tender'
AND submission_deadline > NOW()
ORDER BY submission_deadline;
```

### Volltext-Suche für Keywords

```sql
SELECT project_id, title, description
FROM simap_projects
WHERE to_tsvector('german', COALESCE(title, '') || ' ' || COALESCE(description, ''))
      @@ to_tsquery('german', 'Software | IT | Digitalisierung');
```

### Views für ML-Training

Das Schema erstellt automatisch Views:

- `simap_tenders` - Nur Ausschreibungen
- `simap_awards` - Nur Zuschläge
- `simap_tender_award_pairs` - Matching von Ausschreibungen und Zuschlägen

```sql
-- Verwende die Views
SELECT * FROM simap_tenders LIMIT 10;
SELECT * FROM simap_awards WHERE award_amount > 100000;
```

## 🔧 Erweiterte Nutzung

### Nur DB-Import ohne CSV

```python
EXPORT_TO_CSV = False
IMPORT_TO_DB = True
```

### Nur CSV ohne DB

```python
EXPORT_TO_CSV = True
IMPORT_TO_DB = False
```

### CSV nachträglich importieren

```python
from Simap.db_importer import import_csv_to_db

stats = import_csv_to_db("data/simap_projects.csv")
print(f"Importiert: {stats['inserted']}")
```

## ⚡ Performance-Tipps

1. **Batch Size**: Standard ist 100 Records pro Batch. Bei langsamer Verbindung reduzieren:
   ```python
   import_csv_to_db("data/simap_projects.csv", batch_size=50)
   ```

2. **Indizes**: Die wichtigsten Indizes werden automatisch erstellt. Siehe [sql/schema.sql](sql/schema.sql)

3. **Connection Pooling**: Für High-Frequency Updates Supabase Pooler verwenden (port=6543)

## 🐛 Troubleshooting

### Fehler: "DATABASE_URL nicht gefunden"

Prüfe dass die `.env` Datei existiert und `DATABASE_URL` gesetzt ist.

### Fehler: "psycopg2 not found"

```bash
pip install psycopg2-binary
```

### Fehler: "connection refused"

Prüfe die Supabase Connection Details:
- Supabase Dashboard → Settings → Database → Connection String
- Verwende "Connection Pooling" (Port 6543) statt "Direct Connection" (Port 5432)

### Duplikate vermeiden

Das Script verwendet automatisch `ON CONFLICT UPDATE` basierend auf `(project_id, publication_id)`.
Beim erneuten Import werden existierende Einträge aktualisiert statt neu eingefügt.

## 📈 Monitoring

Aktiviere Logging für Details:

```python
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/import.log'),
        logging.StreamHandler()
    ]
)
```

## 🔐 Security Best Practices

1. **Niemals** `.env` oder Credentials in Git committen
2. Prüfe dass `.env` in [.gitignore](.gitignore) steht
3. Für Production: Verwende Environment Variables statt `.env`
4. Row Level Security (RLS) in Supabase aktivieren für Multi-User Setup

## 🚀 Next Steps für ML-Pipeline

1. **Feature Engineering**: Views in [sql/schema.sql](sql/schema.sql) anpassen
2. **Training Data**: Query mit relevanten Features erstellen
3. **Prediction Pipeline**: Neue Ausschreibungen täglich analysieren
4. **Feedback Loop**: Predictions zurück in DB schreiben für Monitoring

Beispiel für ML-Features:

```sql
SELECT
    project_id,
    title,
    description,
    canton,
    estimated_amount,
    cpv_code,
    LENGTH(description) as description_length,
    EXTRACT(DOW FROM publication_date) as day_of_week,
    -- Deine eigenen Features...
FROM simap_tenders
WHERE publication_date >= '2024-01-01';
```
