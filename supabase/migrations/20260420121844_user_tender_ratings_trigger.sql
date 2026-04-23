-- Exportiert aus Remote schema_migrations (version=20260420121844, name=user_tender_ratings_trigger)
-- Generator: supabase/scripts/sync_migrations_from_remote.py

-- ============================================================
-- TASK 5: Trigger - haelt ui.user_taste_vectors synchron
-- mit ui.user_tender_ratings (INSERT / UPDATE / DELETE).
-- ============================================================
CREATE OR REPLACE FUNCTION ui.tg_user_tender_ratings_refresh_taste()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  -- INSERT / UPDATE: NEW.user_id ist betroffen.
  -- DELETE:          OLD.user_id ist betroffen.
  -- UPDATE mit user_id-Change: beide Seiten müssen aktualisiert werden.
  IF TG_OP = 'DELETE' THEN
    PERFORM ui.refresh_user_taste(OLD.user_id);
    RETURN OLD;
  ELSIF TG_OP = 'UPDATE' THEN
    IF OLD.user_id IS DISTINCT FROM NEW.user_id THEN
      PERFORM ui.refresh_user_taste(OLD.user_id);
    END IF;
    PERFORM ui.refresh_user_taste(NEW.user_id);
    RETURN NEW;
  ELSE  -- INSERT
    PERFORM ui.refresh_user_taste(NEW.user_id);
    RETURN NEW;
  END IF;
END;
$$;

DROP TRIGGER IF EXISTS trg_user_tender_ratings_refresh_taste ON ui.user_tender_ratings;
CREATE TRIGGER trg_user_tender_ratings_refresh_taste
AFTER INSERT OR UPDATE OR DELETE ON ui.user_tender_ratings
FOR EACH ROW
EXECUTE FUNCTION ui.tg_user_tender_ratings_refresh_taste();

COMMENT ON TRIGGER trg_user_tender_ratings_refresh_taste ON ui.user_tender_ratings IS
  'Rebuildet den Rocchio-Taste-Vektor in ui.user_taste_vectors bei jedem Rating-Change.';
