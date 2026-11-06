-- Defense in depth for the dedicated synthetic-only staging schema.
-- A fixed ZIP hash denylist does not prove any other input is synthetic.
-- It does not authorize research import, staging or canonical promotion.
BEGIN;
DO $$ BEGIN
  IF current_database() !~ '^scriptura_staging_[a-zA-Z0-9_]+$' THEN
    RAISE EXCEPTION 'J-1 guard requires dedicated synthetic staging database';
  END IF;
  IF to_regclass('scriptura_d2_stage.snapshots') IS NULL OR NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conrelid='scriptura_d2_stage.snapshots'::regclass AND conname='i3_reject_frozen_d4_d5_d6_archives'
  ) THEN RAISE EXCEPTION 'apply synthetic staging 004 and guards 005 and 007 first'; END IF;
END $$;
ALTER TABLE scriptura_d2_stage.snapshots ADD CONSTRAINT j1_reject_frozen_d7_archive CHECK (
  archive_sha256 <> '8a8fb8d4efde68f639b99ab8edb9eab14c320b4bc9e64e0aab882af7ee0a4820'
);
COMMIT;
