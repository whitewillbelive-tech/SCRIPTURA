-- Non-destructive correction: ordinary UPDATE, DELETE and TRUNCATE cannot rewrite audit events.
BEGIN;
CREATE FUNCTION scriptura_reject_audit_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'audit events are append-only' USING ERRCODE = '55000';
END;
$$;
CREATE TRIGGER review_events_append_only BEFORE UPDATE OR DELETE OR TRUNCATE ON review_events
  FOR EACH STATEMENT EXECUTE FUNCTION scriptura_reject_audit_mutation();
CREATE TRIGGER provenance_events_append_only BEFORE UPDATE OR DELETE OR TRUNCATE ON provenance_events
  FOR EACH STATEMENT EXECUTE FUNCTION scriptura_reject_audit_mutation();
COMMIT;
