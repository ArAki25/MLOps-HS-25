# SIMAP CSV-Export – Einfache Anleitung für Einsteiger

## Was ist SIMAP?

SIMAP ist eine Plattform, auf der öffentliche Aufträge in der Schweiz veröffentlicht werden. Mit diesem kleinen Programm kannst du Aufträge aus SIMAP suchen und als Tabelle (CSV-Datei) speichern. So kannst du die Daten einfach anschauen oder weiterverarbeiten.

## Was macht dieses Tool?

Das Tool holt für dich die Aufträge von SIMAP und speichert sie in einer Datei. Du kannst einen Zeitraum und Auftragsarten einstellen und bekommst dann eine Tabelle mit den passenden Aufträgen.

---

## Schritt 1: Python installieren

Python ist eine Programmiersprache. Das Programm läuft damit.

- Gehe auf https://www.python.org/downloads/
- Lade die neueste Version herunter (am besten 3.10 oder neuer)
- Folge den Installationsanweisungen auf der Webseite

---

## Schritt 2: Das Programm vorbereiten

1. Öffne die Kommandozeile (Terminal oder Eingabeaufforderung).
2. Wechsle in den Ordner, in dem das Programm liegt.
3. Installiere die benötigten Zusatzprogramme (Pakete) mit diesem Befehl:

```
pip install -r requirements.txt  # Installiert alle nötigen Pakete
```

---

## Schritt 3: Das Programm starten

Du kannst jetzt das Programm starten, um Aufträge herunterzuladen.

- Beispiel: Alle Aufträge vom 1. Januar bis 30. Juni 2024

Vorher kannst du noch einstellen, welche Aufträge du willst. Das machst du mit Umgebungsvariablen. So geht das:

```
# Zeitraum einstellen
set SIMAP_START=2024-01-01
set SIMAP_END=2024-06-30

# Auftragstypen einstellen (Beispiel: alle Typen)
set SIMAP_TYPES=OB00,OB01,OB02,OB03,OB04,OB05,OB06,OB07,OB08,OB09
```

(Diese Befehle sind für Windows. Auf Mac oder Linux benutzt du `export` statt `set`.)

Dann startest du das Programm so:

```
python -m source_code.export_csv  # Startet den Export
```

---

## Schritt 4: Ergebnis anschauen

Das Programm speichert die Daten als CSV-Datei im Ordner `data/raw/`.

Beispiel-Datei:

```
data/raw/auftraege_2024-01-01_2024-06-30_all.csv
```

Du kannst diese Datei mit Excel oder einem anderen Tabellenprogramm öffnen.

---

## Zusammenfassung

1. Python installieren
2. Pakete installieren mit `pip install -r requirements.txt`
3. Zeitraum und Typen einstellen (optional)
4. Programm starten mit `python -m source_code.export_csv`
5. Ergebnis-Datei in `data/raw/` öffnen

Viel Erfolg beim Arbeiten mit SIMAP-Daten!

---

## Schnellstart mit main.py

- Abhängigkeiten installieren: `pip install -r requirements.txt`
- CSV exportieren, z. B. die letzten 10 Tage und max. 3 Seiten:
  - `python main.py --days-back 10 --max-pages 3 --output simap_projects.csv`
- Weitere Optionen:
  - `--detail-delay`, `--page-delay`, `--max-projects`, `--log-level`

Beispiel:

```
python main.py --days-back 30 --max-pages 5 --output data/raw/simap_last30d.csv
```
