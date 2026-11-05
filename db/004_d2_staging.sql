-- Synthetic testing only. Never run in the canonical or an existing project database.
BEGIN;
DO $$ BEGIN
  IF current_database() !~ '^scriptura_staging_[a-zA-Z0-9_]+$' THEN
    RAISE EXCEPTION 'staging migration requires a dedicated scriptura_staging_ database';
  END IF;
  IF EXISTS (
    SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE c.relkind IN ('r','p','v','m','f') AND n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg\_%'
  ) THEN RAISE EXCEPTION 'staging database must not contain existing user tables or views'; END IF;
END $$;
CREATE SCHEMA scriptura_d2_stage;
REVOKE ALL ON SCHEMA scriptura_d2_stage FROM PUBLIC;
CREATE TABLE scriptura_d2_stage.snapshots (
  snapshot_id text PRIMARY KEY CHECK (snapshot_id ~ '^TEST-SYNTHETIC-[A-Za-z0-9._-]{1,100}$'),
  archive_sha256 text NOT NULL CHECK (archive_sha256 ~ '^[0-9a-f]{64}$' AND archive_sha256 <> 'c8b64b9144367a8526c77b121b3343f04a7c683276f9fd239b2cc51458589a47'),
  origin_zip text NOT NULL CHECK (origin_zip ~ '^[A-Za-z0-9._-]{1,160}[.]zip$'),
  record_count integer NOT NULL CHECK (record_count >= 0),
  metadata_hash text NOT NULL CHECK (metadata_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE scriptura_d2_stage.records (
  snapshot_id text NOT NULL REFERENCES scriptura_d2_stage.snapshots(snapshot_id),
  record_type text NOT NULL CHECK (record_type IN ('sources','editions','locators','rights','passages','alignments','agents','affiliations','claims','evidence','relations','reviews')),
  record_id text NOT NULL CHECK (record_id ~ '^[A-Za-z0-9][A-Za-z0-9._:/-]{0,191}$'),
  origin_file text NOT NULL CHECK (origin_file = 'd2/records_merged/' || record_type || '.jsonl'),
  row_number integer NOT NULL CHECK (row_number > 0),
  origin_file_sha256 text NOT NULL CHECK (origin_file_sha256 ~ '^[0-9a-f]{64}$'),
  original_sha256 text NOT NULL CHECK (original_sha256 ~ '^[0-9a-f]{64}$'),
  disposition text NOT NULL CHECK (disposition IN ('eligible','quarantined','blocked')),
  reasons text[] NOT NULL,
  validation_status text,
  rights_action text CHECK (rights_action IS NULL OR rights_action IN ('browse','collect_metadata','store_raw','store_excerpt','index_fulltext','embed','send_to_model','redistribute','public_link')),
  rights_decision text CHECK (rights_decision IS NULL OR rights_decision IN ('allowed','conditional','unknown','prohibited')),
  rights_edition_id text CHECK (rights_edition_id IS NULL OR rights_edition_id ~ '^[A-Za-z0-9][A-Za-z0-9._:/-]{0,191}$'),
  PRIMARY KEY (snapshot_id,record_type,record_id),
  UNIQUE (snapshot_id,origin_file,row_number),
  CHECK ((record_type='rights' AND rights_action IS NOT NULL AND rights_decision IS NOT NULL AND rights_edition_id IS NOT NULL) OR (record_type<>'rights' AND rights_action IS NULL AND rights_decision IS NULL AND rights_edition_id IS NULL))
);
CREATE FUNCTION scriptura_d2_stage.reject_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'staging provenance is append-only' USING ERRCODE='55000'; END $$;
CREATE TRIGGER staging_snapshots_immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON scriptura_d2_stage.snapshots FOR EACH STATEMENT EXECUTE FUNCTION scriptura_d2_stage.reject_mutation();
CREATE TRIGGER staging_records_immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON scriptura_d2_stage.records FOR EACH STATEMENT EXECUTE FUNCTION scriptura_d2_stage.reject_mutation();
REVOKE ALL ON ALL TABLES IN SCHEMA scriptura_d2_stage FROM PUBLIC;
COMMIT;
