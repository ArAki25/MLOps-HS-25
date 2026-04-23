-- Exportiert aus Remote schema_migrations (version=20260420122017, name=refresh_user_taste_function_v3)
-- Generator: supabase/scripts/sync_migrations_from_remote.py

-- ============================================================
-- TASK 4 + TASK 5: Rocchio-Taste-Vektor (v3)
--
-- pgvector 0.8 kennt weder  vector*real  noch  real*vector.
-- Workaround: Rocchio als gewichtete Summe umformulieren:
--   v = sum( embedding_i * per_row_factor )
-- mit per_row_factor = alpha/N_like bzw. -beta/N_dis,
-- verpackt als 1024-dim konstanter Vektor via array_fill.
-- ============================================================
CREATE OR REPLACE FUNCTION ui.refresh_user_taste(p_user_id uuid)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
  v_likes        int;
  v_dis          int;
  v_alpha        real := 1.0;
  v_beta         real := 0.3;
  v_like_factor  vector(1024);
  v_dis_factor   vector(1024);
  v_raw          vector(1024);
  v_norm         vector(1024);
BEGIN
  -- 1. Likes/Dislikes zählen
  SELECT count(*) FILTER (WHERE rating =  1),
         count(*) FILTER (WHERE rating = -1)
    INTO v_likes, v_dis
  FROM ui.user_tender_ratings
  WHERE user_id = p_user_id;

  -- 2. Ohne Likes kein sinnvoller Taste-Vektor.
  IF v_likes = 0 THEN
    DELETE FROM ui.user_taste_vectors WHERE user_id = p_user_id;
    RETURN;
  END IF;

  -- 3. Skalar-Faktor als konstanter 1024-d Vektor kodieren
  --    (pgvector unterstützt vector * vector element-weise).
  v_like_factor := array_fill((v_alpha::real / v_likes::real), ARRAY[1024])::vector;

  IF v_dis > 0 THEN
    v_dis_factor := array_fill((-v_beta::real / v_dis::real), ARRAY[1024])::vector;
  ELSE
    v_dis_factor := NULL;
  END IF;

  -- 4. Rocchio = sum( embedding * per-row-factor )
  SELECT sum(
    CASE
      WHEN r.rating =  1 THEN e.embedding * v_like_factor
      WHEN r.rating = -1 AND v_dis > 0 THEN e.embedding * v_dis_factor
      ELSE NULL
    END
  )
  INTO v_raw
  FROM ui.user_tender_ratings r
  JOIN public.embeddings e
    ON e.project_id = r.tender_id::uuid
   AND e.source    = 'project'
  WHERE r.user_id = p_user_id
    AND (r.rating = 1 OR (r.rating = -1 AND v_dis > 0));

  IF v_raw IS NULL THEN
    DELETE FROM ui.user_taste_vectors WHERE user_id = p_user_id;
    RETURN;
  END IF;

  -- 5. Normalisieren (l2_normalize gibt Null-Vektor bei 0-Norm zurück,
  --    dann würde der Cosine-Vergleich undefined sein -> löschen).
  BEGIN
    v_norm := l2_normalize(v_raw);
  EXCEPTION WHEN OTHERS THEN
    DELETE FROM ui.user_taste_vectors WHERE user_id = p_user_id;
    RETURN;
  END;

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
