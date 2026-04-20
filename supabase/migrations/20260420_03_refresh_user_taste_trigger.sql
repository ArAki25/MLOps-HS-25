-- ===========================================================================
-- Auto-Refresh Trigger fuer ui.user_taste_vectors
-- ===========================================================================
-- Feuert bei INSERT/UPDATE/DELETE auf ui.user_tender_ratings und ruft
-- ui.refresh_user_taste() fuer den betroffenen User auf.
-- ===========================================================================

CREATE OR REPLACE FUNCTION ui.tg_user_tender_ratings_refresh_taste()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    PERFORM ui.refresh_user_taste(OLD.user_id);
    RETURN OLD;
  ELSIF TG_OP = 'UPDATE' THEN
    IF OLD.user_id IS DISTINCT FROM NEW.user_id THEN
      PERFORM ui.refresh_user_taste(OLD.user_id);
    END IF;
    PERFORM ui.refresh_user_taste(NEW.user_id);
    RETURN NEW;
  ELSE
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
