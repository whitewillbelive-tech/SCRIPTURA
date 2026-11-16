-- Non-destructive rollback: populated C-01 data must be preserved.
BEGIN;
LOCK TABLE c01_research_versions, c01_source_contributors, c01_agent_relations IN ACCESS EXCLUSIVE MODE;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM c01_research_versions) OR EXISTS (SELECT 1 FROM c01_source_contributors)
     OR EXISTS (SELECT 1 FROM c01_agent_relations) THEN
    RAISE EXCEPTION 'rollback refused: C-01 data exists';
  END IF;
END $$;
DROP VIEW c01_source_contributors_effective;
DROP VIEW c01_agent_relations_effective;
DROP TRIGGER c01_source_class_lock ON sources;
DROP TRIGGER c01_agent_class_lock ON agents;
DROP FUNCTION c01_lock_data_class_boundary();
DROP TRIGGER c01_locator_identity_lock ON source_locators;
DROP FUNCTION c01_lock_checked_locator_identity();
DROP TRIGGER c01_agent_relation_check ON c01_agent_relations;
DROP TRIGGER c01_contributor_check ON c01_source_contributors;
DROP FUNCTION c01_check_graph_assertion();
DROP TABLE c01_agent_relations;
DROP TABLE c01_source_contributors;
DROP TRIGGER c01_versions_append_only ON c01_research_versions;
DROP TRIGGER c01_version_parent_check ON c01_research_versions;
DROP FUNCTION c01_check_version_parent();
DROP TABLE c01_research_versions;
COMMIT;
