# Supabase Migrationen

Die Dateinamen folgen dem Supabase-CLI-Format `<timestamp>_<name>.sql` und
entsprechen den Eintraegen in `supabase_migrations.schema_migrations` auf dem
verlinkten Projekt. Damit funktionieren `supabase migration list` und
`supabase db push` ohne Versionskonflikt.

## Neu aus Remote synchronisieren

Falls Historie und Repo wieder auseinanderlaufen (z. B. Migrationen nur im
Dashboard angewendet):

```bash
python3 supabase/scripts/sync_migrations_from_remote.py
```

Das Skript liest `schema_migrations` per `supabase db query --linked` und
schreibt die SQL-Dateien neu (Projekt muss verlinkt sein).

## Chronologie (Auszug)

| Timestamp | Inhalt (Kurz) |
|-----------|----------------|
| `20260322101618` | `archive_embeddings` (spaeter umbenannt, siehe unten) |
| `20260322101926` | RPC `get_similar_projects_all` |
| `20260414150037` | Tabelle `public.archive` |
| `20260415064419` | Pending-Indizes auf `archive` |
| `20260418122707` … `20260418125120` | Trigger-Fixes, Embeddings-Umbenennung |
| `20260420121807` … `20260420192357` | `ui.user_taste_vectors`, `refresh_user_taste`, Trigger, Recommend-RPC |
| `20260421091130` | Likes-only (`rating` nur noch `NULL`/`1`) |
| `20260423` | RLS/Indizes/`search_path`-Haertung (`01_db_optimizations`) |

Details stehen in den jeweiligen `.sql`-Dateien (Kopfkommentare aus dem Export).

## Vorbedingungen (nicht in diesem Ordner)

- Schema `ui` existiert.
- Tabellen: `ui.projects_ui`, `ui.user_profiles`, `ui.user_tender_ratings`
  (mit Spalte `source`).
- Tabelle: `public.embeddings` mit HNSW-Index auf `embedding`.
- Extension: `vector >= 0.7` (wegen `l2_normalize`).
