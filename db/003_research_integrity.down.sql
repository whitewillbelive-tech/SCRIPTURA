-- Refuse to discard explicit data classification. Dedicated DB only.
BEGIN;
LOCK TABLE corpora, works, reference_schemes, passages, traditions, agents, sources, claim_versions IN ACCESS EXCLUSIVE MODE;
DO $$ DECLARE t text; has_rows boolean; BEGIN
  FOREACH t IN ARRAY ARRAY['corpora','works','reference_schemes','passages','traditions','agents','sources','claim_versions'] LOOP
    EXECUTE format('SELECT EXISTS (SELECT 1 FROM %I WHERE data_class <> ''unclassified'')', t) INTO has_rows;
    IF has_rows THEN RAISE EXCEPTION 'rollback refused: % contains classified data', t; END IF;
  END LOOP;
END $$;
DROP FUNCTION scriptura_review_claim(text,text,text,text,text,text);
DROP TRIGGER source_class_lock ON sources;
DROP FUNCTION scriptura_lock_verified_source();
DROP TRIGGER official_agent_lock ON agents;
DROP FUNCTION scriptura_lock_official_agent();
DROP TRIGGER locator_lock ON source_locators;
DROP FUNCTION scriptura_lock_checked_locator();
DROP TRIGGER attribution_lock ON claim_attributions;
DROP TRIGGER evidence_lock ON claim_evidence;
DROP FUNCTION scriptura_lock_verified_support();
DROP TRIGGER claim_integrity_check ON claim_versions;
DROP FUNCTION scriptura_claim_integrity();
DROP TRIGGER attribution_check ON claim_attributions;
DROP FUNCTION scriptura_attribution_integrity();
DROP TRIGGER claim_relation_check ON claim_relations;
DROP TRIGGER passage_relation_check ON passage_relations;
DROP TRIGGER passage_alignment_check ON passage_alignments;
DROP TRIGGER claim_evidence_check ON claim_evidence;
DROP FUNCTION scriptura_checked_relation();
ALTER TABLE claim_versions DROP COLUMN data_class;
ALTER TABLE sources DROP COLUMN data_class;
ALTER TABLE agents DROP COLUMN data_class;
ALTER TABLE traditions DROP COLUMN data_class;
ALTER TABLE passages DROP COLUMN data_class;
ALTER TABLE reference_schemes DROP COLUMN data_class;
ALTER TABLE works DROP COLUMN data_class;
ALTER TABLE corpora DROP COLUMN data_class;
COMMIT;
