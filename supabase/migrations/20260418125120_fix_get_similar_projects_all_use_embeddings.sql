-- Exportiert aus Remote schema_migrations (version=20260418125120, name=fix_get_similar_projects_all_use_embeddings)
-- Generator: supabase/scripts/sync_migrations_from_remote.py

CREATE OR REPLACE FUNCTION public.get_similar_projects_all(
  p_project_id uuid,
  match_threshold double precision DEFAULT 0.3,
  match_count integer DEFAULT 10,
  include_archive boolean DEFAULT true
)
RETURNS TABLE(source text, ref_id text, similarity double precision)
LANGUAGE sql
STABLE
AS $function$
  WITH query_embedding AS (
    SELECT e.embedding
    FROM public.embeddings e
    WHERE e.source = 'project' AND e.project_id = p_project_id
    LIMIT 1
  ),
  current_matches AS (
    SELECT
      'current'::text AS source,
      pe.project_id::text AS ref_id,
      (1 - (pe.embedding <=> qe.embedding))::double precision AS similarity
    FROM public.embeddings pe
    CROSS JOIN query_embedding qe
    WHERE pe.source = 'project'
      AND pe.project_id <> p_project_id
      AND (1 - (pe.embedding <=> qe.embedding)) >= match_threshold
  ),
  archive_matches AS (
    SELECT
      'archive'::text AS source,
      ae.archive_project_id::text AS ref_id,
      (1 - (ae.embedding <=> qe.embedding))::double precision AS similarity
    FROM public.embeddings ae
    CROSS JOIN query_embedding qe
    WHERE include_archive
      AND ae.source = 'archive'
      AND (1 - (ae.embedding <=> qe.embedding)) >= match_threshold
  ),
  combined AS (
    SELECT * FROM current_matches
    UNION ALL
    SELECT * FROM archive_matches
  )
  SELECT c.source, c.ref_id, c.similarity
  FROM combined c
  ORDER BY c.similarity DESC
  LIMIT match_count;
$function$;

GRANT EXECUTE ON FUNCTION public.get_similar_projects_all TO PUBLIC, anon, authenticated, service_role;
