-- Exportiert aus Remote schema_migrations (version=20260420121922, name=refresh_user_taste_function_v2)
-- Generator: supabase/scripts/sync_migrations_from_remote.py

-- ============================================================
-- TASK 4 + TASK 5: Rocchio-Taste-Vektor (v2, pgvector 0.8 kompatibel)
-- ============================================================
CREATE OR REPLACE FUNCTION ui.refresh_user_taste(p_user_id uuid)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
  v_mean_like     vector(1024);
  v_mean_dis      vector(1024);
  v_raw           vector(1024);
  v_norm          vector(1024);
  v_likes         int;
  v_dis           int;
  v_alpha         real := 1.0;
  v_beta          real := 0.3;
BEGIN
  -- Mittelwerte getrennt berechnen, damit NULL bei fehlenden Dislikes
  -- nicht den gesamten Ausdruck auf NULL zieht.
  SELECT
    avg(e.embedding) FILTER (WHERE r.rating =  1),
    avg(e.embedding) FILTER (WHERE r.rating = -1),
    count(*)         FILTER (WHERE r.rating =  1),
    count(*)         FILTER (WHERE r.rating = -1)
  INTO v_mean_like, v_mean_dis, v_likes, v_dis
  FROM ui.user_tender_ratings r
  JOIN public.embeddings e
    ON e.project_id = r.tender_id::uuid
   AND e.source    = 'project'
  WHERE r.user_id = p_user_id;

  -- Ohne Likes kein sinnvoller Taste-Vektor.
  IF v_mean_like IS NULL OR v_likes = 0 THEN
    DELETE FROM ui.user_taste_vectors WHERE user_id = p_user_id;
    RETURN;
  END IF;

  -- pgvector 0.8: Skalarmultiplikation ist nur als  vector * real  definiert.
  IF v_mean_dis IS NULL THEN
    v_raw := v_mean_like * v_alpha;
  ELSE
    v_raw := (v_mean_like * v_alpha) - (v_mean_dis * v_beta);
  END IF;

  BEGIN
    v_norm := l2_normalize(v_raw);
  EXCEPTION WHEN OTHERS THEN
    -- Null-Norm (Rocchio hat den Vektor auf 0 gezogen): Eintrag löschen.
    DELETE FROM ui.user_taste_vectors WHERE user_id = p_user_id;
    RETURN;
  END;

  -- Zusätzlicher Safety-Check: wenn l2_normalize zurückgibt, aber Norm ≈ 0.
  IF v_norm IS NULL THEN
    DELETE FROM ui.user_taste_vectors WHERE user_id = p_user_id;
    RETURN;
  END IF;

  INSERT INTO ui.user_taste_vectors AS t (user_id, v, n_likes, n_dislikes, updated_at)
  VALUES (p_user_id, v_norm, v_likes, v_dis, now())
  ON CONFLICT (user_id) DO UPDATE
  SET v          = EXCLUDED.v,
      n_likes    = EXCLUDED.n_likes,
      n_dislikes = EXCLUDED.n_dislikes,
      updated_at = now();
END;
$$;
