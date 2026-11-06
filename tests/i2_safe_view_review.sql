\set ON_ERROR_STOP on
BEGIN;
CREATE ROLE i2_review_reader NOLOGIN;
GRANT USAGE ON SCHEMA public TO i2_review_reader;
GRANT SELECT ON authority_safe_readings TO i2_review_reader;
GRANT EXECUTE ON FUNCTION authority_safe_rows() TO i2_review_reader;
INSERT INTO claims(id) VALUES ('i2-review-candidate'),('i2-review-synthetic');
INSERT INTO claim_versions(id,claim_id,revision_no,statement,extraction_method,revision_reason,data_class) VALUES ('i2-review-cv-c','i2-review-candidate',1,'fictional sentinel','human','fictional','scholarly_candidate'),('i2-review-cv-s','i2-review-synthetic',1,'fictional safe','human','fictional','synthetic');
INSERT INTO sources(id,title,source_kind,data_class) VALUES ('i2-review-src','Fictional metadata','book','scholarly_candidate');
INSERT INTO source_locators(id,source_id,locator_type,locator_value) VALUES ('i2-review-loc','i2-review-src','section','FICTIONAL_LOCATOR_SENTINEL');
INSERT INTO authority_attestations(id,claim_version_id,authority_kind,statement,representativity,uncertainty,data_class,source_locator_id) VALUES ('i2-review-a-c','i2-review-cv-c','plural_or_unresolved','FICTIONAL_RAW_SENTINEL','FICTIONAL_REP_SENTINEL','FICTIONAL_UNCERTAINTY_SENTINEL','scholarly_candidate','i2-review-loc'),('i2-review-a-s','i2-review-cv-s','plural_or_unresolved','FICTIONAL_SAFE_TEXT','Fictional scope','Fictional uncertainty','synthetic',NULL);
SET LOCAL ROLE i2_review_reader;
DO $$ BEGIN
 IF EXISTS (SELECT 1 FROM authority_safe_readings WHERE id='i2-review-a-c' AND (statement LIKE '%SENTINEL%' OR representativity IS NOT NULL OR uncertainty IS NOT NULL OR locator_value IS NOT NULL)) THEN RAISE EXCEPTION 'candidate masking failed'; END IF;
 IF NOT EXISTS (SELECT 1 FROM authority_safe_readings WHERE id='i2-review-a-s' AND statement='FICTIONAL_SAFE_TEXT') THEN RAISE EXCEPTION 'synthetic text absent'; END IF;
 BEGIN PERFORM statement FROM authority_attestations LIMIT 1; RAISE EXCEPTION 'raw table access allowed'; EXCEPTION WHEN insufficient_privilege THEN NULL; END;
 BEGIN PERFORM statement FROM authority_readings LIMIT 1; RAISE EXCEPTION 'raw view access allowed'; EXCEPTION WHEN insufficient_privilege THEN NULL; END;
 BEGIN PERFORM statement FROM claim_versions LIMIT 1; RAISE EXCEPTION 'legacy claim access allowed'; EXCEPTION WHEN insufficient_privilege THEN NULL; END;
 BEGIN INSERT INTO authority_attestations(id) VALUES ('x'); RAISE EXCEPTION 'write allowed'; EXCEPTION WHEN insufficient_privilege THEN NULL; END;
 RAISE NOTICE 'PASS: safe masking, synthetic visible, raw table/view and legacy table denied, write denied';
END $$;
ROLLBACK;
