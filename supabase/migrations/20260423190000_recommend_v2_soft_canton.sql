-- ============================================================================
-- recommend_projects_for_user_v2: Multi-Canton Soft-Filter
--
-- Aenderungen gegenüber der vorherigen Version:
--   - Hard-Filter  pu.canton = v_canton  entfernt.
--   - Liest preferred_cantons (text[]) aus ui.user_profiles.
--   - Kanton-Matching als Soft-Boost (+15 %) auf den Cosine-Similarity-Score,
--     wenn das Projekt in einem der bevorzugten Kantone liegt.
--   - Fallback: kein preferred_cantons-Eintrag => kein Boost, kein Filter.
--   - Subtype- und Budget-Hard-Filter bleiben unveraendert.
-- ============================================================================

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
  taste_vector        vector(1024);
  v_preferred_cantons text[];
  v_subtype           varchar;
  v_min               numeric;
  v_max               numeric;
BEGIN
  -- 1. Materialisierten Rocchio-Taste-Vektor lesen.
  SELECT tv.v INTO taste_vector
  FROM ui.user_taste_vectors tv
  WHERE tv.user_id = p_user_id;

  IF taste_vector IS NULL THEN
    RETURN;
  END IF;

  -- 2. Profil-Filter laden.
  --    preferred_cantons: neues Multi-Canton-Array.
  --    Fallback auf ARRAY[canton] wenn das Array leer ist (Altdaten).
  SELECT
    CASE
      WHEN cardinality(up.preferred_cantons) > 0 THEN up.preferred_cantons
      WHEN up.canton IS NOT NULL AND up.canton <> '' THEN ARRAY[up.canton]
      ELSE NULL
    END,
    up.project_subtype,
    up.award_amount_min,
    up.award_amount_max
  INTO v_preferred_cantons, v_subtype, v_min, v_max
  FROM ui.user_profiles up
  WHERE up.user_id = p_user_id;

  -- 3. Vektor-kNN mit Soft-Canton-Boost; kein Hard-Filter auf Kanton.
  RETURN QUERY
  SELECT
    pu.id,
    pu.title_de,
    pu.description_de,
    pu.canton,
    pu.project_subtype,
    pu.award_amount,
    (
      (1 - (e.embedding <=> taste_vector))
      * CASE
          WHEN v_preferred_cantons IS NULL         THEN 1.0
          WHEN pu.canton = ANY(v_preferred_cantons) THEN 1.15
          ELSE 1.0
        END
    )::double precision AS similarity,
    e.embedding
  FROM ui.projects_ui pu
  JOIN public.embeddings e ON e.project_id = pu.id AND e.source = 'project'
  WHERE pu.project_subtype = v_subtype
    AND (v_min  IS NULL OR pu.award_amount >= v_min)
    AND (v_max  IS NULL OR pu.award_amount <= v_max)
    AND NOT EXISTS (
      SELECT 1 FROM ui.user_tender_ratings r
      WHERE r.user_id = p_user_id AND r.tender_id = pu.id::text
    )
  ORDER BY
    (1 - (e.embedding <=> taste_vector))
    * CASE
        WHEN v_preferred_cantons IS NULL         THEN 1.0
        WHEN pu.canton = ANY(v_preferred_cantons) THEN 1.15
        ELSE 1.0
      END
    DESC
  LIMIT match_count_pool;
END;
$$;

COMMENT ON FUNCTION ui.recommend_projects_for_user_v2(uuid, integer) IS
  'Liefert Top-N Kandidaten-Pool mit Embeddings fuer MMR-Reranking. '
  'Kanton: Soft-Boost +15 % fuer alle preferred_cantons (text[]). '
  'Subtype / Budget bleiben als Hard-Filter. '
  'Materialisierter Rocchio-Vektor aus ui.user_taste_vectors.';

GRANT EXECUTE ON FUNCTION ui.recommend_projects_for_user_v2(uuid, integer)
  TO anon, authenticated, service_role;
