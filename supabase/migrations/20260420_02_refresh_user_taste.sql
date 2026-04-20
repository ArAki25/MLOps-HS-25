-- ===========================================================================
-- Rocchio-Taste-Vektor Aktualisierung (TASK 4 + FIX Archive-JOIN)
-- ===========================================================================
-- Berechnet v = alpha*mean(likes) - beta*mean(dislikes), anschliessend
-- L2-normalisiert.
--
-- pgvector 0.8 unterstuetzt keine direkte Scalar-Vector-Multiplikation, daher
-- wird der skalare Faktor per array_fill() in einen 1024-dim Vektor expandiert
-- und elementweise multipliziert.
--
-- Dualer JOIN: beruecksichtigt Likes/Dislikes von Projekten UND Archiv-Items.
-- ===========================================================================

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
  SELECT count(*) FILTER (WHERE rating =  1),
         count(*) FILTER (WHERE rating = -1)
    INTO v_likes, v_dis
  FROM ui.user_tender_ratings
  WHERE user_id = p_user_id;

  IF v_likes = 0 THEN
    DELETE FROM ui.user_taste_vectors WHERE user_id = p_user_id;
    RETURN;
  END IF;

  v_like_factor := array_fill((v_alpha::real / v_likes::real), ARRAY[1024])::vector;

  IF v_dis > 0 THEN
    v_dis_factor := array_fill((-v_beta::real / v_dis::real), ARRAY[1024])::vector;
  ELSE
    v_dis_factor := NULL;
  END IF;

  SELECT sum(
    CASE
      WHEN r.rating =  1 THEN e.embedding * v_like_factor
      WHEN r.rating = -1 AND v_dis > 0 THEN e.embedding * v_dis_factor
      ELSE NULL
    END
  )
  INTO v_raw
  FROM ui.user_tender_ratings r
  JOIN public.embeddings e ON (
    (r.source = 'project' AND e.project_id = r.tender_id::uuid AND e.source = 'project')
    OR
    (r.source = 'archive' AND e.archive_id = r.tender_id::uuid AND e.source = 'archive')
  )
  WHERE r.user_id = p_user_id
    AND (r.rating = 1 OR (r.rating = -1 AND v_dis > 0));

  IF v_raw IS NULL THEN
    DELETE FROM ui.user_taste_vectors WHERE user_id = p_user_id;
    RETURN;
  END IF;

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

COMMENT ON FUNCTION ui.refresh_user_taste(uuid) IS
  'Rocchio-Taste-Vektor aus Likes+Dislikes (projects UND archives). alpha=1.0, beta=0.3, L2-normalisiert.';
