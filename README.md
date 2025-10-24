# SIMAP CSV-Export – Kurzanleitung

Dieses Repo enthält einen kleinen Python‑Client, um aus der SIMAP‑Archiv‑API (https://archiv.simap.ch/api) Aufträge zu suchen und als CSV zu exportieren. Optional kannst du die CSV auch in Excel konvertieren und formatieren.

## Voraussetzungen
- Python 3.10+ und ein virtuelles Environment (`.venv`) empfohlen
- Installiere Abhängigkeiten: `pip install -r requirements.txt` 

## Schnellstart: CSV für ein Datumsspektrum erzeugen
1) Basis‑URL prüfen/setzen (Standard ist bereits korrekt):
   - `SIMAP_BASE_URL` default: `https://archiv.simap.ch/api`
2) Zeitraum und Typen einstellen (ENV‑Variablen, optional):
   - `SIMAP_START` z. B. `2024-01-01`
   - `SIMAP_END` z. B. `2024-06-30`
   - `SIMAP_TYPES` z. B. `OB00,OB01,OB02,OB03,OB04,OB05,OB06,OB07,OB08,OB09` (alle Typen)
3) Export starten:
   - `python -m source_code.export_csv`
4) Ergebnis:
   - CSV liegt in `data/raw/`, z. B. `auftraege_2024-01-01_2024-06-30_all.csv`

## Relevante Dateien
- `source_code/api_client.py` – HTTP‑Client, Suche, CSV‑Export und Filter‑Helper
- `source_code/export_csv.py` – einfaches Skript, das Filter setzt und exportiert

## Filter bequem setzen (Helper)
Zum Setzen der Filter gibt es `build_search_filters(...)` in `source_code/api_client.py`. Damit kannst du gängige Felder komfortabel übergeben:

Beispiel (Python):
```
from source_code.api_client import SimapAPIClient, build_search_filters

filters = build_search_filters(
    start_date="2024-01-01",
    end_date="2024-06-30",
    types=["OB00","OB01","OB02","OB03","OB04","OB05","OB06","OB07","OB08","OB09"],
    contract_types=["WORKS","SERVICES"],
    procedures=["OPEN","RESTRICTED"],
    cpv=["45000000"],
    bkp=["40","211"],
    keywords="*Brücke*",
    canton_codes=["ZH","BE"],
)

client = SimapAPIClient()
pubs = client.iterate_publications(filters, records_per_page=1000)
client.export_publications_csv(pubs, filename="auftraege_custom.csv")
```

Oder per ENV‑Variablen mit `source_code/export_csv.py`:
- `SIMAP_START` / `SIMAP_END`
- `SIMAP_TYPES` (kommagetrennt, z. B. `OB00,OB01,...`)
- `SIMAP_CONTRACT_TYPES` (z. B. `WORKS,SERVICES,SUPPLIES,CONTEST`)
- `SIMAP_PROCEDURES` (z. B. `OPEN,RESTRICTED,OTHER`)
- `SIMAP_CPV` / `SIMAP_BKP` (kommagetrennt)
- `SIMAP_KEYWORDS` (z. B. `*Tunnel*`)
- `SIMAP_CSV_NAME` (Dateiname der Ausgabe)

Beispiel (PowerShell):
```
$env:SIMAP_START = "2024-01-01"
$env:SIMAP_END = "2024-06-30"
$env:SIMAP_TYPES = "OB00,OB01,OB02,OB03,OB04,OB05,OB06,OB07,OB08,OB09"
$env:SIMAP_KEYWORDS = "*Brücke*"
python -m source_code.export_csv
```

## Optional: Excel‑Konvertierung und Formatierung
Wenn Excel installiert ist, kannst du die CSV per PowerShell/COM in `.xlsx` umwandeln und formatieren (Autofilter, Kopfzeile fixieren, Datumsspalten etc.). Beispiel‑Skripte sind nicht im Repo enthalten, aber wir haben die Abläufe bereits getestet.

Alternativ lässt sich eine reine Python‑Variante (z. B. `openpyxl`) ergänzen – melde dich, wenn wir das hinzufügen sollen.
