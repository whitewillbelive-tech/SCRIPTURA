-- Remove this guard only from an empty disposable synthetic database.
BEGIN;
DO $$ BEGIN
  IF current_database() !~ '^scriptura_staging_[a-zA-Z0-9_]+$' THEN
    RAISE EXCEPTION 'J-1 guard rollback requires dedicated synthetic staging database';
  END IF;
END $$;
LOCK TABLE scriptura_d2_stage.snapshots, scriptura_d2_stage.records IN ACCESS EXCLUSIVE MODE;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM scriptura_d2_stage.snapshots) OR EXISTS (SELECT 1 FROM scriptura_d2_stage.records) THEN
    RAISE EXCEPTION 'rollback refused: staging provenance exists';
  END IF;
END $$;
ALTER TABLE scriptura_d2_stage.snapshots DROP CONSTRAINT j1_reject_frozen_d7_archive;
COMMIT;
