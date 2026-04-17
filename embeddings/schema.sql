-- ===========================================================================
-- archive_embeddings: unified pgvector table for public.projects + public.archive
-- Model: BAAI/bge-m3 (1024 dim, cosine, normalize_embeddings=True)
-- Run as postgres/service role once. Idempotent via IF NOT EXISTS / DO blocks.
-- ===========================================================================

CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------------------
-- 1. Archive-Legacy-Tabellen umbenennen (falls vorhanden), sanft und reversibel
-- ---------------------------------------------------------------------------
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relname = 'archive_embeddings' AND c.relkind = 'r'
  ) THEN
    -- Unterscheide: wenn schon 1024d, nicht umbenennen; sonst als v1 deprecaten
    IF EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name   = 'archive_embeddings'
        AND column_name  = 'embedding'
        AND udt_name     = 'vector'
    ) AND EXISTS (
      SELECT 1 FROM pg_attribute a
      JOIN pg_class c ON c.oid = a.attrelid
      JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname = 'public' AND c.relname = 'archive_embeddings'
        AND a.attname = 'embedding' AND format_type(a.atttypid, a.atttypmod) = 'vector(1024)'
    ) THEN
      RAISE NOTICE 'archive_embeddings existiert bereits mit vector(1024) - lasse unangetastet';
    ELSE
      EXECUTE 'ALTER TABLE public.archive_embeddings RENAME TO archive_embeddings_v1_deprecated';
      RAISE NOTICE 'archive_embeddings -> archive_embeddings_v1_deprecated';
    END IF;
  END IF;

  IF EXISTS (
    SELECT 1 FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relname = 'project_embeddings' AND c.relkind = 'r'
  ) THEN
    EXECUTE 'ALTER TABLE public.project_embeddings RENAME TO project_embeddings_v1_deprecated';
    RAISE NOTICE 'project_embeddings -> project_embeddings_v1_deprecated';
  END IF;
END$$;

-- ---------------------------------------------------------------------------
-- 2. Unified archive_embeddings anlegen
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.archive_embeddings (
  id                      BIGSERIAL PRIMARY KEY,
  source                  TEXT NOT NULL CHECK (source IN ('project','archive')),
  project_id              UUID,                                       -- FK to public.projects.id
  archive_id              UUID,                                       -- FK to public.archive.id
  archive_publication_id  TEXT,                                       -- simap_publication_id (redundant, for fast filters)
  archive_project_id      TEXT,                                       -- simap_project_id (archive only)
  pub_type                TEXT,                                       -- OB00..OB09
  language                TEXT,                                       -- DE | FR | IT | EN
  text_hash               TEXT NOT NULL,                              -- md5(raw_text)
  raw_text_preview        TEXT,                                       -- first ~500 chars for debug
  embedding               vector(1024) NOT NULL,
  embedding_model         TEXT NOT NULL DEFAULT 'BAAI/bge-m3',
  created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT proj_xor_archive CHECK (
    (source = 'project' AND project_id IS NOT NULL AND archive_id IS NULL)
    OR (source = 'archive' AND archive_id IS NOT NULL AND project_id IS NULL)
  )
);

-- Foreign keys (separat, damit DDL im Falle fehlender Basis-Tabelle nicht crasht)
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_class WHERE relname = 'projects' AND relnamespace = 'public'::regnamespace)
     AND NOT EXISTS (
       SELECT 1 FROM pg_constraint WHERE conname = 'archive_embeddings_project_id_fkey'
     ) THEN
    ALTER TABLE public.archive_embeddings
      ADD CONSTRAINT archive_embeddings_project_id_fkey
      FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;
  END IF;

  IF EXISTS (SELECT 1 FROM pg_class WHERE relname = 'archive' AND relnamespace = 'public'::regnamespace)
     AND NOT EXISTS (
       SELECT 1 FROM pg_constraint WHERE conname = 'archive_embeddings_archive_id_fkey'
     ) THEN
    ALTER TABLE public.archive_embeddings
      ADD CONSTRAINT archive_embeddings_archive_id_fkey
      FOREIGN KEY (archive_id) REFERENCES public.archive(id) ON DELETE CASCADE;
  END IF;
END$$;

-- ---------------------------------------------------------------------------
-- 3. Indizes
-- ---------------------------------------------------------------------------
CREATE UNIQUE INDEX IF NOT EXISTS archive_emb_proj_uniq
  ON public.archive_embeddings (project_id)
  WHERE source = 'project';

CREATE UNIQUE INDEX IF NOT EXISTS archive_emb_archive_uniq
  ON public.archive_embeddings (archive_id)
  WHERE source = 'archive';

CREATE INDEX IF NOT EXISTS archive_emb_archive_pid
  ON public.archive_embeddings (archive_project_id)
  WHERE source = 'archive';

CREATE INDEX IF NOT EXISTS archive_emb_archive_pub
  ON public.archive_embeddings (archive_publication_id)
  WHERE source = 'archive';

CREATE INDEX IF NOT EXISTS archive_emb_source    ON public.archive_embeddings (source);
CREATE INDEX IF NOT EXISTS archive_emb_pub_type  ON public.archive_embeddings (pub_type);
CREATE INDEX IF NOT EXISTS archive_emb_hash      ON public.archive_embeddings (text_hash);

-- HNSW für Cosine (Vektoren sind normalisiert → Cosine == Dot)
CREATE INDEX IF NOT EXISTS archive_emb_vec_hnsw
  ON public.archive_embeddings
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

-- ---------------------------------------------------------------------------
-- 4. Trigger: updated_at automatisch mitführen
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.archive_embeddings_touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS archive_embeddings_touch ON public.archive_embeddings;
CREATE TRIGGER archive_embeddings_touch
  BEFORE UPDATE ON public.archive_embeddings
  FOR EACH ROW EXECUTE FUNCTION public.archive_embeddings_touch_updated_at();

-- ---------------------------------------------------------------------------
-- 5. RLS + Permissions
-- ---------------------------------------------------------------------------
ALTER TABLE public.archive_embeddings ENABLE ROW LEVEL SECURITY;

-- Readable durch anon/auth (nur SELECT; Writes gehen via service_role/ETL)
DROP POLICY IF EXISTS archive_embeddings_read ON public.archive_embeddings;
CREATE POLICY archive_embeddings_read
  ON public.archive_embeddings FOR SELECT
  USING (true);

COMMENT ON TABLE public.archive_embeddings IS
  'Unified pgvector 1024d embeddings (BAAI/bge-m3) for public.projects and public.archive. Same vector space -> cross-source similarity search. See embeddings/SPEC.md for text construction spec.';
