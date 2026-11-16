-- C-01 additive schema. Apply only to an isolated SCRIPTURA database after 003.
-- No research content is ingested or approved by this migration.
BEGIN;

CREATE TABLE c01_research_versions (
  id TEXT PRIMARY KEY,
  parent_id TEXT REFERENCES c01_research_versions(id),
  version_label TEXT NOT NULL,
  archive_sha256 TEXT NOT NULL CHECK (archive_sha256 ~ '^[a-f0-9]{64}$'),
  manifest_sha256 TEXT NOT NULL CHECK (manifest_sha256 ~ '^[a-f0-9]{64}$'),
  data_class TEXT NOT NULL CHECK (data_class IN ('synthetic','scholarly_candidate')),
  receipt_status TEXT NOT NULL DEFAULT 'quarantined' CHECK (receipt_status IN ('quarantined','validated','rejected')),
  received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK (id IS DISTINCT FROM parent_id),
  UNIQUE (archive_sha256, manifest_sha256)
);
CREATE FUNCTION c01_check_version_parent() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.parent_id IS NOT NULL AND NOT EXISTS
      (SELECT 1 FROM c01_research_versions WHERE id = NEW.parent_id AND data_class = NEW.data_class) THEN
    RAISE EXCEPTION 'missing or cross-class baseline version' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER c01_version_parent_check BEFORE INSERT ON c01_research_versions FOR EACH ROW EXECUTE FUNCTION c01_check_version_parent();
CREATE TRIGGER c01_versions_append_only BEFORE UPDATE OR DELETE OR TRUNCATE ON c01_research_versions
  FOR EACH STATEMENT EXECUTE FUNCTION scriptura_reject_audit_mutation();

-- A contributor to a document is not automatically a claim's speaker.
CREATE TABLE c01_source_contributors (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL REFERENCES sources(id),
  agent_id TEXT NOT NULL REFERENCES agents(id),
  contributor_role TEXT NOT NULL CHECK (contributor_role IN ('author','editor','translator','publisher','other')),
  source_locator_id TEXT REFERENCES source_locators(id),
  assertion_status TEXT NOT NULL DEFAULT 'recorded' CHECK (assertion_status IN ('recorded','source_checked','disputed')),
  reviewer_agent_id TEXT REFERENCES agents(id),
  CHECK (assertion_status <> 'source_checked' OR (source_locator_id IS NOT NULL AND reviewer_agent_id IS NOT NULL)),
  UNIQUE (source_id, agent_id, contributor_role)
);

-- Actor and target are distinct: external criticism does not become self-description.
CREATE TABLE c01_agent_relations (
  id TEXT PRIMARY KEY,
  actor_agent_id TEXT NOT NULL REFERENCES agents(id),
  target_agent_id TEXT NOT NULL REFERENCES agents(id),
  relation_kind TEXT NOT NULL CHECK (relation_kind IN ('external_criticism','institutional_description','reported_affiliation','research_subject','publication_by','other')),
  source_locator_id TEXT REFERENCES source_locators(id),
  assertion_status TEXT NOT NULL DEFAULT 'recorded' CHECK (assertion_status IN ('recorded','source_checked','disputed')),
  reviewer_agent_id TEXT REFERENCES agents(id),
  CHECK (actor_agent_id <> target_agent_id),
  CHECK (assertion_status <> 'source_checked' OR (source_locator_id IS NOT NULL AND reviewer_agent_id IS NOT NULL))
);

CREATE FUNCTION c01_check_graph_assertion() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE loc_status text; loc_source text; actor_class text; target_class text; source_class text; reviewer_class text;
BEGIN
  IF TG_TABLE_NAME = 'c01_source_contributors' THEN
    SELECT data_class INTO actor_class FROM agents WHERE id = NEW.agent_id;
    SELECT data_class INTO source_class FROM sources WHERE id = NEW.source_id;
    IF (actor_class = 'synthetic') IS DISTINCT FROM (source_class = 'synthetic') THEN
      RAISE EXCEPTION 'synthetic and non-synthetic records cannot be mixed' USING ERRCODE='23514';
    END IF;
  ELSE
    SELECT data_class INTO actor_class FROM agents WHERE id = NEW.actor_agent_id;
    SELECT data_class INTO target_class FROM agents WHERE id = NEW.target_agent_id;
    IF (actor_class = 'synthetic') IS DISTINCT FROM (target_class = 'synthetic') THEN
      RAISE EXCEPTION 'synthetic and non-synthetic records cannot be mixed' USING ERRCODE='23514';
    END IF;
  END IF;
  IF NEW.reviewer_agent_id IS NOT NULL THEN
    SELECT data_class INTO reviewer_class FROM agents WHERE id = NEW.reviewer_agent_id;
    IF (actor_class = 'synthetic') IS DISTINCT FROM (reviewer_class = 'synthetic') THEN
      RAISE EXCEPTION 'synthetic and non-synthetic records cannot be mixed' USING ERRCODE='23514';
    END IF;
  END IF;
  IF NEW.source_locator_id IS NOT NULL THEN
    SELECT l.verification_status, l.source_id, s.data_class INTO loc_status, loc_source, source_class
      FROM source_locators l JOIN sources s ON s.id = l.source_id WHERE l.id = NEW.source_locator_id;
    IF (actor_class = 'synthetic') IS DISTINCT FROM (source_class = 'synthetic') THEN
      RAISE EXCEPTION 'synthetic and non-synthetic records cannot be mixed' USING ERRCODE='23514';
    END IF;
    IF TG_TABLE_NAME = 'c01_source_contributors' THEN
      IF loc_source IS DISTINCT FROM NEW.source_id THEN
        RAISE EXCEPTION 'locator source mismatch' USING ERRCODE='23514';
      END IF;
    END IF;
  END IF;
  IF NEW.assertion_status = 'source_checked' AND loc_status IS DISTINCT FROM 'checked' THEN
    RAISE EXCEPTION 'checked source required' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER c01_contributor_check BEFORE INSERT OR UPDATE ON c01_source_contributors FOR EACH ROW EXECUTE FUNCTION c01_check_graph_assertion();
CREATE TRIGGER c01_agent_relation_check BEFORE INSERT OR UPDATE ON c01_agent_relations FOR EACH ROW EXECUTE FUNCTION c01_check_graph_assertion();

-- A checked assertion cannot silently change the identity or position of its evidence.
-- Status can still be disputed; the effective views then stop calling it checked.
CREATE FUNCTION c01_lock_checked_locator_identity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF (NEW.source_id, NEW.locator_type, NEW.locator_value, NEW.direct_url, NEW.quote_sha256)
       IS DISTINCT FROM (OLD.source_id, OLD.locator_type, OLD.locator_value, OLD.direct_url, OLD.quote_sha256)
     AND (EXISTS (SELECT 1 FROM c01_source_contributors WHERE source_locator_id=OLD.id AND assertion_status='source_checked')
       OR EXISTS (SELECT 1 FROM c01_agent_relations WHERE source_locator_id=OLD.id AND assertion_status='source_checked')) THEN
    RAISE EXCEPTION 'retract checked C-01 assertions before changing locator identity' USING ERRCODE='55000';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER c01_locator_identity_lock BEFORE UPDATE ON source_locators FOR EACH ROW EXECUTE FUNCTION c01_lock_checked_locator_identity();

-- Class changes may not connect synthetic records to real candidates after insertion.
CREATE FUNCTION c01_lock_data_class_boundary() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF (OLD.data_class = 'synthetic') IS DISTINCT FROM (NEW.data_class = 'synthetic') THEN
    IF TG_TABLE_NAME = 'agents' THEN
      IF EXISTS (SELECT 1 FROM c01_source_contributors WHERE agent_id=OLD.id OR reviewer_agent_id=OLD.id)
         OR EXISTS (SELECT 1 FROM c01_agent_relations WHERE actor_agent_id=OLD.id OR target_agent_id=OLD.id OR reviewer_agent_id=OLD.id) THEN
        RAISE EXCEPTION 'C-01 graph class boundary is immutable while referenced' USING ERRCODE='55000';
      END IF;
    ELSE
      IF EXISTS (SELECT 1 FROM c01_source_contributors WHERE source_id=OLD.id)
         OR EXISTS (SELECT 1 FROM source_locators l JOIN c01_agent_relations r ON r.source_locator_id=l.id WHERE l.source_id=OLD.id) THEN
        RAISE EXCEPTION 'C-01 graph class boundary is immutable while referenced' USING ERRCODE='55000';
      END IF;
    END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER c01_agent_class_lock BEFORE UPDATE ON agents FOR EACH ROW EXECUTE FUNCTION c01_lock_data_class_boundary();
CREATE TRIGGER c01_source_class_lock BEFORE UPDATE ON sources FOR EACH ROW EXECUTE FUNCTION c01_lock_data_class_boundary();

-- Evaluate the live locator: a later dispute never leaves a confirmed-looking edge.
CREATE VIEW c01_agent_relations_effective AS
SELECT r.*, CASE WHEN r.assertion_status = 'source_checked' AND l.verification_status IS DISTINCT FROM 'checked'
  THEN 'recorded' ELSE r.assertion_status END AS effective_status
FROM c01_agent_relations r LEFT JOIN source_locators l ON l.id = r.source_locator_id;
CREATE VIEW c01_source_contributors_effective AS
SELECT c.*, CASE WHEN c.assertion_status = 'source_checked' AND l.verification_status IS DISTINCT FROM 'checked'
  THEN 'recorded' ELSE c.assertion_status END AS effective_status
FROM c01_source_contributors c LEFT JOIN source_locators l ON l.id = c.source_locator_id;
CREATE INDEX c01_agent_relations_actor_idx ON c01_agent_relations(actor_agent_id, relation_kind);
CREATE INDEX c01_agent_relations_target_idx ON c01_agent_relations(target_agent_id, relation_kind);
CREATE INDEX c01_source_contributors_agent_idx ON c01_source_contributors(agent_id, contributor_role);
COMMIT;
