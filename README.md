# SIMAP CSV Exporter

**Einfaches Tool zum Exportieren von Schweizer öffentlichen Ausschreibungsdaten als CSV.**

Holt Daten von der [SIMAP-API](https://www.simap.ch) (Swiss Internet Market Place) und exportiert sie in eine übersichtliche CSV-Datei für Analysen.

## 🎯 Was macht dieses Tool?

- **Holt** öffentliche Ausschreibungen und Zuschläge von SIMAP
- **Extrahiert** umfangreiche Informationen:
  - Basis-Daten (Titel, Beschreibung, Auftraggeber, Ort)
  - Fristen und geschätzte Preise
  - **Award-Informationen**: Gewinner, Zuschlagspreise, Anzahl Eingaben
  - **Projektdetails**: Projektnummern, Bautypen, Kategorien
  - **Klassifizierungen**: CPV, BKP, NPK Codes
- **Filtert** nach Ihren Bedürfnissen (Kantone, Sprachen, Publikationstypen)
- **Exportiert** alles in eine CSV-Datei
- **Zeigt automatisch Statistiken** nach dem Export

## 🚀 Schnellstart

### Installation

```bash
# Repository klonen
git clone <repository-url>
cd MLOps-HS-25

# Dependencies installieren
pip install -r requirements.txt
```

### Verwendung

```bash
# Einfach ausführen
python main.py
```

Das erstellt eine Datei `data/simap_projects.csv` mit allen Projekten der letzten 30 Tage und zeigt automatisch Statistiken an.

## 🎛️ Filter konfigurieren

Öffnen Sie [main.py](main.py) und passen Sie die Filter an:

```python
# Basis-Parameter
DAYS_BACK = 30              # Wie viele Tage zurück
MAX_PAGES = 10              # Maximale Anzahl API-Seiten
MAX_PROJECTS = None         # Maximale Anzahl Projekte (None = alle)

# Filter (Optional)
PUBLICATION_TYPES = ["tender"]      # Nur Ausschreibungen
CANTONS = ["ZH", "BE"]              # Nur Zürich und Bern
LANGUAGES = ["de"]                  # Nur deutschsprachig
PROCESS_TYPES = ["open"]            # Nur offene Verfahren
```

### Filter-Optionen

| Filter | Optionen | Beispiel |
|--------|----------|----------|
| **Publikationstypen** | `tender` (Ausschreibungen)<br>`award` (Zuschläge)<br>`cancellation` (Stornierungen) | `["tender", "award"]` |
| **Kantone** | `ZH`, `BE`, `LU`, `GE`, `VD`, `AG`, `SG`, etc. | `["ZH", "BE", "GE"]` |
| **Sprachen** | `de`, `fr`, `it`, `en` | `["de"]` |
| **Prozesstypen** | `open`, `selective`, `invitation` | `["open"]` |

## 📊 CSV-Ausgabe

Die CSV-Datei enthält **39 Spalten** mit detaillierten Informationen:

### Basis-Informationen
- `project_id`, `publication_id`, `publication_date`
- `title`, `description`, `contracting_authority`
- `canton`, `city`, `postal_code`, `country`

### Projektdetails
- `project_number`, `publication_number`
- `project_type`, `project_subtype`, `publication_type`
- `order_type`, `construction_type`, `construction_category`
- `lots_type`, `creation_language`

### Fristen & Preise
- `submission_deadline`
- `estimated_amount`, `estimated_currency`
- `process_type`

### Award-Informationen (bei Zuschlägen)
- `award_decision_date`, `number_of_submissions`
- `winner_name`, `winner_city`, `winner_canton`, `winner_postal_code`
- `award_amount`, `award_currency`, `award_vat_type`

### Klassifizierungen
- `cpv_code`, `additional_cpv_codes`
- `bkp_codes`, `ebkph_codes`, `ebkpt_codes`, `npk_codes`

## 📈 Automatische Statistiken

Nach jedem Export sehen Sie automatisch:

```
============================================================
EXPORT-STATISTIKEN
============================================================
Total Projekte: 200

Publikationstypen:
  Ausschreibungen     :  120 ( 60.0%)
  Zuschläge           :   75 ( 37.5%)
  Stornierungen       :    5 (  2.5%)

Sprachen:
  Deutsch        :  120 ( 60.0%)
  Französisch    :   60 ( 30.0%)
  Italienisch    :   20 ( 10.0%)

Top 5 Kantone:
  ZH   :   50 ( 25.0%)
  BE   :   40 ( 20.0%)
  GE   :   30 ( 15.0%)
  VD   :   25 ( 12.5%)
  AG   :   20 ( 10.0%)

Basis-Felder:
  Titel vorhanden:        194 ( 97.0%)
  Kanton vorhanden:       133 ( 66.5%)
  Stadt vorhanden:        130 ( 65.0%)
  PLZ vorhanden:          134 ( 67.0%)

Award-Informationen (Zuschläge):
  Zuschlagspreis:          75 ( 37.5%)
  Gewinner-Name:           83 ( 41.5%)
  Anzahl Eingaben:         73 ( 36.5%)
============================================================
```

## 📁 Projektstruktur

```
MLOps-HS-25/
├── Simap/
│   ├── api.py         # API-Client mit Retry-Logik
│   ├── extract.py     # Datenextraktion (39 Felder!)
│   └── exporter.py    # CSV-Export mit Filtern & Statistiken
├── data/              # Exportierte CSV-Dateien
├── main.py            # Hauptprogramm mit Filter-Konfiguration
└── requirements.txt   # Dependencies
```

## 🛠️ Erweiterte Nutzung

### Als Python-Modul verwenden

```python
from Simap.exporter import export_to_csv

# Nur deutschsprachige Ausschreibungen aus Zürich
export_to_csv(
    output_file="data/zh_tenders.csv",
    days_back=7,
    publication_types=["tender"],
    cantons=["ZH"],
    languages=["de"]
)
```

### Nur API-Client nutzen

```python
from Simap.api import SimapClient

client = SimapClient()

# Projekte abrufen
params = {"newestPublicationFrom": "2024-01-01"}
for project in client.get_projects(params, max_pages=1):
    print(project["title"])

    # Details holen
    details = client.get_project_details(
        project["id"],
        project["publicationId"]
    )
```

## 💡 Anwendungsfälle

### 1. Marktanalyse
Filtern Sie nach Zuschlägen, um zu sehen:
- Welche Firmen gewinnen Aufträge?
- Zu welchen Preisen?
- Wie viele Firmen bewerben sich durchschnittlich?

```python
PUBLICATION_TYPES = ["award"]
CANTONS = ["ZH", "BE"]
```

### 2. Geschäftsmöglichkeiten finden
Nur offene Ausschreibungen in Ihrer Region:

```python
PUBLICATION_TYPES = ["tender"]
CANTONS = ["ZH"]
LANGUAGES = ["de"]
PROCESS_TYPES = ["open"]
```

### 3. Wettbewerbsanalyse
Alle Projekte eines Kantons:

```python
CANTONS = ["GE"]
DAYS_BACK = 90
```

## ⚠️ Hinweise

- **Rate Limiting**: Das Tool respektiert automatisch Rate Limits der API
- **Pausen**: Zwischen Requests gibt es automatische Pausen (0.25s)
- **Fehlerbehandlung**: Fehlerhafte Projekte werden übersprungen und geloggt
- **DSGVO**: Keine persönlichen Kontaktdaten werden gespeichert

## 📝 Lizenz

Dieses Projekt ist für Bildungszwecke erstellt.

## 🤝 Contributing

Pull Requests sind willkommen! Für größere Änderungen bitte zuerst ein Issue öffnen.
