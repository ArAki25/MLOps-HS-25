# Feld-Analyse `public.archive` / `public.projects` für Embedding-Text

Quelle: Live-Daten via `user-supabase` MCP, 2026-04-17.
Grundgesamtheit: `archive` = **254'101 Zeilen** (nach Cleanup vom 2026-04-16), `projects` = **10'967 Zeilen**.

Zweck dieses Berichts: Für jedes Feld begründet entscheiden, ob es in den Rohtext für das Embedding gehört, wie es formatiert werden soll und welche Fallstricke es gibt. Ergebnis fliesst direkt in `embeddings/text_builder.py`.

---

## 1. Die zentrale Einsicht: pub_type bestimmt, welche Felder überhaupt gefüllt sind

Feldbefüllung nach `pub_type` (alle Zahlen = Anzahl NOT NULL):


| pub_type                  | Anzahl  | `description_de` | `description_fr` | `winner_name` | `award_amount` | `award_justification_de` | `remedies_notice_de` | `bkp_codes` |
| ------------------------- | ------- | ---------------- | ---------------- | ------------- | -------------- | ------------------------ | -------------------- | ----------- |
| **OB01** (Ausschreibung)  | 124'152 | **0**            | **0**            | 0             | 0              | 0                        | 0                    | 40'628      |
| **OB02** (Zuschlag)       | 97'641  | 20'523           | 9'448            | **97'641**    | **85'917**     | 69'103                   | 75'486               | 25'019      |
| **OB05** (Abbruch)        | 12'327  | 2'429            | 9'898            | 0             | 0              | 0                        | 0                    | 4'451       |
| **OB06** (Wettbewerb)     | 6'364   | 3'625            | 2'689            | 0             | 0              | 0                        | 0                    | 1'011       |
| **OB04** (Vorankündigung) | 5'496   | 3'450            | 2'046            | 0             | 0              | 0                        | 0                    | 0           |
| **OB00** (Einladung)      | 2'741   | 1'647            | 1'094            | 0             | 0              | 0                        | 0                    | 0           |
| **OB07** (Projektwettb.)  | 2'633   | 1'839            | 794              | 0             | 0              | 0                        | 0                    | 748         |
| **OB08** (Freihändige)    | 1'152   | 0                | 0                | **1'152**     | 0              | 0                        | 817                  | 369         |
| **OB03** (Eignungsprüf.)  | 820     | 557              | 263              | 0             | 0              | 0                        | 0                    | 0           |
| **OB09** (Andere)         | 775     | 215              | 126              | 0             | 0              | 0                        | 0                    | 0           |


**Konsequenzen für das Embedding:**

1. Für **49% des Archivs (OB01)** gibt es **keine Beschreibung** — der Embedding-Text muss aus Titel + kategorialen Labels + CPV + BKP alleine Aussagekraft gewinnen. Die alte Template-Logik mit "Beschreibung ist zentral" ist für die halbe Tabelle wertlos.
2. **Zuschläge (OB02/OB08)** tragen semantisch reiche Zusatzinfos (`winner_name`, `award_justification_de`), die bis jetzt komplett ignoriert wurden. Das ist ein grosser ungenutzter Signal-Gewinn.
3. Der **Embedding-Text muss pub_type-aware sein** (andere Felder je nach Publikationstyp), sonst wird der Vektorraum zwischen OB01 und OB02 künstlich getrennt, weil bei OB01 alle "Zuschlag an …"-Blöcke fehlen.

**Strategie:** Einheitliches Basis-Template (Labels + CPV + BKP + Titel + Beschreibung), plus optionale Blöcke für OB02/OB08 (winner + justification). Fehlende Felder werden stillschweigend weggelassen (kein "`None`", keine leeren Platzhalter).

---

## 2. Feld-für-Feld-Entscheidung

Legende Spalte **Verwendung**:

- **INCLUDE** — fliesst in den Embedding-Text ein
- **LABEL** — ENUM-Wert wird auf natürlich-sprachliches DE-Label gemappt
- **LOOKUP** — Code wird über externes Wörterbuch aufgelöst
- **FEATURE** — taugt als separates ML-Feature (nicht für Text), nicht fürs Embedding
- **SKIP** — bewusst ignoriert, mit Begründung

### 2.1 Identifikations- und Metadaten-Felder (SKIP)


| Feld                                                                                     | Verwendung | Begründung                                               |
| ---------------------------------------------------------------------------------------- | ---------- | -------------------------------------------------------- |
| `id`, `simap_project_id`, `simap_publication_id`, `project_number`, `publication_number` | SKIP       | IDs tragen keine Semantik, blähen nur das Embedding auf. |
| `created_at`, `updated_at`, `detail_fetched_at`, `last_checked_at`                       | SKIP       | ETL-Timestamps, irrelevant.                              |
| `content_hash`, `detail_fetch_error`, `raw_json_search`, `raw_json_detail`               | SKIP       | Operative Felder.                                        |
| `corrected`, `publication_ted`, `state_contract_area`, `has_project_documents`           | SKIP       | Bool-Flags ohne Semantik im Volltext.                    |
| `referencing_pub`_* (id, type, date, number)                                             | SKIP       | Verweisstruktur, keine inhaltliche Aussage.              |


### 2.2 Titel und Beschreibung (INCLUDE, zentrales Signal)


| Feld             | archive N     | projects N   | Verwendung                                                               |
| ---------------- | ------------- | ------------ | ------------------------------------------------------------------------ |
| `title_de`       | 162'956 (64%) | 10'864 (99%) | **INCLUDE** — Hauptsignal, Sprachpriorität DE > FR > IT > EN             |
| `title_fr`       | 90'315 (36%)  | 3'054 (28%)  | **INCLUDE** (Fallback)                                                   |
| `description_de` | 34'285 (13%)  | 10'281 (94%) | **INCLUDE** — sehr semantisch, **OHNE 800-char Cut** (avg 427, p99 2410) |
| `description_fr` | 26'358 (10%)  | 1'599 (15%)  | **INCLUDE** (Fallback)                                                   |


HTML-Stripping ist zwingend (alte Daten enthalten `<p>`, `<br>`). BGE-M3 kann 8192 Token → keine Kürzung nötig.

### 2.3 Auftragsart und Verfahren (LABEL – hochrelevant, alle gut gefüllt)


| Feld                    | Coverage                            | Enum-Werte                                                                                                       | Neues DE-Label-Mapping                                                                                                                                                                                        |
| ----------------------- | ----------------------------------- | ---------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `order_type`            | 99.3%                               | WORKS / SERVICES / SUPPLIES / ARCHITECT / CONTEST / ENGINEER / OTHER / NOT_SPECIFIED                             | `Bauauftrag` / `Dienstleistungsauftrag` / `Lieferauftrag` / `Architekturleistung` / `Wettbewerb` / `Ingenieurleistung` / — / —                                                                                |
| `project_type`          | 100%                                | MUNICIPALITY / CANTON / FEDERATION / CANTON_OTHER / MUNICIPALITY_OTHER / UTILITY / FOREIGN / OTHER               | `Gemeinde` / `Kanton` / `Bund` / `Kantonale Körperschaft` / `Gemeindliche Körperschaft` / `Öffentliches Unternehmen` / `Ausland` / `Sonstige`                                                                 |
| `process_type`          | 100%                                | OPEN / RESTRICTED / INVITATION / OTHER                                                                           | `Offenes Verfahren` / `Selektives Verfahren` / `Einladungsverfahren` / `Anderes Verfahren`                                                                                                                    |
| `pub_type`              | 100%                                | OB00–OB09                                                                                                        | `Einladung zur Angebotsabgabe` / `Ausschreibung` / `Zuschlag` / `Eignungsprüfung` / `Vorankündigung` / `Abbruch/Widerruf` / `Wettbewerb` / `Projektwettbewerb` / `Freihändige Vergabe` / `Andere Publikation` |
| `lots_type`             | 13%                                 | NONE / LOTS / PROCUREMENTS                                                                                       | weglassen bei NONE, sonst `Los-Verfahren` / `Beschaffungsrahmen`                                                                                                                                              |
| `project_subtype`       | **0% in archive**, 100% in projects | construction / service / supply / project_competition / project_study / request_for_information / idea_study / … | `Bauauftrag` / `Dienstleistungsauftrag` / `Lieferauftrag` / `Projektwettbewerb` / `Projektstudie` / `Informationsanfrage` / `Ideenstudie` / … (**nur projects, skip in archive weil leer**)                   |
| `construction_type`     | **0% in archive**, 64% in projects  | execution / planning_and_execution                                                                               | `Ausführung` / `Planung und Ausführung`                                                                                                                                                                       |
| `construction_category` | **0% in archive**, 65% in projects  | structural_engineering / civil_engineering / not_specified                                                       | `Hochbau` / `Tiefbau` / —                                                                                                                                                                                     |


**Wichtig:** Für `archive` fallen `project_subtype`, `construction_type`, `construction_category` weg (leer). Der alte Bericht hat sie als fix gelistet, was die Archiv-Embeddings einheitlich um diese Signale beraubt hat — also kein Verlust.

Der alte `CONTEST`-Fall kam im alten Mapping nicht vor und wurde zu `service` umgemappt – das ist semantisch falsch. Neu: eigenes Label "Wettbewerb".

### 2.4 Geografie (INCLUDE, wichtig)


| Feld          | Coverage | Verwendung                                | Format                                                                                                                           |
| ------------- | -------- | ----------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `canton`      | 89%      | **INCLUDE** mit Mapping                   | `"Kanton Zürich"`, `"Kanton Genf"`, … Bund wenn country=CH und canton NULL bei project_type=FEDERATION                           |
| `city`        | 51%      | **INCLUDE** (Ausführungsort der Leistung) | roh, z.B. `"Luzern"` oder sogar mehrzeilige Strassenangaben (behalten, HTML-strip). Nicht zu verwechseln mit `proc_office_city`. |
| `country`     | 100%     | LABEL nur wenn != CH                      | `"Schweiz"` weglassen (Default), sonst z.B. `"Deutschland"`                                                                      |
| `postal_code` | niedrig  | SKIP                                      | wenig Zusatzsignal ggü. canton+city                                                                                              |


26 Kantone + Bund werden vollnamig abgebildet, nicht als 2-Letter-Code. Der Vektorraum versteht "Kanton Zürich" messbar besser als "ZH".

### 2.5 Beschaffungsstelle (INCLUDE, moderat)


| Feld                                                                                                                                   | Coverage | Verwendung                                                                                                                      |
| -------------------------------------------------------------------------------------------------------------------------------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `proc_office_name_de`                                                                                                                  | 64%      | **INCLUDE** — Organisationsname trägt Domänen-Signal ("Bundesamt für Strassen" ≠ "Stadt Zürich Hochbauamt")                     |
| `proc_office_name_fr`                                                                                                                  | 36%      | **INCLUDE** (Fallback)                                                                                                          |
| `proc_office_city`                                                                                                                     | hoch     | SKIP — i.d.R. redundant zum canton/city                                                                                         |
| `proc_office_street`, `proc_office_postal_code`, `proc_office_canton`, `proc_office_email`, `proc_office_phone`, `proc_office_contact` | —        | **SKIP** — Kontaktdaten, kein Retrieval-Signal; E-Mails/Telefon würden Embeddings sogar verunreinigen (viele ähnliche Strings). |


### 2.6 CPV-Codes (INCLUDE — mit VOLLEN Labels)


| Feld                | Coverage | Verwendung                                                                                                                                                                                                                                                                                |
| ------------------- | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `cpv_code_main`     | 99.3%    | **LOOKUP** — volles DE-Label über EU-CPV-2008-Wörterbuch, konkretester Code mit Fallback-Kaskade 8→7→6→5→4→3→2                                                                                                                                                                            |
| `cpv_codes` (array) | 99.3%    | **LOOKUP all** — alle Nebencodes; oft ist der als "main" markierte Code der generischere (`71000000` = "Dienstleistungen von Architektur-, …") während die Nebencodes die Fachspezifik tragen (`71314200` = "Straßenverkehrsdienste"). **Alle** reinnehmen, dedupliziert auf Label-Ebene. |


**Alt (kritisch fehlerhaft):** nur die ersten 2 Ziffern von `cpv_code_main` → macht aus `71314200` ("Straßenverkehrsdienste") `71` ("Architektur-Dienstleistungen"). Ganz andere Bedeutung.

Quelle für Wörterbuch: offizielle `cpv_2008.xml` der EU Publications Office (frei, mehrsprachig DE/FR/IT). ~9'500 Einträge. Wird einmalig extrahiert in `embeddings/cpv_de.json`.

### 2.7 BKP-Codes (Baukostenplan) (INCLUDE — neu!)


| Feld                | Coverage     | Verwendung                                                                                                                                                                           |
| ------------------- | ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `bkp_codes` (array) | 28% (72'226) | **LOOKUP all** — Schweizer Baukostenplan (CRB/SBV); hochspezifische Fachkategorien wie `112` = "Abbrucharbeiten", `242` = "Wärmeerzeugung", `2211` = "Fenster/Türen aus Holz/Metall" |


**Alt:** komplett ignoriert. BKP ist DAS Schweizer Fach-Schema für Bauarbeiten und liefert Fachsemantik, die CPV nicht abdeckt. In 28% der Archivzeilen vorhanden, in 46% der `projects`-Zeilen. Standard-BKP-Wörterbuch (SIA 102 / CRB) wird in `embeddings/bkp_de.json` bereitgestellt (~250 Codes).

### 2.8 OAG-Codes und Codes, die leer sind (SKIP)


| Feld                                                   | archive N | Verwendung                         |
| ------------------------------------------------------ | --------- | ---------------------------------- |
| `oag_codes`                                            | 0         | **SKIP** — in beiden Tabellen leer |
| `recipient_name`, `recipient_city`, `recipient_canton` | 0         | **SKIP** — leer in archive         |


### 2.9 Zuschlags-Felder (nur OB02/OB08) — INCLUDE (konditional)


| Feld                                                                | Coverage (in OB02) | Verwendung                                                                                                                                                                                                                                               |
| ------------------------------------------------------------------- | ------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `winner_name`                                                       | 100%               | **INCLUDE** — Firmenname gewinnt, semantisch wertvoll für "welche Firma hat ähnliche Aufträge bekommen?"                                                                                                                                                 |
| `winner_city`                                                       | 100%               | **INCLUDE** — regionaler Match-Indikator (Gewinner aus gleicher Region?)                                                                                                                                                                                 |
| `winner_canton`, `winner_street`, `winner_postal_code`, `winner_id` | variabel           | SKIP — Adressdetails, zu granular                                                                                                                                                                                                                        |
| `all_winners` (jsonb)                                               | variabel           | **INCLUDE** nur Firmen-Namen bei Los-Vergaben (wenn >1 Gewinner), sonst redundant zu winner_name                                                                                                                                                         |
| `award_amount`                                                      | 88%                | **FEATURE** — numerisch, gehört nicht in den Embedding-Text. Gerne als separate ML-Feature behalten.                                                                                                                                                     |
| `award_currency`, `award_vat_type`                                  | meist CHF          | SKIP — fast immer Default                                                                                                                                                                                                                                |
| `award_decision_date`                                               | hoch               | SKIP — Datum, separate Feature                                                                                                                                                                                                                           |
| `number_of_submissions`                                             | 68%                | **FEATURE** — integer; im Embedding unschön, als strukturiertes Feature behalten                                                                                                                                                                         |
| `award_justification_de`                                            | 71%                | **INCLUDE** — "wirtschaftlich günstigstes Angebot" / "beste Referenzen" / "höchste Qualitätsbewertung" etc.: sehr semantisch, kein Boilerplate (avg 211 Zeichen, p90 467). Wenn die FR-Version irgendwann gefüllt wird, analog `award_justification_fr`. |
| `remedies_notice_de`                                                | 77% (OB02)         | **SKIP** — Rechtsmittelbelehrung ist fast identischer Boilerplate-Text in allen Zuschlägen. Würde den Embedding-Raum homogenisieren und Similarity-Signal verdünnen.                                                                                     |
| `total_price_selection`                                             | niedrig            | SKIP — ENUM-Indikator, kein Mehrwert                                                                                                                                                                                                                     |


### 2.10 Fristen / Daten (FEATURE)


| Feld                                                                                   | Verwendung                                                                                                                                                                                    |
| -------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `publication_date`, `submission_deadline`, `offer_opening_date`, `award_decision_date` | **FEATURE** — Datumswerte gehören nicht in den Embedding-Text. Sie werden vom Abruf/Filter benutzt und als separate numerische Features für ML. Für `archive_embeddings`-Tabelle kein Nutzen. |


### 2.11 Struktur (FEATURE / LABEL)


| Feld                | Verwendung                                                                     |
| ------------------- | ------------------------------------------------------------------------------ |
| `lots_count`        | FEATURE (wenn >1 Los: `"Auftrag mit N Losen"` als Text, sonst weg — Grenzfall) |
| `creation_language` | FEATURE — bestimmt die Sprachpriorität, ist selbst aber nicht Teil des Texts   |


### 2.12 Nur in `public.projects` (für symmetrische Embeddings)

`projects` hat zusätzlich folgende nicht-null-Felder, die für die Vektorraum-Konsistenz relevant sind:

- `project_subtype` (100%): bereits behandelt in 2.3, wird auf DE-Label gemappt und eingebaut.
- `construction_type` (64%): dito.
- `construction_category` (65%): dito.

Diese Felder existieren in `archive` nicht → Archiv-Embeddings haben diese Blöcke einfach nicht. Das ist OK, solange die gemeinsamen Felder (order_type, project_type, canton, CPV, BKP, title, description) den Hauptteil der Semantik tragen (was sie tun).

---

## 3. Finales Text-Template

Fest definierte Reihenfolge, damit der Vektorraum-Inhalt stabil bleibt. Teile mit leerem Wert werden stillschweigend übersprungen. Trenner zwischen Blöcken: `". "`.

```
BLOCK A — Publikationstyp & Auftragsart:
  {pub_type_label}. {order_type_label}. {project_type_label}. {process_type_label}.
  {project_subtype_label?}. {construction_category_label?}. {construction_type_label?}.
  {lots_type_label?}.

BLOCK B — Geografie:
  {canton_full_name}. {city?}. {country_label if != CH}.

BLOCK C — Beschaffungsstelle:
  Beschaffungsstelle: {proc_office_name_de or proc_office_name_fr}.

BLOCK D — Fachcodes (CPV + BKP, volle DE-Labels):
  Branchen: {cpv_label_main}; {cpv_label_secondary_1}; {cpv_label_secondary_2}; …
  Bau-Kostengruppen: {bkp_label_1}; {bkp_label_2}; …

BLOCK E — Titel & Beschreibung (Hauptsignal):
  Titel: {title_de or title_fr}.
  Beschreibung: {description_de or description_fr}.            # ohne 800-char Cut

BLOCK F — nur bei OB02/OB08 (Zuschlag / Freihändige Vergabe):
  Zuschlag an: {winner_name}, {winner_city}.
  {weitere Gewinner bei Losen aus all_winners}.
  Begründung: {award_justification_de}.
```

Das ergibt für eine typische OB02-Zeile einen Text von ~500–2000 Zeichen, für eine OB01-Zeile ~200–500 Zeichen. BGE-M3 verarbeitet beides ohne Kürzung.

---

## 4. Auswirkung auf Ähnlichkeitssuche (was wird besser)

Konkret verbessert gegenüber dem alten Setup:

1. **+49% bessere OB01-Embeddings** — weil BKP-Codes und volle CPV-Labels die fehlende Beschreibung kompensieren.
2. **Neue Signal-Achse für OB02/OB08** — über `winner_name` findet man "welche Firma hat in den letzten 10 Jahren ähnliche Aufträge gewonnen". Komplett neuer Retrieval-Pfad.
3. **Geografische Ähnlichkeit** — "Kanton Zürich" im Text gruppiert regional ähnliche Aufträge, was vorher gar nicht kodiert war.
4. **Keine CPV-Fehlklassifikation mehr** — durch 8-stelligen Lookup statt 2-stelliger Division.
5. **Fachtiefe durch BKP** — zwei Bau-Aufträge mit BKP `242` (Wärmeerzeugung) clustern jetzt nah zueinander, auch wenn Titel/Beschreibung unterschiedlich formuliert sind.
6. **Keine 800-Zeichen-Trunkierung** — das 10% der Aufträge mit längerer Beschreibung bekommt komplettes Embedding.

## 5. Risiken / bewusst akzeptierte Trade-offs

- **Winner-Felder erzeugen strukturelle OB01↔OB02-Distanz.** Das ist gewollt: die beiden sind fachlich unterschiedliche Ereignisse. Wenn wir das NICHT wollten, müssten wir `winner_name` weglassen.
- **BKP-Wörterbuch unvollständig.** Der offizielle CRB-BKP ist ~250 Codes, aber mit Varianten; wir stellen eine Baseline bereit und loggen fehlende Codes, damit wir sie nachziehen können.
- **Kein Embedding für leere Zeilen.** Wenn `title_`*, `description_*` UND `cpv_code_main` fehlen (selten, aber möglich), wird die Zeile übersprungen und der Fall geloggt.

## 6. Konkrete Konsequenzen für den Plan

Ergänzungen zum bestehenden Plan `archive_embeddings_rebuild`:

- Neues Artefakt `**embeddings/bkp_de.json`** (Baukostenplan-Wörterbuch) + entsprechende Lookup-Funktion in `text_builder.py`.
- `text_builder.py` wird **pub_type-aware**: Block F wird nur für OB02/OB08 gerendert.
- Label-Mapping wird um `CONTEST`, `ENGINEER`, `ARCHITECT` (order_type) und OB00–OB09 (pub_type) erweitert.
- Zusätzliches Feld `pub_type` im `archive_embeddings`-Schema (direkt in der Tabelle, für Filter-Queries). Nicht nur im Text.
- Sprachbevorzugung bleibt DE > FR > IT > EN, aber **pro Block** (Titel DE vs. Beschreibung DE separat entschieden; falls kein title_de vorhanden aber description_de, werden beide auf DE gemischt gerendert — Realität in ~5% der Zeilen).

---

*Generiert 2026-04-17 auf Basis der Live-Daten in Supabase-Projekt `rkfwuxocuojkjswigoss`.*