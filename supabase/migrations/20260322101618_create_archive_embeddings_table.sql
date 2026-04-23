-- Exportiert aus Remote schema_migrations (version=20260322101618, name=create_archive_embeddings_table)
-- Generator: supabase/scripts/sync_migrations_from_remote.py

-- Archiv-Embeddings Tabelle fuer historische SIMAP-Daten (2010-2024)
-- Vergleichbar mit project_embeddings (gleiche Dimension 384, gleicher HNSW-Index)
CREATE TABLE IF NOT EXISTS archive_embeddings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  archive_project_id BIGINT NOT NULL UNIQUE,
  embedding vector(384) NOT NULL,
  text_hash TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- HNSW-Index fuer schnelle Cosine-Similarity-Suche (identisch zu project_embeddings)
CREATE INDEX IF NOT EXISTS idx_archive_embeddings_hnsw
  ON archive_embeddings USING hnsw (embedding vector_cosine_ops);

-- Index auf archive_project_id fuer schnelle Lookups
CREATE INDEX IF NOT EXISTS idx_archive_embeddings_project_id
  ON archive_embeddings (archive_project_id);

-- Kommentar
COMMENT ON TABLE archive_embeddings IS 'E5-small Embeddings (384-dim) fuer historische SIMAP-Archivprojekte 2010-2024. Vergleichbar mit project_embeddings.';
COMMENT ON COLUMN archive_embeddings.archive_project_id IS 'Referenz auf project_id in archiv_daten_2010-2024 (BIGINT, keine UUID).';
COMMENT ON COLUMN archive_embeddings.text_hash IS 'MD5 des Embedding-Rohtexts fuer inkrementelle Updates (gleiche Logik wie project_embeddings).';
