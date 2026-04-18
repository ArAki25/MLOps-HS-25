# SQL-Hilfsskripte (Betrieb)

Das **kanonische Schema** (Tabelle `public.embeddings`, Indizes, Trigger, RLS) pflegt ihr in **Supabase** (Migrations / SQL-Editor). Entsprechende DDL-Dateien `embeddings/schema.sql` und `embeddings/search.sql` sind **lokal** üblich, aber per **`.gitignore`** nicht auf GitHub.

Dieser Ordner enthält nur **Werkzeuge** für wiederkehrende Ops:

| Datei | Zweck |
|-------|--------|
| `embeddings_bulk_backfill.sql` | Vor/nach großem Embedding-Load: Indexe droppen bzw. HNSW wieder aufbauen |
| `hnsw_rebuild_psql.sql` | HNSW-Neuaufbau mit `psql` (lange Läufe; umgeht SQL-Editor-Timeouts) |

Einmalige Migrationen liegen in der **Supabase Migration History** im Dashboard, nicht zwingend hier im Git.
