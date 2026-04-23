-- Exportiert aus Remote schema_migrations (version=20260421091130, name=20260421_01_likes_only)
-- Generator: supabase/scripts/sync_migrations_from_remote.py

DELETE FROM ui.user_tender_ratings WHERE rating = -1;

ALTER TABLE ui.user_tender_ratings
  DROP CONSTRAINT IF EXISTS user_tender_ratings_rating_check;

ALTER TABLE ui.user_tender_ratings
  ADD CONSTRAINT user_tender_ratings_rating_check
  CHECK (rating IS NULL OR rating = 1);

ALTER TABLE ui.user_taste_vectors
  DROP COLUMN IF EXISTS n_dislikes;

CREATE OR REPLACE FUNCTION ui.refresh_user_taste(p_user_id uuid)
RETURNS void
LANGUAGE plpgsql
AS $func$
DECLARE
  v_likes       int;
  v_like_factor vector(1024);
  v_raw         vector(1024);
  v_norm        vector(1024);
BEGIN
  SELECT count(*) FILTER (WHERE rating = 1)
    INTO v_likes
  FROM ui.user_tender_ratings
  WHERE user_id = p_user_id;

  IF v_likes = 0 THEN
    DELETE FROM ui.user_taste_vectors WHERE user_id = p_user_id;
    RETURN;
  END IF;

  v_like_factor := array_fill((1.0::real / v_likes::real), ARRAY[1024])::vector;

  SELECT sum(e.embedding * v_like_factor)
    INTO v_raw
  FROM ui.user_tender_ratings r
  JOIN public.embeddings e ON (
    (r.source = 'project' AND e.project_id = r.tender_id::uuid AND e.source = 'project')
    OR
    (r.source = 'archive' AND e.archive_id = r.tender_id::uuid AND e.source = 'archive')
  )
  WHERE r.user_id = p_user_id
    AND r.rating = 1;

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

  INSERT INTO ui.user_taste_vectors AS t (user_id, v, n_likes, updated_at)
  VALUES (p_user_id, v_norm, v_likes, now())
  ON CONFLICT (user_id) DO UPDATE
  SET v          = EXCLUDED.v,
      n_likes    = EXCLUDED.n_likes,
      updated_at = now();
END;
$func$;

COMMENT ON FUNCTION ui.refresh_user_taste(uuid) IS
  'Likes-only Centroid-Taste-Vektor (projects UND archives), L2-normalisiert.';

DO $blk$
DECLARE
  rec_user uuid;
BEGIN
  FOR rec_user IN
    SELECT DISTINCT user_id FROM ui.user_tender_ratings
  LOOP
    PERFORM ui.refresh_user_taste(rec_user);
  END LOOP;

  DELETE FROM ui.user_taste_vectors tv
  WHERE NOT EXISTS (
    SELECT 1 FROM ui.user_tender_ratings utr
    WHERE utr.user_id = tv.user_id AND utr.rating = 1
  );
END
$blk$;
