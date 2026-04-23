-- Exportiert aus Remote schema_migrations (version=20260420121832, name=refresh_user_taste_function)
-- Generator: supabase/scripts/sync_migrations_from_remote.py

-- ============================================================
-- TASK 4 + TASK 5: Rocchio-Taste-Vektor berechnen und materialisieren
--
-- Formel:
--   raw = alpha * avg(embedding WHERE rating = +1)
--       - beta  * avg(embedding WHERE rating = -1)
--   v   = l2_normalize(raw)
--
-- Parameter (hartkodiert fuer v1, spaeter ueber Settings-Tabelle):
--   alpha = 1.0  -- Gewicht der Likes
--   beta  = 0.3  -- Gewicht der Dislikes
--
-- Semantik:
--   - Wenn Rocchio-Rohvektor nicht existiert oder Null-Norm hat
--     (z.B. keine Ratings), wird die Zeile GELÖSCHT.
--   - Sonst wird sie via UPSERT aktualisiert.
-- ============================================================
CREATE OR REPLACE FUNCTION ui.refresh_user_taste(p_user_id uuid)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
  v_raw     vector(1024);
  v_norm    vector(1024);
  v_likes   int;
  v_dis     int;
  v_alpha   real := 1.0;
  v_beta    real := 0.3;
BEGIN
  SELECT
    (v_alpha * avg(e.embedding) FILTER (WHERE r.rating = 1))
  - (v_beta  * COALESCE(avg(e.embedding) FILTER (WHERE r.rating = -1),
                         ARRAY_FILL(0::real, ARRAY[1024])::vector)),
    count(*) FILTER (WHERE r.rating = 1),
    count(*) FILTER (WHERE r.rating = -1)
  INTO v_raw, v_likes, v_dis
  FROM ui.user_tender_ratings r
  JOIN public.embeddings e
    ON e.project_id = r.tender_id::uuid
   AND e.source    = 'project'
  WHERE r.user_id = p_user_id;

  IF v_raw IS NULL OR v_likes = 0 THEN
    DELETE FROM ui.user_taste_vectors WHERE user_id = p_user_id;
    RETURN;
  END IF;

  BEGIN
    v_norm := l2_normalize(v_raw);
  EXCEPTION WHEN OTHERS THEN
    DELETE FROM ui.user_taste_vectors WHERE user_id = p_user_id;
    RETURN;
  END;

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
  'Berechnet Rocchio-Taste-Vektor (alpha=1.0, beta=0.3) aus ui.user_tender_ratings und materialisiert ihn in ui.user_taste_vectors. Delete-Semantik, wenn keine Likes vorhanden sind.';
