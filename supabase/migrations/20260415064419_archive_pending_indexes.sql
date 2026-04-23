-- Exportiert aus Remote schema_migrations (version=20260415064419, name=archive_pending_indexes)
-- Generator: supabase/scripts/sync_migrations_from_remote.py

-- Helps pending detail selection be fast and stable
CREATE INDEX IF NOT EXISTS idx_archive_pending_pubid
  ON public.archive (simap_publication_id)
  WHERE detail_fetched_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_archive_pending_project
  ON public.archive (simap_project_id)
  WHERE detail_fetched_at IS NULL;
