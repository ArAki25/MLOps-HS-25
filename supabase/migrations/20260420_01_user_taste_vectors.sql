-- ===========================================================================
-- Materialisierte Taste-Vektoren (TASK 5)
-- ===========================================================================
-- Jeder User bekommt einen zwischengespeicherten Rocchio-Taste-Vektor, damit
-- der Recommender-RPC nicht bei jedem Feed-Load neu aggregieren muss.
-- Trigger siehe 03_refresh_user_taste_trigger.sql.
-- ===========================================================================

CREATE TABLE IF NOT EXISTS ui.user_taste_vectors (
  user_id    uuid PRIMARY KEY,
  v          vector(1024) NOT NULL,
  n_likes    integer NOT NULL DEFAULT 0,
  n_dislikes integer NOT NULL DEFAULT 0,
  updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE ui.user_taste_vectors ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS user_taste_vectors_self_read ON ui.user_taste_vectors;
CREATE POLICY user_taste_vectors_self_read
  ON ui.user_taste_vectors
  FOR SELECT
  USING (auth.uid() = user_id);

COMMENT ON TABLE ui.user_taste_vectors IS
  'Pro User ein vorberechneter Rocchio-Taste-Vektor (1024-dim, L2-normiert).';
