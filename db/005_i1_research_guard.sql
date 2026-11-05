-- Defense in depth for the isolated synthetic-only staging schema.
-- This does not read or load research material or change the existing 004 migration.
BEGIN;
DO $$ BEGIN
  IF current_database() !~ '^scriptura_staging_[a-zA-Z0-9_]+$' THEN
    RAISE EXCEPTION 'I-1 guard requires dedicated synthetic staging database';
  END IF;
  IF to_regclass('scriptura_d2_stage.snapshots') IS NULL THEN
    RAISE EXCEPTION 'apply 004 in an empty dedicated staging database first';
  END IF;
END $$;
ALTER TABLE scriptura_d2_stage.snapshots ADD CONSTRAINT i1_reject_frozen_d3_archive
  CHECK (archive_sha256 <> 'baf206d2846544f1e1bb20622ac10c557394b71aa41cfd6e2be5bbafade347be');
COMMIT;
