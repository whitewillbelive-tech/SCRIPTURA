-- SCRIPTURA v0.1 / PostgreSQL 15+ / initial schema draft
-- Do not run against existing UTT or Site databases.
-- This migration intentionally does NOT ingest copyrighted text.
-- Status promotion and source-locator verification require transactional application checks.
-- Multi-step review logic is not fully enforceable by CHECK constraints alone.

BEGIN;

CREATE TABLE corpora (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  corpus_kind TEXT NOT NULL CHECK (corpus_kind IN ('bible','quran','rabbinic','patristic','commentary','other')),
  description TEXT
);

CREATE TABLE works (
  id TEXT PRIMARY KEY,
  corpus_id TEXT NOT NULL REFERENCES corpora(id),
  title TEXT NOT NULL,
  abbrev TEXT,
  description TEXT,
  UNIQUE (id, corpus_id)
);

CREATE TABLE reference_schemes (
  id TEXT PRIMARY KEY,
  corpus_id TEXT NOT NULL REFERENCES corpora(id),
  scheme_name TEXT NOT NULL,
  normative_uri TEXT,
  notes TEXT,
  UNIQUE (id, corpus_id)
);

CREATE TABLE passages (
  id TEXT PRIMARY KEY,
  corpus_id TEXT NOT NULL,
  work_id TEXT NOT NULL,
  scheme_id TEXT NOT NULL,
  external_ref TEXT NOT NULL,
  granularity TEXT NOT NULL CHECK (granularity IN ('book','chapter','verse','range','paragraph','word','other')),
  location_expression JSONB NOT NULL DEFAULT '{}'::jsonb,
  indexing_status TEXT NOT NULL DEFAULT 'pending' CHECK (indexing_status IN ('pending','verified','uncertain')),
  FOREIGN KEY (work_id, corpus_id) REFERENCES works(id,corpus_id),
  FOREIGN KEY (scheme_id, corpus_id) REFERENCES reference_schemes(id,corpus_id),
  UNIQUE (scheme_id, work_id, external_ref, granularity)
);

CREATE TABLE traditions (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  classification_kind TEXT NOT NULL CHECK (classification_kind IN ('religion','denomination','movement','school','other')),
  parent_id TEXT REFERENCES traditions(id),
  active_period TEXT,
  notes TEXT,
  CHECK (id IS DISTINCT FROM parent_id)
);

CREATE TABLE agents (
  id TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  agent_kind TEXT NOT NULL CHECK (agent_kind IN ('person','institution','collective')),
  name_disambiguator TEXT,
  note TEXT
);

CREATE TABLE sources (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  creator TEXT,
  publication_year INTEGER,
  source_kind TEXT NOT NULL CHECK (source_kind IN ('book','article','video','lecture','official_document','manuscript','dataset','webpage','other')),
  source_url TEXT,
  doi TEXT,
  edition_or_version TEXT,
  storage_policy TEXT NOT NULL DEFAULT 'metadata_only' CHECK (storage_policy IN ('metadata_only','link_only','snippet_only','full_text_allowed')),
  license_status TEXT NOT NULL DEFAULT 'unknown' CHECK (license_status IN ('verified','pending_review','restricted','unknown')),
  license_identifier TEXT,
  license_url TEXT,
  rights_holder TEXT,
  attribution_notice TEXT,
  rights_checked_at TIMESTAMPTZ,
  retention_limit_days INTEGER CHECK (retention_limit_days IS NULL OR retention_limit_days >= 0),
  content_sha256 TEXT CHECK (content_sha256 IS NULL OR content_sha256 ~ '^[a-f0-9]{64}$'),
  rights_notes TEXT,
  CONSTRAINT full_text_requires_license CHECK (storage_policy <> 'full_text_allowed' OR (license_status = 'verified' AND (license_identifier IS NOT NULL OR license_url IS NOT NULL)))
);

CREATE UNIQUE INDEX sources_doi_unique ON sources(lower(doi)) WHERE doi IS NOT NULL;

CREATE TABLE source_locators (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL REFERENCES sources(id),
  locator_type TEXT NOT NULL CHECK (locator_type IN ('page','page_range','section','paragraph','chapter','timestamp','verse','url_fragment','other')),
  locator_value TEXT NOT NULL,
  direct_url TEXT,
  verification_status TEXT NOT NULL DEFAULT 'unverified' CHECK (verification_status IN ('unverified','checked','disputed')),
  quote_sha256 TEXT CHECK (quote_sha256 IS NULL OR quote_sha256 ~ '^[a-f0-9]{64}$'),
  verified_at TIMESTAMPTZ
);

CREATE TABLE text_editions (
  id TEXT PRIMARY KEY,
  work_id TEXT NOT NULL REFERENCES works(id),
  edition_label TEXT NOT NULL,
  language_code TEXT NOT NULL,
  corpus_id TEXT NOT NULL REFERENCES corpora(id),
  scheme_id TEXT,
  source_id TEXT REFERENCES sources(id),
  witness_or_translation TEXT NOT NULL CHECK (witness_or_translation IN ('witness','critical_edition','translation','other')),
  notes TEXT,
  FOREIGN KEY (work_id, corpus_id) REFERENCES works(id, corpus_id),
  FOREIGN KEY (scheme_id, corpus_id) REFERENCES reference_schemes(id, corpus_id)
);

CREATE TABLE passage_alignments (
  id TEXT PRIMARY KEY,
  from_passage_id TEXT NOT NULL REFERENCES passages(id),
  to_passage_id TEXT NOT NULL REFERENCES passages(id),
  alignment_type TEXT NOT NULL CHECK (alignment_type IN ('equivalent','overlapping','partial','uncertain')),
  review_status TEXT NOT NULL DEFAULT 'proposed' CHECK (review_status IN ('proposed','verified','disputed')),
  source_locator_id TEXT REFERENCES source_locators(id),
  rationale TEXT NOT NULL,
  CHECK (from_passage_id <> to_passage_id)
);

CREATE TABLE agent_affiliations (
  id TEXT PRIMARY KEY,
  agent_id TEXT NOT NULL REFERENCES agents(id),
  tradition_id TEXT NOT NULL REFERENCES traditions(id),
  relation_type TEXT NOT NULL CHECK (relation_type IN ('self_identified','officially_affiliated','historically_attributed','reported_by_other','contested')),
  period_start INTEGER,
  period_end INTEGER,
  source_locator_id TEXT REFERENCES source_locators(id),
  notes TEXT,
  CHECK (period_start IS NULL OR period_end IS NULL OR period_start <= period_end)
);

CREATE TABLE claims (
  id TEXT PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  retired_at TIMESTAMPTZ,
  internal_notes TEXT
);

CREATE TABLE claim_versions (
  id TEXT PRIMARY KEY,
  claim_id TEXT NOT NULL REFERENCES claims(id),
  revision_no INTEGER NOT NULL CHECK (revision_no >= 1),
  statement TEXT NOT NULL,
  language_code TEXT NOT NULL DEFAULT 'ko',
  interpretive_method TEXT,
  extraction_method TEXT NOT NULL CHECK (extraction_method IN ('human','ai_assisted','ai_generated')),
  review_status TEXT NOT NULL DEFAULT 'extracted' CHECK (review_status IN ('imported','extracted','source_verified','scholarly_reviewed','disputed','retired')),
  created_by_agent_id TEXT REFERENCES agents(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  revision_reason TEXT NOT NULL,
  UNIQUE (claim_id, revision_no)
);

CREATE TABLE claim_attributions (
  id TEXT PRIMARY KEY,
  claim_version_id TEXT NOT NULL REFERENCES claim_versions(id),
  agent_id TEXT NOT NULL REFERENCES agents(id),
  attribution_kind TEXT NOT NULL CHECK (attribution_kind IN ('official_doctrine','institutional_statement','scholarly_interpretation','individual_opinion','reported_view')),
  source_locator_id TEXT REFERENCES source_locators(id),
  attribution_status TEXT NOT NULL DEFAULT 'unverified' CHECK (attribution_status IN ('unverified','verified','disputed')),
  explanatory_note TEXT,
  CONSTRAINT verified_attribution_requires_source CHECK (attribution_status <> 'verified' OR source_locator_id IS NOT NULL)
);

CREATE TABLE claim_passages (
  id TEXT PRIMARY KEY,
  claim_version_id TEXT NOT NULL REFERENCES claim_versions(id),
  passage_id TEXT NOT NULL REFERENCES passages(id),
  link_kind TEXT NOT NULL CHECK (link_kind IN ('interpretation_of','applies_to','discusses','quotes')),
  UNIQUE (claim_version_id, passage_id, link_kind)
);

CREATE TABLE claim_evidence (
  id TEXT PRIMARY KEY,
  claim_version_id TEXT NOT NULL REFERENCES claim_versions(id),
  source_locator_id TEXT REFERENCES source_locators(id),
  passage_id TEXT REFERENCES passages(id),
  related_claim_version_id TEXT REFERENCES claim_versions(id),
  evidence_role TEXT NOT NULL CHECK (evidence_role IN ('supports','rebuts','counterexample','context','original_quote','translation_argument')),
  explanation TEXT NOT NULL,
  review_status TEXT NOT NULL DEFAULT 'proposed' CHECK (review_status IN ('proposed','verified','disputed')),
  CHECK (source_locator_id IS NOT NULL OR passage_id IS NOT NULL OR related_claim_version_id IS NOT NULL)
);

CREATE TABLE claim_relations (
  id TEXT PRIMARY KEY,
  from_version_id TEXT NOT NULL REFERENCES claim_versions(id),
  to_version_id TEXT NOT NULL REFERENCES claim_versions(id),
  relation_type TEXT NOT NULL CHECK (relation_type IN ('supports','contradicts','qualifies','rebuts','depends_on','historically_influenced_by')),
  source_locator_id TEXT REFERENCES source_locators(id),
  review_status TEXT NOT NULL DEFAULT 'proposed' CHECK (review_status IN ('proposed','verified','disputed')),
  rationale TEXT NOT NULL,
  CHECK (from_version_id <> to_version_id),
  CONSTRAINT verified_claim_relation_requires_source CHECK (review_status <> 'verified' OR source_locator_id IS NOT NULL)
);

CREATE TABLE passage_relations (
  id TEXT PRIMARY KEY,
  from_passage_id TEXT NOT NULL REFERENCES passages(id),
  to_passage_id TEXT NOT NULL REFERENCES passages(id),
  relation_type TEXT NOT NULL CHECK (relation_type IN ('quotes','alludes_to','parallel','interpretively_linked')),
  asserted_by_agent_id TEXT REFERENCES agents(id),
  source_locator_id TEXT REFERENCES source_locators(id),
  review_status TEXT NOT NULL DEFAULT 'proposed' CHECK (review_status IN ('proposed','verified','disputed')),
  rationale TEXT NOT NULL,
  CHECK (from_passage_id <> to_passage_id),
  CONSTRAINT verified_passage_relation_requires_source CHECK (review_status <> 'verified' OR source_locator_id IS NOT NULL),
  CONSTRAINT interpretive_link_requires_attribution CHECK (relation_type <> 'interpretively_linked' OR asserted_by_agent_id IS NOT NULL)
);

CREATE TABLE review_events (
  id TEXT PRIMARY KEY,
  target_entity_type TEXT NOT NULL,
  target_entity_id TEXT NOT NULL,
  reviewer_agent_id TEXT NOT NULL REFERENCES agents(id),
  decision TEXT NOT NULL CHECK (decision IN ('approve_source','approve_scholarly','request_changes','reject','mark_disputed')),
  rationale TEXT NOT NULL,
  source_locator_id TEXT REFERENCES source_locators(id),
  reviewed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE provenance_events (
  id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL CHECK (event_type IN ('import','extract','transform','review','correct','retire','evaluate')),
  target_entity_type TEXT NOT NULL,
  target_entity_id TEXT NOT NULL,
  actor_agent_id TEXT REFERENCES agents(id),
  source_id TEXT REFERENCES sources(id),
  input_hash TEXT CHECK (input_hash IS NULL OR input_hash ~ '^[a-f0-9]{64}$'),
  tool_name TEXT,
  tool_version TEXT,
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE ai_assessments (
  id TEXT PRIMARY KEY,
  question TEXT NOT NULL,
  answer TEXT NOT NULL,
  assessment_mode TEXT NOT NULL CHECK (assessment_mode IN ('historical_linguistic','textual_criticism','canonical','confessional','logical','mixed')),
  assumption_notes TEXT NOT NULL,
  conclusion_status TEXT NOT NULL CHECK (conclusion_status IN ('better_supported','conditional','contested','insufficient_evidence')),
  rubric_version TEXT NOT NULL,
  model_identifier TEXT NOT NULL,
  dataset_snapshot TEXT NOT NULL,
  source_locator_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  claim_version_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_passages_ref ON passages(scheme_id, external_ref);
CREATE INDEX idx_claim_versions_status ON claim_versions(review_status);
CREATE INDEX idx_claim_passages_passage ON claim_passages(passage_id);
CREATE INDEX idx_claim_attributions_agent ON claim_attributions(agent_id, attribution_kind);
CREATE INDEX idx_claim_evidence_claim ON claim_evidence(claim_version_id);
CREATE INDEX idx_claim_relations_from ON claim_relations(from_version_id);
CREATE INDEX idx_claim_relations_to ON claim_relations(to_version_id);
CREATE INDEX idx_passage_relations_from ON passage_relations(from_passage_id);
CREATE INDEX idx_passage_relations_to ON passage_relations(to_passage_id);
CREATE INDEX idx_source_locators_source ON source_locators(source_id);
CREATE INDEX idx_provenance_target ON provenance_events(target_entity_type, target_entity_id);

COMMIT;
