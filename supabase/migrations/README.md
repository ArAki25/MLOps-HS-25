# Supabase Migrationen

Alle DB-Objekte, die fuer das Recommender-System noetig sind, liegen
versioniert in diesem Ordner. Die Dateien sind chronologisch nummeriert
und koennen in dieser Reihenfolge auf eine leere DB angewendet werden:

```
supabase db reset                                # lokal (falls verwendet)
# oder per Supabase-MCP apply_migration einzeln anwenden
```

## Reihenfolge

1. `20260420_01_user_taste_vectors.sql`
   - Tabelle `ui.user_taste_vectors` (materialisierte Rocchio-Vektoren).
2. `20260420_02_refresh_user_taste.sql`
   - Funktion `ui.refresh_user_taste(uuid)`.
   - Beruecksichtigt Likes/Dislikes von **projects und archives**.
3. `20260420_03_refresh_user_taste_trigger.sql`
   - Trigger `trg_user_tender_ratings_refresh_taste`.
4. `20260420_04_recommend_projects_v2.sql`
   - RPC `ui.recommend_projects_for_user_v2` (HNSW-kNN + Hard-Filter).

## Vorbedingungen (nicht in diesem Ordner)

- Schema `ui` existiert.
- Tabellen: `ui.projects_ui`, `ui.user_profiles`, `ui.user_tender_ratings`
  (mit Spalte `source`).
- Tabelle: `public.embeddings` mit HNSW-Index auf `embedding`.
- Extension: `vector >= 0.7` (wegen `l2_normalize`).
