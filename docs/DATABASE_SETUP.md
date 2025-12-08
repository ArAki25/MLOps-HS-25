# Supabase Datenbank Setup für SIMAP-Daten

Diese Anleitung zeigt, wie du die SIMAP-Daten in Supabase importierst und automatisierte tägliche Updates einrichtest.

> **Hinweis für Teams**: Diese Integration ist **optional**. Das Tool funktioniert ohne Supabase und exportiert standardmäßig nur CSV-Dateien. Nur wer tägliche Updates oder eine ML-Pipeline mit Datenbank braucht, muss dies einrichten.

## Schnellstart

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
python scripts/update_db.py
```

Das Script wird:
1. SIMAP-Daten von der API holen
2. CSV exportieren nach `data/simap_projects.csv`
3. Automatisch die Tabelle in Supabase erstellen
4. Die Daten importieren

## Konfiguration

In [config.py](../config.py) oder direkt im Script kannst du folgende Parameter anpassen:

```python
# Basis-Parameter
OUTPUT_FILE = "data/simap_projects.csv"
DAYS_BACK = 30              # Wie viele Tage zurück
MAX_PAGES = None            # Maximale Anzahl API-Seiten

# Filter
PUBLICATION_TYPES = None    # z.B. ["tender", "award"]
CANTONS = None              # z.B. ["ZH", "BE", "GE"]
LANGUAGES = "de"            # z.B. ["de", "fr"]
PROCESS_TYPES = "open"      # z.B. ["open", "selective"]
```

## Datenbank-Schema

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

## Automatisierte Updates

### GitHub Actions (empfohlen)

Der Workflow in `.github/workflows/hourly_update.yml` führt stündlich Updates durch:

```yaml
on:
  schedule:
    - cron: '15 * * * *'  # Stündlich zur 15. Minute
  workflow_dispatch:       # Manueller Trigger
```

Füge `DATABASE_URL` als Secret in GitHub hinzu:
- Settings → Secrets and variables → Actions → New repository secret

### Manueller Import

```bash
# Letzte 2 Tage
python scripts/update_db.py --days 2

# Ab bestimmtem Datum
python scripts/update_db.py --start 2024-01-01

# Nur Export (kein DB-Import)
python scripts/update_db.py --dry-run
```

## Daten laden

```bash
# Alle Daten
python scripts/load_data.py

# Gefiltert
python scripts/load_data.py --type filtered --cantons ZH BE --limit 100

# Nur Awards
python scripts/load_data.py --type awards --limit 500
```

## Nützliche SQL-Queries

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

### Volltext-Suche

```sql
SELECT project_id, title, description
FROM simap_projects
WHERE to_tsvector('german', COALESCE(title, '') || ' ' || COALESCE(description, ''))
      @@ to_tsquery('german', 'Software | IT | Digitalisierung');
```

## Troubleshooting

### Fehler: "DATABASE_URL nicht gefunden"
Prüfe dass die `.env` Datei existiert und `DATABASE_URL` gesetzt ist.

### Fehler: "psycopg2 not found"
```bash
pip install psycopg2-binary
```

### Fehler: "connection refused"
Prüfe die Supabase Connection Details:
- Verwende "Connection Pooling" (Port 6543) statt "Direct Connection" (Port 5432)

## Security Best Practices

1. **Niemals** `.env` oder Credentials in Git committen
2. Prüfe dass `.env` in `.gitignore` steht
3. Für Production: Verwende Environment Variables statt `.env`
4. Row Level Security (RLS) in Supabase aktivieren für Multi-User Setup

