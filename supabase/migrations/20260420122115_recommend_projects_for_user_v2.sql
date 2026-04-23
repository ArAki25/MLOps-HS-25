-- Exportiert aus Remote schema_migrations (version=20260420122115, name=recommend_projects_for_user_v2)
-- Generator: supabase/scripts/sync_migrations_from_remote.py

-- ============================================================
-- TASK 4: Recommender-RPC v2
--
-- Unterschiede zur Vorgaengerversion:
--  1. Liest den materialisierten Rocchio-Vektor aus
--     ui.user_taste_vectors statt ihn bei jedem Call zu bilden.
--  2. Gibt zusaetzlich das Embedding jedes Kandidaten zurueck,
--     damit die Flask-Route danach MMR rechnen kann.
--  3. Erlaubt via match_count_pool einen groesseren Kandidaten-Pool
--     (typisch 50), aus dem MMR die final sichtbaren N auswaehlt.
--
-- Der alte Hard-Filter (canton/subtype/award_amount) bleibt unveraendert
-- drin. Das umbauen auf Soft-Filter ist Task 3 und kommt separat.
-- ============================================================
CREATE OR REPLACE FUNCTION ui.recommend_projects_for_user_v2(
  p_user_id        uuid,
  match_count_pool integer DEFAULT 50
)
RETURNS TABLE (
  id               uuid,
  title_de         text,
  description_de   text,
  canton           varchar,
  project_subtype  varchar,
  award_amount     numeric,
  similarity       double precision,
  embedding        vector(1024)
)
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
  taste_vector  vector(1024);
  v_canton      varchar;
  v_subtype     varchar;
  v_min         numeric;
  v_max         numeric;
BEGIN
  -- 1. Materialisierten Taste-Vektor lesen (Task 5).
  SELECT tv.v INTO taste_vector
  FROM ui.user_taste_vectors tv
  WHERE tv.user_id = p_user_id;

  IF taste_vector IS NULL THEN
    -- Kein Taste-Vektor -> kein Ranking moeglich, leere Liste.
    RETURN;
  END IF;

  -- 2. Profil-Filter
  SELECT up.canton, up.project_subtype, up.award_amount_min, up.award_amount_max
    INTO v_canton, v_subtype, v_min, v_max
  FROM ui.user_profiles up
  WHERE up.user_id = p_user_id;

  -- 3. HNSW-kNN gegen public.embeddings (source='project'),
  --    Hard-Filter ueber projects_ui-Join.
  RETURN QUERY
  SELECT
    pu.id,
    pu.title_de,
    pu.description_de,
    pu.canton,
    pu.project_subtype,
    pu.award_amount,
    (1 - (e.embedding <=> taste_vector))::double precision AS similarity,
    e.embedding
  FROM ui.projects_ui pu
  JOIN public.embeddings e ON e.project_id = pu.id AND e.source = 'project'
  WHERE pu.canton          = v_canton
    AND pu.project_subtype = v_subtype
    AND pu.award_amount   >= v_min
    AND (v_max IS NULL OR pu.award_amount <= v_max)
    AND NOT EXISTS (
      SELECT 1 FROM ui.user_tender_ratings r
      WHERE r.user_id = p_user_id AND r.tender_id = pu.id::text
    )
  ORDER BY e.embedding <=> taste_vector
  LIMIT match_count_pool;
END;
$$;

COMMENT ON FUNCTION ui.recommend_projects_for_user_v2(uuid, integer) IS
  'Liefert Top-N Kandidaten-Pool mit Embeddings fuer MMR-Reranking in der App-Schicht. Nutzt den materialisierten Rocchio-Vektor aus ui.user_taste_vectors.';

GRANT EXECUTE ON FUNCTION ui.recommend_projects_for_user_v2(uuid, integer) TO anon, authenticated, service_role;
