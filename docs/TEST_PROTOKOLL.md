# Testprotokoll — Recommender-System

Ziel: Wir wollen empirisch sehen, ob die Embedding-basierten Empfehlungen
**mit der Zeit praezieser** werden, wenn ein User (Firma) Ausschreibungen
liked/disliked.

## 1. Voraussetzungen

- Migrationen aus `supabase/migrations/` sind in Supabase angewendet
  (insb. `ui.user_taste_vectors`, `ui.refresh_user_taste`, Trigger, v2-RPC).
- Flask-App laeuft (`cd simap_ui && python app.py`).
- ENV gesetzt:
  - `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`
  - Fuer das Dashboard: `ENABLE_TEST_DASHBOARD=true`

## 2. Test-User anlegen

```bash
python scripts/create_test_companies.py
```

Legt 5 Firmen-Logins an (idempotent). Ergebnis: `scripts/test_companies.json`.

| Firma                         | Kanton | Subtype      | Betragsband         |
|-------------------------------|--------|--------------|---------------------|
| Muster Bau AG Zuerich         | ZH     | construction | 100k – 5M           |
| Alpen Hochbau Bern AG         | BE     | construction | 50k – 2M            |
| City Services ZH GmbH         | ZH     | service      | 20k – 800k          |
| Tech Supply Zuerich AG        | ZH     | supply       | 10k – 1.5M          |
| Graubuenden Holzbau AG        | GR     | construction | 80k – 3M            |

## 3. Ablauf pro Firma

1. **Login** mit Testzugang (siehe Ausgabe des Seed-Skripts).
2. **Onboarding**: ~20 Karten (Mix aus Archive + Projects) bewerten.
   - Likes: 👍 fuer alles, was plausibel zum Firmenprofil passt.
   - Dislikes: 👎 fuer alles, was offensichtlich nicht passt.
3. **Profil abschliessen** → wird auf `/publications` weitergeleitet.
4. **Tab „Empfehlungen"** oeffnen → erste 10 Vorschlaege sichten.
   Snapshot: Titel der Top-10 notieren (Runde A).
5. **Tab „Ausschreibungen"**: 5–10 Items liken/disliken
   (👍 / 👎 rechts in jeder Zeile).
6. **Tab „Empfehlungen"** erneut oeffnen → Snapshot Runde B.
7. Schritt 5 + 6 **2–3 Iterationen** wiederholen, um die Entwicklung zu sehen.

Die Empfehlungen **sollen zwischen Runde A, B, C messbar homogener pro
Profil** werden (hoeherer `avg_similarity_top_n`) und **diverser innerhalb
einer Runde** (niedrigerer `avg_pairwise_cosine_mmr`).

## 4. Quantitative Auswertung

Oeffne `http://localhost:5000/admin/test-runs`. Zeigt pro Test-User:

- Anzahl Likes / Dislikes
- Taste-Vektor-Status
- **avg_similarity_top_n** — wie nah sind die Top-10 am Profil?
  Zielwert `>= 0.55`.
- **avg_pairwise_cosine** — baseline (ohne MMR) vs. MMR.
  Zielwert MMR `<= 0.75`.
- Top-5 Empfehlungen mit Score.

### JSON-Variante (praktisch fuer Skripte)

```bash
curl -s http://localhost:5000/api/admin/test-runs | jq .
```

## 5. Erwartete Beobachtungen

| Metrik                          | Nach Onboarding | Nach 10–20 Likes  |
|---------------------------------|-----------------|-------------------|
| avg_similarity_top_n            | ~0.45 – 0.55    | **>= 0.55**       |
| avg_pairwise_cosine_mmr (Top-10)| ~0.70 – 0.80    | **<= 0.75**       |
| Diff Baseline ↔ MMR             | ~+0.05 – +0.10  | stabil positiv    |
| Firmen-Spezifitaet              | noch generisch  | klar unterschiedlich |

Wenn zwei Firmen mit unterschiedlichem Profil (z. B. ZH construction vs
ZH service) **am Ende klar andere Top-5** haben, ist das Grundsignal da.

## 6. Troubleshooting

- **„Taste aktiv: fehlt"** → Onboarding unvollstaendig oder 0 Likes.
  Mindestens 1 Like noetig, damit `refresh_user_taste` einen Vektor schreibt.
- **Empfehlungen leer** → Hard-Filter im Profil matcht keine offenen
  Projekte. Pruefe in Supabase:
  ```sql
  SELECT count(*) FROM ui.projects_ui
  WHERE canton='ZH' AND project_subtype='construction';
  ```
- **avg_pairwise_cosine_mmr bleibt hoch** → MMR_LAMBDA / MMR_MIN_DIVERSITY
  in `simap_ui/supabase_client.py` nachjustieren (Default 0.7 / 0.3).

## 7. Reset fuer naechsten Durchlauf

```sql
-- Alle Ratings und Taste-Vektoren eines Test-Users loeschen
DELETE FROM ui.user_tender_ratings WHERE user_id = '<uuid>';
DELETE FROM ui.user_taste_vectors   WHERE user_id = '<uuid>';
UPDATE ui.user_profiles SET onboarding_completed=false WHERE user_id = '<uuid>';
```
