-- Refuse to drop any snapshot or provenance; run on disposable empty DB only.
BEGIN;
DO $$ BEGIN
  IF current_database() !~ '^scriptura_staging_[a-zA-Z0-9_]+$' THEN RAISE EXCEPTION 'not an isolated staging database'; END IF;
END $$;
LOCK TABLE scriptura_d2_stage.records, scriptura_d2_stage.snapshots IN ACCESS EXCLUSIVE MODE;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM scriptura_d2_stage.records) OR EXISTS (SELECT 1 FROM scriptura_d2_stage.snapshots) THEN
    RAISE EXCEPTION 'rollback refused: staging provenance exists';
  END IF;
END $$;
DROP TABLE scriptura_d2_stage.records RESTRICT;
DROP TABLE scriptura_d2_stage.snapshots RESTRICT;
DROP FUNCTION scriptura_d2_stage.reject_mutation() RESTRICT;
DROP SCHEMA scriptura_d2_stage RESTRICT;
COMMIT;
