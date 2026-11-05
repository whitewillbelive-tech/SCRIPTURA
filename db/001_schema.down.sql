-- Run only in the dedicated SCRIPTURA database, after 002 down.
-- Refuse to remove schema if ANY application table contains data.
BEGIN;
LOCK TABLE corpora, works, reference_schemes, passages, traditions, agents, sources,
  source_locators, text_editions, passage_alignments, agent_affiliations, claims,
  claim_versions, claim_attributions, claim_passages, claim_evidence, claim_relations,
  passage_relations, review_events, provenance_events, ai_assessments IN ACCESS EXCLUSIVE MODE;
DO $$
DECLARE t text; has_rows boolean;
BEGIN
  FOREACH t IN ARRAY ARRAY['corpora','works','reference_schemes','passages','traditions','agents','sources','source_locators','text_editions','passage_alignments','agent_affiliations','claims','claim_versions','claim_attributions','claim_passages','claim_evidence','claim_relations','passage_relations','review_events','provenance_events','ai_assessments'] LOOP
    EXECUTE format('SELECT EXISTS (SELECT 1 FROM %I LIMIT 1)', t) INTO has_rows;
    IF has_rows THEN RAISE EXCEPTION 'rollback refused: % contains data', t; END IF;
  END LOOP;
END $$;
DROP TABLE ai_assessments, provenance_events, review_events, passage_relations, claim_relations,
  claim_evidence, claim_passages, claim_attributions, claim_versions, claims, agent_affiliations,
  passage_alignments, text_editions, source_locators, sources, agents, traditions, passages,
  reference_schemes, works, corpora;
COMMIT;
