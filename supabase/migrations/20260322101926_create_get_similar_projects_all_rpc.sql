-- Exportiert aus Remote schema_migrations (version=20260322101926, name=create_get_similar_projects_all_rpc)
-- Generator: supabase/scripts/sync_migrations_from_remote.py

-- Unified RPC: Sucht aehnliche Projekte in BEIDEN Embedding-Tabellen
-- (project_embeddings fuer aktuelle Projekte + archive_embeddings fuer Archiv 2010-2024)
--
-- Parameter:
--   p_project_id     UUID eines aktuellen Projekts aus `projects`
--   match_threshold  Minimale Cosine-Similarity (Standard 0.3)
--   match_count      Maximale Treffer gesamt (Standard 10)
--   include_archive  Archiv-Embeddings einbeziehen (Standard TRUE)
--
-- Gibt zurueck:
--   source           'current' oder 'archive'
--   ref_id           UUID (aktuelle Projekte) oder project_id als TEXT (Archiv)
--   similarity       Cosine-Similarity [0,1]

CREATE OR REPLACE FUNCTION get_similar_projects_all(
  p_project_id     UUID,
  match_threshold  FLOAT DEFAULT 0.3,
  match_count      INT   DEFAULT 10,
  include_archive  BOOLEAN DEFAULT TRUE
)
RETURNS TABLE (
  source      TEXT,
  ref_id      TEXT,
  similarity  FLOAT
)
LANGUAGE sql
STABLE
AS $$
  WITH query_embedding AS (
    -- Embedding des Quellprojekts aus project_embeddings holen
    SELECT embedding
    FROM   project_embeddings
    WHERE  project_id = p_project_id
    LIMIT  1
  ),
  current_matches AS (
    -- Aehnliche aktuelle Projekte (ohne das Quellprojekt selbst)
    SELECT
      'current'                        AS source,
      pe.project_id::TEXT              AS ref_id,
      1 - (pe.embedding <=> qe.embedding) AS similarity
    FROM   project_embeddings pe
    CROSS JOIN query_embedding qe
    WHERE  pe.project_id <> p_project_id
      AND  1 - (pe.embedding <=> qe.embedding) >= match_threshold
  ),
  archive_matches AS (
    -- Aehnliche Archivprojekte (nur wenn include_archive = TRUE)
    SELECT
      'archive'                         AS source,
      ae.archive_project_id::TEXT       AS ref_id,
      1 - (ae.embedding <=> qe.embedding) AS similarity
    FROM   archive_embeddings ae
    CROSS JOIN query_embedding qe
    WHERE  include_archive = TRUE
      AND  1 - (ae.embedding <=> qe.embedding) >= match_threshold
  ),
  combined AS (
    SELECT * FROM current_matches
    UNION ALL
    SELECT * FROM archive_matches
  )
  SELECT source, ref_id, similarity
  FROM   combined
  ORDER  BY similarity DESC
  LIMIT  match_count;
$$;

COMMENT ON FUNCTION get_similar_projects_all IS
  'Sucht aehnliche SIMAP-Projekte in project_embeddings (aktuelle) und archive_embeddings (2010-2024) per Cosine-Similarity. Gibt kombinierte, nach Aehnlichkeit sortierte Ergebnisse zurueck.';
