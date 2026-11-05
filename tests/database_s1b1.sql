\set ON_ERROR_STOP on
-- Synthetic statements for a transaction in an isolated test DB only; no scholarly data.
BEGIN;
CREATE FUNCTION pg_temp.expect_error(sql_text text, expected_state text) RETURNS void LANGUAGE plpgsql AS $$
DECLARE actual_state text;
BEGIN
  BEGIN EXECUTE sql_text;
  EXCEPTION WHEN OTHERS THEN
    GET STACKED DIAGNOSTICS actual_state = RETURNED_SQLSTATE;
    IF actual_state <> expected_state THEN RAISE EXCEPTION 'expected %, got % for %',expected_state,actual_state,sql_text; END IF;
    RETURN;
  END;
  RAISE EXCEPTION 'expected % but command succeeded: %',expected_state,sql_text;
END $$;
INSERT INTO agents(id,display_name,agent_kind,data_class) VALUES ('rv','test reviewer','person','scholarly_candidate'),('org','test organization','institution','scholarly_candidate'),('fake','synthetic actor','person','synthetic');
INSERT INTO sources(id,title,source_kind,data_class) VALUES ('src','test source, no original text','book','source_verified');
INSERT INTO source_locators(id,source_id,locator_type,locator_value,verification_status,verified_at) VALUES
 ('loc','src','page','test-locator','checked',CURRENT_TIMESTAMP),('unchecked','src','page','test-unchecked','unverified',NULL),('empty','src','page',' ','checked',CURRENT_TIMESTAMP);
INSERT INTO claims(id) VALUES ('claim'),('other'),('bad'),('synth'),('mixed');
INSERT INTO claim_versions(id,claim_id,revision_no,statement,extraction_method,revision_reason,data_class) VALUES
 ('ver','claim',1,'synthetic test statement','human','test','scholarly_candidate'),
 ('v2','other',1,'synthetic test statement 2','human','test','scholarly_candidate'),
 ('vbad','bad',1,'test no support','human','test','scholarly_candidate'),
 ('vsynthetic','synth',1,'synthetic','human','test','synthetic'),
 ('vmixed','mixed',1,'test mixed provenance','human','test','scholarly_candidate');
SELECT pg_temp.expect_error($q$SELECT scriptura_review_claim('vbad','rv','approve_source','test','r_bad','p_bad')$q$,'23514');
DO $$ BEGIN IF EXISTS (SELECT 1 FROM review_events WHERE id='r_bad') THEN RAISE EXCEPTION 'failed approval left audit row'; END IF; END $$;
SELECT pg_temp.expect_error($q$SELECT scriptura_review_claim('vsynthetic','rv','approve_source','test','r_syn','p_syn')$q$,'23514');

INSERT INTO corpora(id,name,corpus_kind,data_class) VALUES ('syn-corpus','synthetic','bible','synthetic');
INSERT INTO works(id,corpus_id,title,data_class) VALUES ('syn-work','syn-corpus','synthetic','synthetic');
INSERT INTO reference_schemes(id,corpus_id,scheme_name,data_class) VALUES ('syn-scheme','syn-corpus','synthetic','synthetic');
INSERT INTO passages(id,corpus_id,work_id,scheme_id,external_ref,granularity,data_class) VALUES ('syn-passage','syn-corpus','syn-work','syn-scheme','1:1','verse','synthetic');
INSERT INTO claim_attributions(id,claim_version_id,agent_id,attribution_kind,source_locator_id,attribution_status) VALUES ('bad-attr','vbad','org','institutional_statement','loc','verified');
INSERT INTO claim_evidence(id,claim_version_id,source_locator_id,passage_id,evidence_role,explanation,review_status) VALUES ('bad-ev','vbad','loc','syn-passage','supports','test','verified');
SELECT pg_temp.expect_error($q$SELECT scriptura_review_claim('vbad','rv','approve_source','test','r_mix_passage','p_mix_passage')$q$,'23514');
UPDATE claim_evidence SET passage_id=NULL,related_claim_version_id='vsynthetic' WHERE id='bad-ev';
SELECT pg_temp.expect_error($q$SELECT scriptura_review_claim('vbad','rv','approve_source','test','r_mix_claim','p_mix_claim')$q$,'23514');

SELECT pg_temp.expect_error($q$INSERT INTO claim_attributions(id,claim_version_id,agent_id,attribution_kind) VALUES ('personal','ver','rv','official_doctrine')$q$,'23514');
SELECT pg_temp.expect_error($q$INSERT INTO claim_relations(id,from_version_id,to_version_id,relation_type,source_locator_id,review_status,rationale) VALUES ('relbad','ver','v2','rebuts','unchecked','verified','test')$q$,'23514');
SELECT pg_temp.expect_error($q$INSERT INTO claim_relations(id,from_version_id,to_version_id,relation_type,source_locator_id,review_status,rationale) VALUES ('relempty','ver','v2','rebuts','empty','verified','test')$q$,'23514');
INSERT INTO claim_attributions(id,claim_version_id,agent_id,attribution_kind,source_locator_id,attribution_status) VALUES ('mixedattr','vmixed','fake','individual_opinion','loc','verified');
INSERT INTO claim_evidence(id,claim_version_id,source_locator_id,evidence_role,explanation,review_status) VALUES ('mixedev','vmixed','loc','supports','test','verified');
SELECT pg_temp.expect_error($q$SELECT scriptura_review_claim('vmixed','rv','approve_source','test','r_mix','p_mix')$q$,'23514');
INSERT INTO claim_attributions(id,claim_version_id,agent_id,attribution_kind,source_locator_id,attribution_status) VALUES ('attr','ver','org','official_doctrine','loc','verified');
INSERT INTO claim_evidence(id,claim_version_id,source_locator_id,evidence_role,explanation,review_status) VALUES ('ev','ver','loc','supports','test','verified');
SELECT (scriptura_review_claim('ver','rv','approve_source','test','r1','p1')).id;
DO $$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM claim_versions WHERE id='ver' AND review_status='source_verified' AND data_class='source_verified') THEN RAISE EXCEPTION 'source approval failed'; END IF;
 IF NOT EXISTS (SELECT 1 FROM review_events WHERE id='r1') OR NOT EXISTS (SELECT 1 FROM provenance_events WHERE id='p1') THEN RAISE EXCEPTION 'audit missing'; END IF;
END $$;
SELECT pg_temp.expect_error($q$UPDATE source_locators SET locator_value='other' WHERE id='loc'$q$,'55000');
SELECT pg_temp.expect_error($q$UPDATE sources SET data_class='scholarly_candidate' WHERE id='src'$q$,'55000');
SELECT pg_temp.expect_error($q$UPDATE sources SET title='different source' WHERE id='src'$q$,'55000');
SELECT pg_temp.expect_error($q$UPDATE agents SET display_name='different institution' WHERE id='org'$q$,'55000');
SELECT pg_temp.expect_error($q$UPDATE agents SET data_class='synthetic' WHERE id='org'$q$,'55000');
SELECT pg_temp.expect_error($q$DELETE FROM claim_evidence WHERE id='ev'$q$,'55000');
SELECT pg_temp.expect_error($q$UPDATE review_events SET rationale='altered' WHERE id='r1'$q$,'55000');
SELECT pg_temp.expect_error($q$DELETE FROM provenance_events WHERE id='p1'$q$,'55000');
SELECT (scriptura_review_claim('ver','rv','approve_scholarly','test','r2','p2')).id;
DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM claim_versions WHERE id='ver' AND review_status='scholarly_reviewed' AND data_class='scholarly_reviewed') THEN RAISE EXCEPTION 'scholarly review failed'; END IF; END $$;
SELECT (scriptura_review_claim('ver','rv','mark_disputed','test','r3','p3')).id;
INSERT INTO claim_relations(id,from_version_id,to_version_id,relation_type,source_locator_id,review_status,rationale) VALUES ('verified-rel','ver','v2','rebuts','loc','verified','test');
SELECT pg_temp.expect_error($q$UPDATE sources SET title='changed source behind verified relation' WHERE id='src'$q$,'55000');
DO $$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM claim_versions WHERE id='ver' AND review_status='disputed' AND data_class='scholarly_candidate') THEN RAISE EXCEPTION 'dispute failed'; END IF;
 IF EXISTS (SELECT 1 FROM pg_proc p, LATERAL aclexplode(p.proacl) a WHERE p.oid='scriptura_review_claim(text,text,text,text,text,text)'::regprocedure AND a.grantee=0 AND a.privilege_type='EXECUTE') THEN RAISE EXCEPTION 'PUBLIC may execute admin review'; END IF;
END $$;
-- A conflicting provenance ID must roll back both claim state and its review event.
INSERT INTO claim_attributions(id,claim_version_id,agent_id,attribution_kind,source_locator_id,attribution_status) VALUES ('attr2','v2','org','institutional_statement','loc','verified');
INSERT INTO claim_evidence(id,claim_version_id,source_locator_id,evidence_role,explanation,review_status) VALUES ('ev2','v2','loc','supports','test','verified');
SELECT pg_temp.expect_error($q$SELECT scriptura_review_claim('v2','rv','approve_source','test','r_collision','p1')$q$,'23505');
DO $$ BEGIN IF EXISTS (SELECT 1 FROM review_events WHERE id='r_collision') OR EXISTS (SELECT 1 FROM claim_versions WHERE id='v2' AND review_status<>'extracted') THEN RAISE EXCEPTION 'partial approval survived'; END IF; END $$;
-- Verify restricted review role cannot alter tables or hijack the SECURITY DEFINER with temp relations.
CREATE ROLE scriptura_review_test NOLOGIN;
GRANT USAGE ON SCHEMA public TO scriptura_review_test;
GRANT EXECUTE ON FUNCTION scriptura_review_claim(text,text,text,text,text,text) TO scriptura_review_test;
SET LOCAL ROLE scriptura_review_test;
CREATE TEMP TABLE claim_versions(id text,review_status text,data_class text);
SELECT pg_temp.expect_error($q$INSERT INTO public.claim_versions(id,claim_id,revision_no,statement,extraction_method,revision_reason) VALUES ('attack','claim',2,'x','human','test')$q$,'42501');
SELECT pg_temp.expect_error($q$SELECT public.scriptura_review_claim('nonexistent','rv','approve_source','test','r_fake','p_fake')$q$,'P0002');
SELECT (public.scriptura_review_claim('v2','rv','approve_source','test','r_role','p_role')).id;
RESET ROLE;
DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM public.claim_versions WHERE id='v2' AND review_status='source_verified') OR NOT EXISTS (SELECT 1 FROM review_events WHERE id='r_role') THEN RAISE EXCEPTION 'restricted-role approval failed'; END IF; END $$;
\echo 'PASS: S1B.1 integrity, approval, classification, rights metadata and append-only audit (26 checks: 20 expected errors, 6 assertion blocks)'
ROLLBACK;
