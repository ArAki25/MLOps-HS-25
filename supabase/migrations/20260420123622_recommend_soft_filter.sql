-- Exportiert aus Remote schema_migrations (version=20260420123622, name=recommend_soft_filter)
-- Generator: supabase/scripts/sync_migrations_from_remote.py

DROP FUNCTION IF EXISTS ui.recommend_projects_for_user(uuid, integer);

CREATE FUNCTION ui.recommend_projects_for_user(p_user_id uuid, match_count integer DEFAULT 20)
RETURNS TABLE(id uuid, title_de text, description_de text, canton character varying, project_subtype character varying, award_amount numeric, similarity double precision)
LANGUAGE sql STABLE SECURITY DEFINER
AS $$
  SELECT
    pu.id,
    pu.title_de,
    pu.description_de,
    pu.canton,
    pu.project_subtype,
    pu.award_amount,
    (1 - (pe.embedding <=> taste.vec))::float8
  FROM (
    SELECT avg(e.embedding) AS vec
    FROM ui.user_tender_ratings r
    JOIN public.embeddings e ON e.project_id = r.tender_id::uuid AND e.source = 'project'
    WHERE r.user_id = p_user_id AND r.rating = 1
  ) taste,
  (
    SELECT canton, project_subtype, award_amount_min, award_amount_max
    FROM ui.user_profiles
    WHERE user_id = p_user_id
  ) up,
  public.embeddings pe
  JOIN ui.projects_ui pu ON pu.id = pe.project_id
  WHERE pe.source = 'project'
    AND taste.vec IS NOT NULL
    AND NOT EXISTS (
      SELECT 1 FROM ui.user_tender_ratings r2
      WHERE r2.user_id = p_user_id AND r2.tender_id = pu.id::text
    )
  ORDER BY
    (1 - (pe.embedding <=> taste.vec))
    * CASE WHEN pu.canton = up.canton THEN 1.15 ELSE 1.0 END
    * CASE WHEN pu.project_subtype = up.project_subtype THEN 1.10 ELSE 1.0 END
    * CASE
        WHEN pu.award_amount IS NULL THEN 1.0
        WHEN pu.award_amount BETWEEN up.award_amount_min AND COALESCE(up.award_amount_max, 999999999) THEN 1.05
        ELSE 0.85
      END
    DESC
  LIMIT match_count;
$$;
