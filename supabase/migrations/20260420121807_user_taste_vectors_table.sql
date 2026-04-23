-- Exportiert aus Remote schema_migrations (version=20260420121807, name=user_taste_vectors_table)
-- Generator: supabase/scripts/sync_migrations_from_remote.py

-- ============================================================
-- TASK 5: Materialisierte User-Taste-Vektoren
-- Tabelle wird von ui.refresh_user_taste() befüllt und von
-- einem Trigger auf ui.user_tender_ratings aktuell gehalten.
-- ============================================================
CREATE TABLE IF NOT EXISTS ui.user_taste_vectors (
  user_id       uuid PRIMARY KEY,
  v             vector(1024) NOT NULL,
  n_likes       integer NOT NULL DEFAULT 0,
  n_dislikes    integer NOT NULL DEFAULT 0,
  updated_at    timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE  ui.user_taste_vectors IS 'Materialisierter Rocchio-Taste-Vektor pro User. Wird via Trigger aus ui.user_tender_ratings aktualisiert.';
COMMENT ON COLUMN ui.user_taste_vectors.v          IS 'L2-normalisierter Rocchio-Vektor: alpha*mean(likes) - beta*mean(dislikes), anschliessend l2_normalize().';
COMMENT ON COLUMN ui.user_taste_vectors.n_likes    IS 'Anzahl positiver Ratings, die in den Vektor eingeflossen sind.';
COMMENT ON COLUMN ui.user_taste_vectors.n_dislikes IS 'Anzahl negativer Ratings, die in den Vektor eingeflossen sind.';

-- Kein HNSW-Index notwendig: Lookup ist immer per PK (user_id).
-- Ein HNSW-Index ueber ui.user_taste_vectors.v waere nur sinnvoll
-- fuer User-to-User-Aehnlichkeit ("Firmen wie du"), aktuell nicht gebraucht.

ALTER TABLE ui.user_taste_vectors ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS user_taste_vectors_self_read ON ui.user_taste_vectors;
CREATE POLICY user_taste_vectors_self_read
  ON ui.user_taste_vectors FOR SELECT
  USING (auth.uid() = user_id);
