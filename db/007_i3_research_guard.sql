-- Defense in depth for the dedicated synthetic-only 004/005 staging schema.
-- This is a fixed-hash denylist, not proof that any other input is synthetic.
-- It does not create an importer or authorize writes of research material.
BEGIN;
DO $$ BEGIN
  IF current_database() !~ '^scriptura_staging_[a-zA-Z0-9_]+$' THEN
    RAISE EXCEPTION 'I-3 guard requires dedicated synthetic staging database';
  END IF;
  IF to_regclass('scriptura_d2_stage.snapshots') IS NULL OR NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conrelid='scriptura_d2_stage.snapshots'::regclass AND conname='i1_reject_frozen_d3_archive'
  ) THEN RAISE EXCEPTION 'apply synthetic staging 004 and guard 005 first'; END IF;
END $$;
ALTER TABLE scriptura_d2_stage.snapshots ADD CONSTRAINT i3_reject_frozen_d4_d5_d6_archives CHECK (
  archive_sha256 NOT IN (
    '05ab5bdf3fc258f39b926257c771ef4a17138355aa072cb8bc97c56387999beb',
    '4709ddbe914c276e68ebcc66cee1d76e1c096e0071992eb53b9e4c2f03e96d19',
    '6d94de447eba8517c038f6f709c8b1040e0c6efbdd4676f9e19aea568d3e59da'
  )
);
COMMIT;
