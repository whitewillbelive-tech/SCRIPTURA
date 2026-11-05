\set ON_ERROR_STOP on
-- Run only after both migrations in an empty, dedicated test database.
BEGIN;
CREATE FUNCTION pg_temp.expect_error(sql_text text, expected_state text) RETURNS void LANGUAGE plpgsql AS $$
DECLARE actual_state text;
BEGIN
  BEGIN
    EXECUTE sql_text;
  EXCEPTION WHEN OTHERS THEN
    GET STACKED DIAGNOSTICS actual_state = RETURNED_SQLSTATE;
    IF actual_state <> expected_state THEN RAISE EXCEPTION 'expected %, got % for %', expected_state, actual_state, sql_text; END IF;
    RETURN;
  END;
  RAISE EXCEPTION 'expected % but command succeeded: %', expected_state, sql_text;
END $$;
INSERT INTO corpora(id,name,corpus_kind) VALUES ('c','synthetic','bible'),('c2','other','other');
INSERT INTO works(id,corpus_id,title) VALUES ('w','c','synthetic');
INSERT INTO reference_schemes(id,corpus_id,scheme_name) VALUES ('s','c','demo');
INSERT INTO passages(id,corpus_id,work_id,scheme_id,external_ref,granularity) VALUES
 ('p1','c','w','s','1:1','verse'),('p2','c','w','s','1:2','verse');
INSERT INTO claims(id) VALUES ('cl1'),('cl2');
INSERT INTO claim_versions(id,claim_id,revision_no,statement,extraction_method,revision_reason) VALUES
 ('v1','cl1',1,'synthetic','human','test'),('v2','cl2',1,'synthetic','human','test');
INSERT INTO claim_passages(id,claim_version_id,passage_id,link_kind) VALUES
 ('l1','v1','p1','discusses'),('l2','v1','p2','discusses'),('l3','v2','p1','discusses');
DO $$ BEGIN
 IF (SELECT count(*) FROM claim_passages WHERE claim_version_id='v1') <> 2 OR
    (SELECT count(*) FROM claim_passages WHERE passage_id='p1') <> 2
 THEN RAISE EXCEPTION 'many-to-many mapping failed'; END IF;
END $$;
\echo PASS: many-to-many mapping
\echo TEST: cross-corpus work foreign key
SELECT pg_temp.expect_error($q$INSERT INTO passages VALUES ('bad','c2','w','s','x','verse','{}','pending')$q$, '23503');
\echo TEST: missing passage foreign key
SELECT pg_temp.expect_error($q$INSERT INTO claim_passages VALUES ('bad','v1','missing','discusses')$q$, '23503');
\echo TEST: duplicate passage address
SELECT pg_temp.expect_error($q$INSERT INTO passages(id,corpus_id,work_id,scheme_id,external_ref,granularity) VALUES ('bad','c','w','s','1:1','verse')$q$, '23505');
\echo TEST: duplicate claim-passage link
SELECT pg_temp.expect_error($q$INSERT INTO claim_passages VALUES ('dup','v1','p1','discusses')$q$, '23505');
\echo TEST: positive revision check
SELECT pg_temp.expect_error($q$INSERT INTO claim_versions(id,claim_id,revision_no,statement,extraction_method,revision_reason) VALUES ('bad','cl1',0,'test','human','test')$q$, '23514');
\echo TEST: unknown-license full-text check
SELECT pg_temp.expect_error($q$INSERT INTO sources(id,title,source_kind,storage_policy,license_status) VALUES ('bad','unknown','book','full_text_allowed','unknown')$q$, '23514');
\echo TEST: evidence target required
SELECT pg_temp.expect_error($q$INSERT INTO claim_evidence(id,claim_version_id,evidence_role,explanation) VALUES ('bad','v1','supports','test')$q$, '23514');
INSERT INTO agents(id,display_name,agent_kind) VALUES ('a','synthetic','person');
INSERT INTO review_events(id,target_entity_type,target_entity_id,reviewer_agent_id,decision,rationale) VALUES ('r','claim','cl1','a','approve_source','test');
INSERT INTO provenance_events(id,event_type,target_entity_type,target_entity_id,actor_agent_id) VALUES ('e','extract','claim','cl1','a');
\echo TEST: review UPDATE rejected
SELECT pg_temp.expect_error($q$UPDATE review_events SET rationale='changed' WHERE id='r'$q$, '55000');
\echo TEST: review DELETE rejected
SELECT pg_temp.expect_error($q$DELETE FROM review_events WHERE id='r'$q$, '55000');
\echo TEST: review TRUNCATE rejected
SELECT pg_temp.expect_error($q$TRUNCATE review_events$q$, '55000');
\echo TEST: provenance UPDATE rejected
SELECT pg_temp.expect_error($q$UPDATE provenance_events SET event_type='correct' WHERE id='e'$q$, '55000');
\echo TEST: provenance DELETE rejected
SELECT pg_temp.expect_error($q$DELETE FROM provenance_events WHERE id='e'$q$, '55000');
\echo TEST: provenance TRUNCATE rejected
SELECT pg_temp.expect_error($q$TRUNCATE provenance_events$q$, '55000');
\echo 'PASS: 14 PostgreSQL schema assertions (1 mapping, 7 constraints, 6 audit immutability)'
ROLLBACK;
