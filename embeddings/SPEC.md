# `public.archive_embeddings` — Spezifikation

Stand: 2026-04-17 (löst den alten Embedding-Bericht zu `project_embeddings`
(intfloat/multilingual-e5-small, 384d) vollständig ab).

## 1. Ziel

Ein einziger Vektorraum, der sowohl Einträge aus `public.projects` als auch
aus `public.archive` enthält, so dass Cross-Source-Ähnlichkeitssuche
(Projekt → ähnliche archive-Inserate und umgekehrt) mit einem einzigen
HNSW-Index möglich ist.

## 2. Modell

| Parameter              | Wert                                                           |
|-----------------------|-----------------------------------------------------------------|
| Modell                | **`BAAI/bge-m3`**                                               |
| Output-Dimension      | **1024** (vs. vorher 384)                                       |
| Kontextlänge          | 8192 Tokens (vorher 512 → deswegen gab es den 800-char-Cut)     |
| Sprachen              | 100+ inkl. DE/FR/IT/EN (SOTA Multilingual)                      |
| Normalisierung        | L2 (`normalize_embeddings=True`) → Cosine = Dot-Product         |
| Prefix                | **keiner** (bge-m3 braucht, anders als e5, keinen `passage:`)   |
| Precision beim Encode | FP16 auf CUDA/MPS, FP32 auf CPU                                 |
| Dtype in DB           | `vector(1024)` (pgvector, Wert als float32-JSON-Array serialisiert) |
| Distanz-Operator      | `<=>` (cosine) via HNSW-Index `vector_cosine_ops`               |

Entscheidung gegen `multilingual-e5-small`: der alte Stack hatte zwei
unnötige Schwächen: (a) der Prefix `passage: `/`query: ` ist inkonsistent
mit realen Use-Cases und bei Upgrades fragil, und (b) 512 Tokens zwangen zum
800-char-Cut der Beschreibungen — ca. 10 % der Ausschreibungen werden dadurch
gekappt. bge-m3 erledigt beides ohne Tricks, und das cross-lingual
Performance-Delta auf CH-DE/FR-Daten ist signifikant (beide Vektoren
liegen merklich näher beieinander).

## 3. Tabellenschema

Siehe `embeddings/schema.sql`. Wichtig:

* Partial Unique Indexes auf `project_id` (`source='project'`) und `archive_id`
  (`source='archive'`) ermöglichen Upsert via PostgREST `on_conflict`.
* FK-Constraints mit `ON DELETE CASCADE` — wird eine Basis-Row entfernt,
  verschwindet ihr Embedding automatisch.
* HNSW-Index `m=16`, `ef_construction=64` (pgvector-Defaults, Build ist bei 1024d
  + 260k Rows in wenigen Minuten durch).
* `text_hash` ist separat indiziert, damit Full-Rebuild-Checks schnell sind.
* RLS an, nur SELECT öffentlich, Writes via `service_role`.

## 4. Text-Konstruktion

Implementierung: `embeddings/text_builder.py` → `build_text(row, source)`.

Schema-agnostisch: `projects` und `archive` haben de facto identische
Spalten, der Builder nimmt beide an. Beachte die **zwei Dialekte**:

* `archive.pub_type` ∈ `{OB00..OB09}`, `order_type` UPPERCASE (`WORKS`, …),
  `project_type` = **Auftraggeber-Kategorie** (`MUNICIPALITY`, `CANTON`, …).
* `projects.pub_type` ∈ `{award, tender, abandonment, …}`, `order_type`
  lowercase (`construction`, …), `project_type` = **Beschaffungsform**
  (`tender`, `competition`, …).

Der Builder mappt beide Dialekte auf dieselben deutschen Labels
(`embeddings/dicts.py`) → derselbe Vektorraum.

### 4.1 Blockstruktur

Pro Row werden bis zu sechs Blöcke konstruiert; leere Blöcke werden
ausgelassen (kein "n/a"-Rauschen).

```
Publikation: {pub_type}. {order_type}. {project_type|procurer_type}. {process_type}.
             {project_subtype}. {construction_category}. {construction_type}.
Standort:    {kanton voller Name}[, {city}][, {country ≠ CH}].
Beschaffungsstelle: {name} ({city}, {kanton}).
Branchen/CPV: {code1 label1}; {code2 label2}; …
Bau-Kostengruppen (BKP): BKP {code1} {label1}; BKP {code2} {label2}; …
Titel: {title_de|fr|it|en}. Beschreibung: {description_de|fr|it|en}
Zuschlag an: {winner_name} ({winner_city}, {winner_canton}).
Weitere Zuschlagsempfänger: {…}.
Begründung: {award_justification_de|fr}.
```

### 4.2 Design-Entscheidungen

* **Spracheauswahl-Kaskade** DE > FR > IT > EN pro Feld. Die Labels bleiben
  immer DE — so bleibt der strukturelle Rahmen konstant und bge-m3
  verarbeitet den Inhalt in dessen Originalsprache.
* **Kanton voller Name**. `SG` → `St. Gallen`. Der alte Stack hatte `canton`
  gar nicht im Text, obwohl das Feld vorhanden ist.
* **CPV volle Labels**, alle sekundären Codes inklusive. Fallback-Kaskade
  8 → 7 → 6 → 5 → 4 → 3 → 2-Stellen; zusätzlich ein kleiner
  CPV-2003→2008-Translator für die ~57 Legacy-Codes in alten archive-Rows.
  Quelle des Wörterbuchs: [samhallskod/cpv-eu](https://github.com/samhallskod/cpv-eu)
  (offizielle EU-CPV-2008, CH nutzt 1:1 dieselbe Nomenklatur).
* **BKP-Labels** (Baukostenplan Hochbau & Tiefbau) neu inkludiert. War
  vorher komplett weggelassen, obwohl BKP für Bauprojekte extrem
  diskriminativ ist. Quelle: CRB-Standard (Hauptpositionen 0–9).
* **Kein 800-Zeichen-Cut**. Volle Beschreibung geht rein, bge-m3 macht den
  Rest.
* **HTML wird gestrippt** (`<p>` etc.), Whitespace normalisiert.
* **Award-Block nur bei Zuschlag-Typen** (`OB02`, `OB07`, `OB08`,
  `award` in v2). Bei Ausschreibungen (`OB01`, `tender`) wäre das Feld
  `winner_name` leer oder irreführend → wird ausgelassen.
* **`remedies_notice_de` wird NICHT eingebettet**. Das ist reiner
  Rechtsmittel-Boilerplate ("innert 20 Tagen Beschwerde…"), der das
  Embedding-Signal nur verwässert.

## 5. Inkrement-Update (Hash)

`text_hash` = `md5(raw_text)`. Beim Rebuild holt
`build_embeddings.py` pro Batch von 1000 Rows die bestehenden
`(id, text_hash)`-Paare aus `archive_embeddings` und re-encodiert nur,
wo der Hash sich geändert hat (oder kein Eintrag existiert). Typischer
täglicher Re-Run: >99 % `unchanged`, encoded wenige Hundert Rows.

## 6. Similarity / Retrieval

Normalisierung liegt in den Vektoren selbst, daher:

```sql
-- pgvector: Cosine-Distanz <=>, Similarity = 1 - <=>
SELECT (1 - (embedding <=> $1)) AS similarity, *
FROM public.archive_embeddings
ORDER BY embedding <=> $1
LIMIT 20;
```

Für gemeinsame Python-Seite (analog zum alten Code):

```python
# vektoren sind bereits L2-normalisiert → Cosine == Dot
sims = query_vec @ mat.T
```

Fertige RPC: `embeddings/search.sql` → `public.match_archive(query_embedding,
match_count, source_filter, pub_type_filter, canton_filter, min_similarity)`.

## 7. Build-Kommandos

```bash
# Einmalig: Schema anwenden (via Supabase SQL editor oder psql)
psql $SUPABASE_DIRECT_URL -f embeddings/schema.sql
psql $SUPABASE_DIRECT_URL -f embeddings/search.sql

# Smoke-Test (kein Encode, nur Text-Builder + Hash-Diff)
python -m embeddings.build_embeddings --source archive --limit 500 --dry-run

# Kleiner Re-Encode
python -m embeddings.build_embeddings --source archive --limit 2000

# Voller Rebuild
python -m embeddings.build_embeddings --source all
```

## 8. Kennzahlen nach vollem Rebuild (erwartet)

| Source   | Rows   | Text-Länge (Median) | Encode-Zeit (MPS FP16) |
|----------|--------|---------------------|------------------------|
| projects | 12 k   | ~650 chars          | ~1 min                 |
| archive  | 254 k  | ~750 chars          | ~45–90 min             |

Inkrementelle Runs: < 1 min bei normalem daily delta.

## 9. Downstream-Änderungen (separates Todo)

`ML/ml_aki.py` arbeitet heute noch mit 384d + `passage: `-Prefix. Nach
Verification der neuen Embeddings wird:

1. `EMBEDDING_MODEL_NAME` → `BAAI/bge-m3`, `EMBEDDING_DIM` → 1024
2. Die `passage: `-Zeilen in `_berechne_embeddings` entfernt
3. Das zum e5-384d-Raum passende PCA-Modell neu trainiert (PCA-Dim eventuell
   auf 128 statt 64 erhöht, weil die 1024-d-Vektoren mehr lineare Varianz
   tragen).
