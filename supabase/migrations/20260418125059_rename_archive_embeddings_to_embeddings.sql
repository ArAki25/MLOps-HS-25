-- Exportiert aus Remote schema_migrations (version=20260418125059, name=rename_archive_embeddings_to_embeddings)
-- Generator: supabase/scripts/sync_migrations_from_remote.py

ALTER TABLE public.archive_embeddings RENAME TO embeddings;

CREATE OR REPLACE FUNCTION public.match_archive(
  query_embedding  vector(1024),
  match_count      integer DEFAULT 20,
  source_filter    text    DEFAULT NULL,
  pub_type_filter  text[]  DEFAULT NULL,
  canton_filter    text[]  DEFAULT NULL,
  min_similarity   float4  DEFAULT 0.0
)
RETURNS TABLE (
  embedding_id            bigint,
  source                  text,
  project_id              uuid,
  archive_id              uuid,
  archive_publication_id  text,
  archive_project_id      text,
  pub_type                text,
  language                text,
  similarity              float4,
  raw_text_preview        text
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
  RETURN QUERY
  WITH joined AS (
    SELECT
      e.id                       AS embedding_id,
      e.source,
      e.project_id,
      e.archive_id,
      e.archive_publication_id,
      e.archive_project_id,
      e.pub_type,
      e.language,
      (1 - (e.embedding <=> query_embedding))::float4 AS similarity,
      e.raw_text_preview,
      COALESCE(p.canton, a.canton) AS eff_canton
    FROM public.embeddings e
    LEFT JOIN public.projects p ON (e.source = 'project' AND p.id = e.project_id)
    LEFT JOIN public.archive  a ON (e.source = 'archive' AND a.id = e.archive_id)
    WHERE
      (source_filter  IS NULL OR e.source   = source_filter)
      AND (pub_type_filter IS NULL OR e.pub_type = ANY (pub_type_filter))
  )
  SELECT j.embedding_id, j.source, j.project_id, j.archive_id,
         j.archive_publication_id, j.archive_project_id,
         j.pub_type, j.language, j.similarity, j.raw_text_preview
  FROM joined j
  WHERE (canton_filter IS NULL OR j.eff_canton = ANY (canton_filter))
    AND j.similarity >= min_similarity
  ORDER BY j.similarity DESC
  LIMIT match_count;
END;
$$;

COMMENT ON FUNCTION public.match_archive IS
  'Nearest-neighbor search across archive+projects in the unified 1024d bge-m3 vector space. Pass source_filter / pub_type_filter / canton_filter / min_similarity to narrow down. query_embedding must be L2-normalized (same normalization as build pipeline).';

GRANT EXECUTE ON FUNCTION public.match_archive TO anon, authenticated, service_role;
