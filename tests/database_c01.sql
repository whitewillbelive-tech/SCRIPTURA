-- Synthetic only; runs inside a rollback so no fixture survives.
BEGIN;
CREATE FUNCTION pg_temp.expect_error(sql_text text, expected text) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  BEGIN
    EXECUTE sql_text;
  EXCEPTION WHEN OTHERS THEN
    IF SQLSTATE = expected THEN RETURN; END IF;
    RAISE;
  END;
  RAISE EXCEPTION 'expected SQLSTATE %', expected;
END $$;
INSERT INTO agents(id,display_name,agent_kind,data_class) VALUES
  ('c01-syn-author','Synthetic author','person','synthetic'),
  ('c01-syn-org','Synthetic organization','institution','synthetic'),
  ('c01-syn-reviewer','Synthetic reviewer','person','synthetic'),
  ('c01-other','Unclassified institution','institution','unclassified');
INSERT INTO sources(id,title,source_kind,data_class) VALUES
  ('c01-syn-source','Synthetic document','article','synthetic'),
  ('c01-syn-source-two','Synthetic other document','article','synthetic');
INSERT INTO source_locators(id,source_id,locator_type,locator_value,verification_status) VALUES
  ('c01-checked','c01-syn-source','page','1','checked'),
  ('c01-pending','c01-syn-source','page','2','unverified'),
  ('c01-other-loc','c01-syn-source-two','page','1','checked');
INSERT INTO c01_source_contributors(id,source_id,agent_id,contributor_role,source_locator_id,assertion_status,reviewer_agent_id)
VALUES ('c01-author','c01-syn-source','c01-syn-author','author','c01-checked','source_checked','c01-syn-reviewer');
INSERT INTO c01_agent_relations(id,actor_agent_id,target_agent_id,relation_kind,source_locator_id,assertion_status,reviewer_agent_id)
VALUES ('c01-external','c01-syn-author','c01-syn-org','external_criticism','c01-checked','source_checked','c01-syn-reviewer');
SELECT pg_temp.expect_error($q$INSERT INTO c01_agent_relations(id,actor_agent_id,target_agent_id,relation_kind,source_locator_id,assertion_status,reviewer_agent_id) VALUES ('bad-pending','c01-syn-author','c01-syn-org','external_criticism','c01-pending','source_checked','c01-syn-reviewer')$q$,'23514');
SELECT pg_temp.expect_error($q$INSERT INTO c01_source_contributors(id,source_id,agent_id,contributor_role,source_locator_id) VALUES ('bad-source','c01-syn-source','c01-syn-org','publisher','c01-other-loc')$q$,'23514');
SELECT pg_temp.expect_error($q$INSERT INTO c01_agent_relations(id,actor_agent_id,target_agent_id,relation_kind) VALUES ('bad-mixed','c01-syn-author','c01-other','external_criticism')$q$,'23514');
SELECT pg_temp.expect_error($q$INSERT INTO c01_agent_relations(id,actor_agent_id,target_agent_id,relation_kind) VALUES ('bad-claim','c01-syn-author','c01-syn-org','official_doctrine')$q$,'23514');
SELECT pg_temp.expect_error($q$UPDATE source_locators SET source_id='c01-syn-source-two' WHERE id='c01-checked'$q$,'55000');
SELECT pg_temp.expect_error($q$UPDATE agents SET data_class='unclassified' WHERE id='c01-syn-author'$q$,'55000');
SELECT pg_temp.expect_error($q$UPDATE sources SET data_class='unclassified' WHERE id='c01-syn-source'$q$,'55000');
INSERT INTO c01_research_versions(id,version_label,archive_sha256,manifest_sha256,data_class) VALUES
  ('c01-v1','synthetic',repeat('a',64),repeat('b',64),'synthetic');
SELECT pg_temp.expect_error($q$UPDATE c01_research_versions SET version_label='altered' WHERE id='c01-v1'$q$,'55000');
SELECT pg_temp.expect_error($q$INSERT INTO c01_research_versions(id,parent_id,version_label,archive_sha256,manifest_sha256,data_class) VALUES ('c01-v2','c01-v1','candidate',repeat('c',64),repeat('d',64),'scholarly_candidate')$q$,'23514');
UPDATE source_locators SET verification_status='disputed' WHERE id='c01-checked';
DO $$ BEGIN
  IF (SELECT effective_status FROM c01_agent_relations_effective WHERE id='c01-external') <> 'recorded'
     OR (SELECT effective_status FROM c01_source_contributors_effective WHERE id='c01-author') <> 'recorded' THEN
    RAISE EXCEPTION 'disputed locator must not remain source checked';
  END IF;
END $$;
ROLLBACK;
