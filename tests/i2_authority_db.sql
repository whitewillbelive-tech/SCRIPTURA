\set ON_ERROR_STOP on
-- All rows in this disposable transaction are wholly synthetic.
BEGIN;
INSERT INTO traditions(id,name,classification_kind,data_class) VALUES ('tr','Synthetic group','denomination','synthetic'),('tr_other','Other fictional group','denomination','synthetic');
INSERT INTO agents(id,display_name,agent_kind,data_class) VALUES ('org','Fictional institution','institution','synthetic'),('org2','Other fiction','institution','synthetic'),('person','Fictional person','person','synthetic'),('reviewer','Fictional reviewer','person','synthetic');
INSERT INTO sources(id,title,creator,source_kind,data_class) VALUES ('src','Fictional official document','Fictional institution','official_document','synthetic'),('other','Fictional outside record','Other fiction','official_document','synthetic'),('personal_src','Fictional personal essay','Fictional person','webpage','synthetic');
INSERT INTO source_locators(id,source_id,locator_type,locator_value,verification_status,verified_at) VALUES ('loc','src','section','Fictional 1','checked',now()),('adopt_loc','src','section','Fictional adoption','checked',now()),('rights_loc','src','section','Fictional rights','checked',now()),('arg_loc','src','section','Fictional argument','checked',now()),('quote_loc','src','section','Fictional quote','checked',now()),('issuer_loc','src','section','Fictional issuer','checked',now()),('historical_loc','src','section','Fictional historical','checked',now()),('other_loc','other','section','Fictional outside','checked',now()),('review_loc','other','section','Fictional 2','checked',now()),('personal_loc','personal_src','section','Fictional personal note','checked',now()),('unknown_loc','src','section','Fictional unchecked','unverified',NULL);
INSERT INTO claims(id) VALUES ('claim'),('personal');
INSERT INTO claim_versions(id,claim_id,revision_no,statement,extraction_method,revision_reason,data_class) VALUES ('ver','claim',1,'Fictional claim','human','fictional','synthetic'),('pver','personal',1,'Fictional personal claim','human','fictional','synthetic');
INSERT INTO claim_attributions(id,claim_version_id,agent_id,attribution_kind,source_locator_id,attribution_status) VALUES ('attr','ver','org','official_doctrine','loc','verified'),('pattr','pver','person','individual_opinion','loc','verified'),('pattr2','pver','person','individual_opinion','personal_loc','verified');
INSERT INTO agent_affiliations(id,agent_id,tradition_id,relation_type,source_locator_id) VALUES ('aff1','person','tr','self_identified','loc'),('aff2','person','tr_other','self_identified','loc');
INSERT INTO authority_documents(id,issuer_agent_id,tradition_id,authority_kind,jurisdiction,published_on,revised_on,valid_from,valid_until,edition_label,language_code,verification_path,source_locator_id,adoption_locator_id,issuer_tradition_evidence_locator_id,adoption_basis,formal_adoption_confirmed,adoption_verified_by,adoption_verified_at,rights_evidence_status,rights_evidence_locator_id,rights_checked_by,rights_checked_at,rights_check_scope,data_class)
VALUES ('doc','org','tr','normative_adopted','Fictional local scope','2000-01-01','2001-01-01','2001-01-01','2030-12-31','Fictional edition','en','direct','loc','adopt_loc','loc','Fictional explicit adoption',true,'reviewer',now(),'reviewed','rights_loc','reviewer',now(),'metadata only','synthetic');
CREATE TEMP TABLE probe (LIKE authority_attestations INCLUDING DEFAULTS);
INSERT INTO probe(id,claim_version_id,tradition_id,subject_agent_id,document_id,authority_kind,position_scope,perspective,quotation_status,authority_status,statement,jurisdiction,valid_from,valid_until,as_of,representativity,proof_directness,uncertainty,source_locator_id,quotation_checked_by,quotation_checked_at,quotation_check_scope,authority_checked_by,authority_checked_at,authority_check_scope,data_class)
VALUES ('original','ver','tr','org','doc','normative_adopted','documented_group_position','community_self','direct_checked','adoption_documented','Synthetic statement','Fictional local scope','2001-01-01','2030-12-31','2020-01-01','Fictional explicit adoption','direct','Fictional; scoped', 'loc','reviewer',now(),'Fictional exact-location check','reviewer',now(),'Fictional scope check','synthetic');
CREATE FUNCTION pg_temp.rejected(patch jsonb) RETURNS void LANGUAGE plpgsql AS $$
DECLARE r authority_attestations; got text;
BEGIN
  SELECT (jsonb_populate_record(NULL::authority_attestations,to_jsonb(p)||patch||'{"id":"negative"}'::jsonb)).* INTO r FROM probe p LIMIT 1;
  BEGIN INSERT INTO authority_attestations SELECT (r).*;
  EXCEPTION WHEN OTHERS THEN GET STACKED DIAGNOSTICS got=RETURNED_SQLSTATE; IF got='23514' THEN RETURN; END IF; RAISE; END;
  RAISE EXCEPTION 'invalid authority record was accepted';
END $$;
INSERT INTO authority_attestations SELECT * FROM probe;
DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM authority_readings WHERE id='original' AND effective_authority_status='adoption_documented' AND effective_independent_review_status='none' AND effective_argument_status='not_assessed') THEN RAISE EXCEPTION 'documented scoped adoption or axis separation failed'; END IF; END $$;
SELECT pg_temp.rejected('{"as_of":null}');
SELECT pg_temp.rejected('{"as_of":"2040-01-01"}');
SELECT pg_temp.rejected('{"tradition_id":"tr_other"}');
SELECT pg_temp.rejected('{"claim_version_id":"pver","subject_agent_id":"person"}');
SELECT pg_temp.rejected('{"jurisdiction":"Other fictional jurisdiction"}');
SELECT pg_temp.rejected('{"valid_until":null}');
SELECT pg_temp.rejected('{"representativity":null}');
SELECT pg_temp.rejected('{"authority_checked_by":null}');
SELECT pg_temp.rejected('{"quotation_checked_by":null}');
SELECT pg_temp.rejected('{"quotation_status":"direct_checked","proof_directness":"secondary"}');
SELECT pg_temp.rejected('{"argument_status":"documented_argument"}');
SELECT pg_temp.rejected('{"independent_review_status":"human_review_documented","independent_review_verified":true,"independent_reviewer_agent_id":"reviewer","independent_review_target_id":"ver","independent_review_locator_id":"review_loc","independent_reviewed_at":"2026-01-01T00:00:00Z","independent_review_method":null}');
SELECT pg_temp.rejected('{"independent_review_status":"human_review_documented","independent_review_verified":false,"independent_reviewer_agent_id":"reviewer","independent_review_target_id":"ver","independent_review_locator_id":"review_loc","independent_reviewed_at":"2026-01-01T00:00:00Z","independent_review_method":"Fictional review"}');
SELECT pg_temp.rejected('{"independent_review_status":"published_critique_documented"}');
SELECT pg_temp.rejected('{"independent_review_status":"published_critique_documented","independent_reviewer_agent_id":"reviewer","independent_review_target_id":"pver","independent_review_locator_id":"review_loc","independent_reviewed_at":"2026-01-01T00:00:00Z","independent_review_method":"Fictional critique"}');
SELECT pg_temp.rejected('{"independent_review_status":"human_review_documented","independent_review_verified":true,"independent_reviewer_agent_id":"org","independent_review_target_id":"ver","independent_review_locator_id":"review_loc","independent_reviewed_at":"2026-01-01T00:00:00Z","independent_review_method":"Fictional review"}');
SELECT pg_temp.rejected('{"authority_kind":"individual_insider_view","authority_status":"individual_only"}');
SELECT pg_temp.rejected('{"authority_status":"issuer_documented"}');
SELECT pg_temp.rejected('{"authority_status":"historical_only"}');
-- Positive documented independent review needs distinct actual reviewer and proof;
-- it is not inferred from scholarly publication or authority status.
INSERT INTO authority_attestations SELECT (jsonb_populate_record(NULL::authority_attestations,to_jsonb(p)||'{"id":"reviewed","independent_review_status":"human_review_documented","independent_review_verified":true,"independent_reviewer_agent_id":"reviewer","independent_review_target_id":"ver","independent_review_locator_id":"review_loc","independent_reviewed_at":"2026-01-01T00:00:00Z","independent_review_method":"Fictional independent review"}'::jsonb)).* FROM probe p;
DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM authority_readings WHERE id='reviewed' AND effective_independent_review_status='human_review_documented' AND effective_argument_status='not_assessed') THEN RAISE EXCEPTION 'explicit review or independence failed'; END IF; END $$;
-- A documented criticism is not an independent human review automatically.
INSERT INTO authority_attestations SELECT (jsonb_populate_record(NULL::authority_attestations,to_jsonb(p)||'{"id":"critique","independent_review_status":"published_critique_documented","independent_review_verified":false,"independent_reviewer_agent_id":"reviewer","independent_review_target_id":"ver","independent_review_locator_id":"review_loc","independent_reviewed_at":"2026-01-01T00:00:00Z","independent_review_method":"Fictional published criticism"}'::jsonb)).* FROM probe p;
DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM authority_readings WHERE id='critique' AND effective_independent_review_status='published_critique_documented') THEN RAISE EXCEPTION 'critique wrongly treated as human review'; END IF; END $$;
UPDATE source_locators SET verification_status='disputed' WHERE id='review_loc';
DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM authority_readings WHERE id='reviewed' AND effective_independent_review_status='pending' AND effective_authority_status='adoption_documented' AND effective_quotation_status='direct_checked') THEN RAISE EXCEPTION 'read-time independent review downgrade failed'; END IF; END $$;
-- Rights missing on document must not authorize a formal position.
INSERT INTO authority_documents SELECT (jsonb_populate_record(NULL::authority_documents,to_jsonb(d)||'{"id":"no_rights","rights_evidence_status":"unknown","rights_evidence_locator_id":null}'::jsonb)).* FROM authority_documents d WHERE id='doc';
SELECT pg_temp.rejected('{"document_id":"no_rights"}');
INSERT INTO authority_documents SELECT (jsonb_populate_record(NULL::authority_documents,to_jsonb(d)||'{"id":"not_adopted","formal_adoption_confirmed":false}'::jsonb)).* FROM authority_documents d WHERE id='doc';
SELECT pg_temp.rejected('{"document_id":"not_adopted"}');
INSERT INTO authority_documents SELECT (jsonb_populate_record(NULL::authority_documents,to_jsonb(d)||'{"id":"old","published_on":"1951-01-01","revised_on":"1951-01-01","valid_from":"1951-01-01","valid_until":"1951-12-31"}'::jsonb)).* FROM authority_documents d WHERE id='doc';
SELECT pg_temp.rejected('{"document_id":"old"}');
-- A person's documented view remains individual despite two affiliations.
INSERT INTO authority_documents SELECT (jsonb_populate_record(NULL::authority_documents,to_jsonb(d)||'{"id":"personal_doc","issuer_agent_id":"person","authority_kind":"individual_insider_view","source_locator_id":"personal_loc"}'::jsonb)).* FROM authority_documents d WHERE id='doc';
INSERT INTO authority_attestations SELECT (jsonb_populate_record(NULL::authority_attestations,to_jsonb(p)||'{"id":"personal_view","claim_version_id":"pver","subject_agent_id":"person","document_id":"personal_doc","authority_kind":"individual_insider_view","position_scope":"documented_individual_view","perspective":"individual","authority_status":"individual_only","source_locator_id":"personal_loc"}'::jsonb)).* FROM probe p;
DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM authority_readings WHERE id='personal_view' AND effective_authority_status='individual_only' AND NOT official_proof_sufficient) THEN RAISE EXCEPTION 'personal affiliation became official'; END IF; END $$;
-- A candidate with a checked quotation but no authority remains unverified.
INSERT INTO authority_attestations SELECT (jsonb_populate_record(NULL::authority_attestations,to_jsonb(p)||'{"id":"quote_only","authority_status":"unknown","source_locator_id":"quote_loc"}'::jsonb)).* FROM probe p;
DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM authority_readings WHERE id='quote_only' AND effective_quotation_status='direct_checked' AND effective_authority_status='unknown' AND effective_independent_review_status='none') THEN RAISE EXCEPTION 'four axes were conflated'; END IF; END $$;
UPDATE source_locators SET verification_status='disputed' WHERE id='quote_loc';
DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM authority_readings WHERE id='quote_only' AND effective_quotation_status='unchecked') THEN RAISE EXCEPTION 'stale quotation not downgraded'; END IF; END $$;
-- Arguments have independent evidence, which may later be retracted.
INSERT INTO authority_attestations SELECT (jsonb_populate_record(NULL::authority_attestations,to_jsonb(p)||'{"id":"argument","argument_status":"documented_argument","argument_locator_id":"arg_loc","argument_checked_by":"reviewer","argument_checked_at":"2026-01-01T00:00:00Z","argument_check_scope":"Synthetic context"}'::jsonb)).* FROM probe p;
UPDATE source_locators SET verification_status='disputed' WHERE id='arg_loc';
DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM authority_readings WHERE id='argument' AND effective_argument_status='not_assessed' AND effective_authority_status='adoption_documented') THEN RAISE EXCEPTION 'stale argument not independently downgraded'; END IF; END $$;
-- Fictional institutional guidance is not adoption and must be linked to the
-- issuer's verified statement; personal or outsider attribution cannot satisfy it.
INSERT INTO authority_documents SELECT (jsonb_populate_record(NULL::authority_documents,to_jsonb(d)||'{"id":"guidance_doc","authority_kind":"official_institutional_guidance","source_locator_id":"issuer_loc"}'::jsonb)).* FROM authority_documents d WHERE id='doc';
INSERT INTO authority_attestations SELECT (jsonb_populate_record(NULL::authority_attestations,to_jsonb(p)||'{"id":"guidance","authority_kind":"official_institutional_guidance","authority_status":"issuer_documented","document_id":"guidance_doc"}'::jsonb)).* FROM probe p;
SELECT pg_temp.rejected('{"authority_kind":"official_institutional_guidance","authority_status":"issuer_documented","document_id":"guidance_doc","claim_version_id":"pver","subject_agent_id":"person"}');
SELECT pg_temp.rejected('{"authority_kind":"official_institutional_guidance","authority_status":"issuer_documented","document_id":"guidance_doc","perspective":"outsider"}');
SELECT pg_temp.rejected('{"authority_kind":"official_institutional_guidance","authority_status":"issuer_documented","document_id":"guidance_doc","valid_until":null}');
SELECT pg_temp.rejected('{"authority_kind":"official_institutional_guidance","authority_status":"issuer_documented","document_id":"guidance_doc","as_of":"2040-01-01"}');
UPDATE source_locators SET verification_status='disputed' WHERE id='issuer_loc';
DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM authority_readings WHERE id='guidance' AND effective_authority_status='unknown') THEN RAISE EXCEPTION 'stale institutional evidence not downgraded'; END IF; END $$;
-- A 1951 document applies only to its bounded as-of period, not today's position.
INSERT INTO authority_documents SELECT (jsonb_populate_record(NULL::authority_documents,to_jsonb(d)||'{"id":"historic_doc","authority_kind":"historical_organizational_publication","published_on":"1951-01-01","revised_on":"1951-01-01","valid_from":"1951-01-01","valid_until":"1951-12-31","source_locator_id":"historical_loc"}'::jsonb)).* FROM authority_documents d WHERE id='doc';
INSERT INTO authority_attestations SELECT (jsonb_populate_record(NULL::authority_attestations,to_jsonb(p)||'{"id":"historical","authority_kind":"historical_organizational_publication","authority_status":"historical_only","document_id":"historic_doc","valid_from":"1951-01-01","valid_until":"1951-12-31","as_of":"1951-06-01"}'::jsonb)).* FROM probe p;
SELECT pg_temp.rejected('{"authority_kind":"historical_organizational_publication","authority_status":"historical_only","document_id":"historic_doc","valid_from":"1951-01-01","valid_until":"1951-12-31","as_of":"2026-01-01"}');
UPDATE source_locators SET verification_status='disputed' WHERE id='historical_loc';
DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM authority_readings WHERE id='historical' AND effective_authority_status='unknown') THEN RAISE EXCEPTION 'stale historical evidence not downgraded'; END IF; END $$;
-- Original source identity must be the institutional issuer, not a personal page.
INSERT INTO authority_documents SELECT (jsonb_populate_record(NULL::authority_documents,to_jsonb(d)||'{"id":"wrong_source","source_locator_id":"other_loc","adoption_locator_id":"other_loc","issuer_tradition_evidence_locator_id":"other_loc"}'::jsonb)).* FROM authority_documents d WHERE id='doc';
SELECT pg_temp.rejected('{"document_id":"wrong_source"}');
-- Any later source identity mutation must invalidate the official label on read.
UPDATE sources SET creator='Fictional changed issuer' WHERE id='src';
DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM authority_readings WHERE id='original' AND effective_authority_status='unknown' AND NOT official_proof_sufficient) THEN RAISE EXCEPTION 'stale issuer identity not downgraded'; END IF; END $$;
UPDATE sources SET creator='Fictional institution' WHERE id='src';
DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM authority_readings WHERE id='original' AND effective_authority_status='adoption_documented') THEN RAISE EXCEPTION 'restored evidence not recognized'; END IF; END $$;
-- Retraction is explicit and affects the previous observation without rewriting it.
INSERT INTO authority_attestations SELECT (jsonb_populate_record(NULL::authority_attestations,to_jsonb(p)||'{"id":"retraction","supersedes_id":"original","is_retraction":true,"authority_status":"disputed"}'::jsonb)).* FROM probe p;
DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM authority_readings WHERE id='original' AND is_superseded AND effective_authority_status='unknown' AND NOT official_proof_sufficient) THEN RAISE EXCEPTION 'retraction did not suppress original authority'; END IF; END $$;
SELECT pg_temp.rejected('{"id":"negative","supersedes_id":"original","claim_version_id":"pver"}');
UPDATE source_locators SET verification_status='disputed' WHERE id='rights_loc';
DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM authority_readings WHERE id='reviewed' AND effective_authority_status='unknown' AND effective_quotation_status='direct_checked') THEN RAISE EXCEPTION 'stale rights evidence not downgraded'; END IF; END $$;
-- A dedicated read-only role sees only the sanitized view, not raw records.
INSERT INTO claims(id) VALUES ('research_claim');
INSERT INTO claim_versions(id,claim_id,revision_no,statement,extraction_method,revision_reason,data_class) VALUES ('research_ver','research_claim',1,'Fictional unlicensed original','human','synthetic test','scholarly_candidate');
INSERT INTO authority_attestations(id,claim_version_id,authority_kind,statement,representativity,uncertainty,data_class) VALUES ('research_candidate','research_ver','plural_or_unresolved','Fictional protected statement','Fictional protected representative prose','Fictional protected uncertainty','scholarly_candidate'), ('cross_group','research_ver','plural_or_unresolved','Fictional mixed group','Synthetic metadata','Fictional uncertainty','synthetic');
CREATE ROLE scriptura_i2_safe_fixture NOLOGIN;
GRANT USAGE ON SCHEMA public TO scriptura_i2_safe_fixture;
GRANT SELECT ON authority_safe_readings TO scriptura_i2_safe_fixture;
GRANT EXECUTE ON FUNCTION authority_safe_rows() TO scriptura_i2_safe_fixture;
SET LOCAL ROLE scriptura_i2_safe_fixture;
DO $$ BEGIN
 IF EXISTS (SELECT 1 FROM authority_safe_readings WHERE id='cross_group') THEN RAISE EXCEPTION 'cross-class data leaked'; END IF;
 IF NOT EXISTS (SELECT 1 FROM authority_safe_readings WHERE id='research_candidate' AND statement='[권리 검토 전 내용 숨김]' AND representativity IS NULL AND uncertainty IS NULL AND locator_value IS NULL) THEN RAISE EXCEPTION 'non-synthetic content was not masked'; END IF;
 IF NOT EXISTS (SELECT 1 FROM authority_safe_readings WHERE id='personal_view' AND statement='Synthetic statement') THEN RAISE EXCEPTION 'synthetic view unexpectedly hidden'; END IF;
 IF NOT EXISTS (SELECT 1 FROM authority_safe_readings WHERE id='quote_only' AND authority_kind='plural_or_unresolved' AND position_scope='insufficient_evidence' AND effective_authority_status='unknown' AND NOT official_proof_sufficient) THEN RAISE EXCEPTION 'unproven adoption kind was exposed'; END IF;
 PERFORM effective_quotation_status, effective_authority_status, effective_argument_status, effective_independent_review_status, official_proof_sufficient FROM authority_safe_readings WHERE id IN ('original','reviewed','guidance','historical','personal_view');
 BEGIN PERFORM * FROM authority_readings; RAISE EXCEPTION 'raw view access unexpectedly allowed'; EXCEPTION WHEN insufficient_privilege THEN NULL; END;
 BEGIN PERFORM * FROM authority_attestations; RAISE EXCEPTION 'raw table access unexpectedly allowed'; EXCEPTION WHEN insufficient_privilege THEN NULL; END;
 BEGIN PERFORM * FROM claim_versions; RAISE EXCEPTION 'claim raw table unexpectedly allowed'; EXCEPTION WHEN insufficient_privilege THEN NULL; END;
END $$;
RESET ROLE;
DO $$ BEGIN
  BEGIN UPDATE authority_attestations SET statement='rewritten' WHERE id='original'; RAISE EXCEPTION 'mutable authority record'; EXCEPTION WHEN SQLSTATE '55000' THEN NULL; END;
  BEGIN DELETE FROM authority_documents WHERE id='doc'; RAISE EXCEPTION 'mutable authority document'; EXCEPTION WHEN SQLSTATE '55000' THEN NULL; END;
END $$;
\echo 'PASS: I-2 documentary scope, independent axes, authority/rights/identity negatives and append-only audit'
ROLLBACK;
