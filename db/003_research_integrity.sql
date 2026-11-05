-- S-1B.1 additive integrity checks. Run only in a dedicated SCRIPTURA DB.
BEGIN;
ALTER TABLE sources ADD COLUMN data_class TEXT NOT NULL DEFAULT 'unclassified'
  CHECK (data_class IN ('synthetic','unclassified','scholarly_candidate','source_verified','scholarly_reviewed'));
ALTER TABLE claim_versions ADD COLUMN data_class TEXT NOT NULL DEFAULT 'unclassified'
  CHECK (data_class IN ('synthetic','unclassified','scholarly_candidate','source_verified','scholarly_reviewed'));

ALTER TABLE corpora ADD COLUMN data_class TEXT NOT NULL DEFAULT 'unclassified' CHECK (data_class IN ('synthetic','unclassified','scholarly_candidate','source_verified','scholarly_reviewed'));
ALTER TABLE works ADD COLUMN data_class TEXT NOT NULL DEFAULT 'unclassified' CHECK (data_class IN ('synthetic','unclassified','scholarly_candidate','source_verified','scholarly_reviewed'));
ALTER TABLE reference_schemes ADD COLUMN data_class TEXT NOT NULL DEFAULT 'unclassified' CHECK (data_class IN ('synthetic','unclassified','scholarly_candidate','source_verified','scholarly_reviewed'));
ALTER TABLE passages ADD COLUMN data_class TEXT NOT NULL DEFAULT 'unclassified' CHECK (data_class IN ('synthetic','unclassified','scholarly_candidate','source_verified','scholarly_reviewed'));
ALTER TABLE traditions ADD COLUMN data_class TEXT NOT NULL DEFAULT 'unclassified' CHECK (data_class IN ('synthetic','unclassified','scholarly_candidate','source_verified','scholarly_reviewed'));
ALTER TABLE agents ADD COLUMN data_class TEXT NOT NULL DEFAULT 'unclassified' CHECK (data_class IN ('synthetic','unclassified','scholarly_candidate','source_verified','scholarly_reviewed'));

-- A verified relation is not confirmed unless its exact source location was checked.
CREATE FUNCTION scriptura_checked_relation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.review_status = 'verified' AND NOT EXISTS (
    SELECT 1 FROM source_locators l WHERE l.id = NEW.source_locator_id
      AND l.verification_status = 'checked' AND l.verified_at IS NOT NULL AND length(btrim(l.locator_value)) > 0
  ) THEN RAISE EXCEPTION 'verified relation requires a checked, dated source locator' USING ERRCODE='23514'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER claim_relation_check BEFORE INSERT OR UPDATE ON claim_relations FOR EACH ROW EXECUTE FUNCTION scriptura_checked_relation();
CREATE TRIGGER passage_relation_check BEFORE INSERT OR UPDATE ON passage_relations FOR EACH ROW EXECUTE FUNCTION scriptura_checked_relation();
CREATE TRIGGER passage_alignment_check BEFORE INSERT OR UPDATE ON passage_alignments FOR EACH ROW EXECUTE FUNCTION scriptura_checked_relation();
CREATE TRIGGER claim_evidence_check BEFORE INSERT OR UPDATE ON claim_evidence FOR EACH ROW EXECUTE FUNCTION scriptura_checked_relation();

-- Do not use a person's opinion as official doctrine; attribution sources must be checked.
CREATE FUNCTION scriptura_attribution_integrity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.attribution_kind = 'official_doctrine' AND EXISTS (SELECT 1 FROM agents WHERE id=NEW.agent_id AND agent_kind='person') THEN
    RAISE EXCEPTION 'official doctrine requires an institution or collective' USING ERRCODE='23514';
  END IF;
  IF NEW.attribution_status = 'verified' AND NOT EXISTS (SELECT 1 FROM source_locators l WHERE l.id=NEW.source_locator_id AND l.verification_status='checked' AND l.verified_at IS NOT NULL AND length(btrim(l.locator_value)) > 0) THEN
    RAISE EXCEPTION 'verified attribution requires checked, dated source' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER attribution_check BEFORE INSERT OR UPDATE ON claim_attributions FOR EACH ROW EXECUTE FUNCTION scriptura_attribution_integrity();

CREATE FUNCTION scriptura_claim_integrity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.review_status IN ('source_verified','scholarly_reviewed') THEN
    IF NEW.data_class <> NEW.review_status THEN RAISE EXCEPTION 'verified claims must match their review status' USING ERRCODE='23514'; END IF;
    IF NOT EXISTS (
      SELECT 1 FROM claim_attributions a JOIN source_locators l ON l.id=a.source_locator_id JOIN sources s ON s.id=l.source_id JOIN agents ag ON ag.id=a.agent_id
      WHERE ag.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed') AND a.claim_version_id=NEW.id AND a.attribution_status='verified' AND l.verification_status='checked' AND l.verified_at IS NOT NULL AND length(btrim(l.locator_value)) > 0 AND s.data_class IN ('source_verified','scholarly_reviewed')
    ) OR NOT EXISTS (
      SELECT 1 FROM claim_evidence e JOIN source_locators l ON l.id=e.source_locator_id JOIN sources s ON s.id=l.source_id
      WHERE (e.passage_id IS NULL OR EXISTS (SELECT 1 FROM passages ep WHERE ep.id=e.passage_id AND ep.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed'))) AND (e.related_claim_version_id IS NULL OR EXISTS (SELECT 1 FROM claim_versions ec WHERE ec.id=e.related_claim_version_id AND ec.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed'))) AND e.claim_version_id=NEW.id AND e.review_status='verified' AND l.verification_status='checked' AND l.verified_at IS NOT NULL AND length(btrim(l.locator_value)) > 0 AND s.data_class IN ('source_verified','scholarly_reviewed')
    ) THEN RAISE EXCEPTION 'verified claims require verified attribution and evidence at checked scholarly sources' USING ERRCODE='23514'; END IF;
  ELSIF NEW.data_class IN ('source_verified','scholarly_reviewed') THEN
    RAISE EXCEPTION 'verified classification requires a matching review state' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER claim_integrity_check BEFORE INSERT OR UPDATE ON claim_versions FOR EACH ROW EXECUTE FUNCTION scriptura_claim_integrity();

-- Freeze supporting records while claim is verified; first mark the claim disputed to revise.
CREATE FUNCTION scriptura_lock_verified_support() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE cid text;
BEGIN
  cid := OLD.claim_version_id;
  IF EXISTS (SELECT 1 FROM claim_versions WHERE id=cid AND review_status IN ('source_verified','scholarly_reviewed')) THEN
    RAISE EXCEPTION 'mark verified claim disputed before changing support' USING ERRCODE='55000';
  END IF;
  IF TG_OP='DELETE' THEN RETURN OLD; END IF;
  IF NEW.claim_version_id <> OLD.claim_version_id AND EXISTS (SELECT 1 FROM claim_versions WHERE id=NEW.claim_version_id AND review_status IN ('source_verified','scholarly_reviewed')) THEN
    RAISE EXCEPTION 'cannot reassign support to verified claim' USING ERRCODE='55000';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER attribution_lock BEFORE UPDATE OR DELETE ON claim_attributions FOR EACH ROW EXECUTE FUNCTION scriptura_lock_verified_support();
CREATE TRIGGER evidence_lock BEFORE UPDATE OR DELETE ON claim_evidence FOR EACH ROW EXECUTE FUNCTION scriptura_lock_verified_support();

CREATE FUNCTION scriptura_lock_checked_locator() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF (NEW.source_id,NEW.locator_type,NEW.locator_value,NEW.direct_url,NEW.verification_status,NEW.verified_at,NEW.quote_sha256) IS DISTINCT FROM (OLD.source_id,OLD.locator_type,OLD.locator_value,OLD.direct_url,OLD.verification_status,OLD.verified_at,OLD.quote_sha256) AND (
    EXISTS(SELECT 1 FROM claim_relations WHERE source_locator_id=OLD.id AND review_status='verified') OR
    EXISTS(SELECT 1 FROM passage_relations WHERE source_locator_id=OLD.id AND review_status='verified') OR
    EXISTS(SELECT 1 FROM passage_alignments WHERE source_locator_id=OLD.id AND review_status='verified') OR
    EXISTS(SELECT 1 FROM claim_evidence WHERE source_locator_id=OLD.id AND review_status='verified') OR
    EXISTS(SELECT 1 FROM claim_attributions WHERE source_locator_id=OLD.id AND attribution_status='verified')
  ) THEN RAISE EXCEPTION 'retract verified dependent records before changing checked locator' USING ERRCODE='55000'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER locator_lock BEFORE UPDATE ON source_locators FOR EACH ROW EXECUTE FUNCTION scriptura_lock_checked_locator();

CREATE FUNCTION scriptura_lock_verified_source() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF ((OLD.data_class IN ('source_verified','scholarly_reviewed') AND NEW.data_class NOT IN ('source_verified','scholarly_reviewed')) OR (NEW.title,NEW.creator,NEW.source_kind,NEW.source_url,NEW.doi,NEW.edition_or_version) IS DISTINCT FROM (OLD.title,OLD.creator,OLD.source_kind,OLD.source_url,OLD.doi,OLD.edition_or_version)) AND EXISTS (
    SELECT 1 FROM source_locators l WHERE l.source_id=OLD.id AND (
      EXISTS(SELECT 1 FROM claim_relations r WHERE r.source_locator_id=l.id AND r.review_status='verified') OR
      EXISTS(SELECT 1 FROM passage_relations r WHERE r.source_locator_id=l.id AND r.review_status='verified') OR
      EXISTS(SELECT 1 FROM passage_alignments r WHERE r.source_locator_id=l.id AND r.review_status='verified') OR
      EXISTS(SELECT 1 FROM claim_attributions a JOIN claim_versions c ON c.id=a.claim_version_id WHERE a.source_locator_id=l.id AND a.attribution_status='verified' AND c.review_status IN ('source_verified','scholarly_reviewed')) OR
      EXISTS(SELECT 1 FROM claim_evidence e JOIN claim_versions c ON c.id=e.claim_version_id WHERE e.source_locator_id=l.id AND e.review_status='verified' AND c.review_status IN ('source_verified','scholarly_reviewed'))
    )
  ) THEN RAISE EXCEPTION 'mark dependent claims disputed before downgrading source' USING ERRCODE='55000'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER source_class_lock BEFORE UPDATE ON sources FOR EACH ROW EXECUTE FUNCTION scriptura_lock_verified_source();
CREATE FUNCTION scriptura_lock_official_agent() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF (NEW.display_name,NEW.agent_kind,NEW.name_disambiguator,NEW.data_class) IS DISTINCT FROM (OLD.display_name,OLD.agent_kind,OLD.name_disambiguator,OLD.data_class) AND EXISTS (SELECT 1 FROM claim_attributions a JOIN claim_versions c ON c.id=a.claim_version_id WHERE a.agent_id=OLD.id AND a.attribution_status='verified' AND c.review_status IN ('source_verified','scholarly_reviewed')) THEN RAISE EXCEPTION 'mark dependent claims disputed before changing verified attribution identity' USING ERRCODE='55000'; END IF;
  IF NEW.agent_kind='person' AND EXISTS(SELECT 1 FROM claim_attributions WHERE agent_id=OLD.id AND attribution_kind='official_doctrine') THEN
    RAISE EXCEPTION 'person cannot carry official doctrine attribution' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER official_agent_lock BEFORE UPDATE ON agents FOR EACH ROW EXECUTE FUNCTION scriptura_lock_official_agent();

-- One transaction writes the decision, state change, and provenance; no client-side partial approval.
CREATE FUNCTION scriptura_review_claim(p_version_id text, p_reviewer_id text, p_decision text, p_rationale text, p_review_id text, p_provenance_id text)
RETURNS claim_versions LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE result claim_versions;
BEGIN
  IF p_decision NOT IN ('approve_source','approve_scholarly','mark_disputed','reject','request_changes') OR length(btrim(coalesce(p_rationale,'')))=0 THEN
    RAISE EXCEPTION 'invalid review decision or rationale' USING ERRCODE='22023';
  END IF;
  SELECT * INTO result FROM claim_versions WHERE id=p_version_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'claim not found' USING ERRCODE='P0002'; END IF;
  IF result.data_class='synthetic' THEN RAISE EXCEPTION 'synthetic data cannot be approved as scholarly evidence' USING ERRCODE='23514'; END IF;
  IF p_decision='approve_scholarly' AND result.review_status <> 'source_verified' THEN RAISE EXCEPTION 'source verification must precede scholarly review' USING ERRCODE='23514'; END IF;
  INSERT INTO review_events(id,target_entity_type,target_entity_id,reviewer_agent_id,decision,rationale)
    VALUES(p_review_id,'claim_version',p_version_id,p_reviewer_id,p_decision,p_rationale);
  IF p_decision='approve_source' THEN
    UPDATE claim_versions SET review_status='source_verified', data_class='source_verified' WHERE id=p_version_id RETURNING * INTO result;
  ELSIF p_decision='approve_scholarly' THEN
    UPDATE claim_versions SET review_status='scholarly_reviewed', data_class='scholarly_reviewed' WHERE id=p_version_id RETURNING * INTO result;
  ELSIF p_decision IN ('mark_disputed','reject','request_changes') THEN
    UPDATE claim_versions SET review_status='disputed', data_class='scholarly_candidate' WHERE id=p_version_id RETURNING * INTO result;
  END IF;
  INSERT INTO provenance_events(id,event_type,target_entity_type,target_entity_id,actor_agent_id,metadata)
    VALUES(p_provenance_id,'review','claim_version',p_version_id,p_reviewer_id,jsonb_build_object('decision',p_decision,'review_event_id',p_review_id));
  RETURN result;
END $$;
DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_namespace n, LATERAL aclexplode(COALESCE(n.nspacl,acldefault('n', n.nspowner))) a WHERE n.nspname=current_schema() AND a.grantee=0 AND a.privilege_type='CREATE') THEN RAISE EXCEPTION 'schema must not allow CREATE to PUBLIC'; END IF; EXECUTE format('ALTER FUNCTION %I.scriptura_review_claim(text,text,text,text,text,text) SET search_path = pg_catalog, %I, pg_temp', current_schema(), current_schema()); END $$;
REVOKE ALL ON FUNCTION scriptura_review_claim(text,text,text,text,text,text) FROM PUBLIC;
COMMIT;
