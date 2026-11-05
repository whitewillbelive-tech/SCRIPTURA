-- Only removes enforcement from an empty audit log; no event data is deleted.
BEGIN;
LOCK TABLE review_events, provenance_events IN ACCESS EXCLUSIVE MODE;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM review_events) OR EXISTS (SELECT 1 FROM provenance_events) THEN
    RAISE EXCEPTION 'rollback refused: audit history exists';
  END IF;
END $$;
DROP TRIGGER review_events_append_only ON review_events;
DROP TRIGGER provenance_events_append_only ON provenance_events;
DROP FUNCTION scriptura_reject_audit_mutation();
COMMIT;
