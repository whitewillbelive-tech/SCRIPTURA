-- I-2 additive authority evidence. No external texts, claims or research rows are imported.
BEGIN;
CREATE TABLE authority_documents (
  id text PRIMARY KEY,
  issuer_agent_id text REFERENCES agents(id),
  tradition_id text REFERENCES traditions(id),
  authority_kind text NOT NULL CHECK (authority_kind IN ('normative_adopted','official_institutional_guidance','historical_organizational_publication','individual_insider_view','external_description_or_criticism','scholarly_individual_analysis','plural_or_unresolved')),
  jurisdiction text,
  published_on date,
  revised_on date,
  valid_from date,
  valid_until date,
  edition_label text,
  language_code text,
  verification_path text NOT NULL DEFAULT 'unknown' CHECK (verification_path IN ('direct','translation','secondary','search','unknown')),
  source_locator_id text REFERENCES source_locators(id),
  adoption_locator_id text REFERENCES source_locators(id),
  issuer_tradition_evidence_locator_id text REFERENCES source_locators(id),
  adoption_basis text,
  formal_adoption_confirmed boolean NOT NULL DEFAULT false,
  adoption_verified_by text REFERENCES agents(id),
  adoption_verified_at timestamptz,
  rights_evidence_status text NOT NULL DEFAULT 'unknown' CHECK (rights_evidence_status IN ('unknown','reviewed')),
  rights_evidence_locator_id text REFERENCES source_locators(id),
  rights_checked_by text REFERENCES agents(id),
  rights_checked_at timestamptz,
  rights_check_scope text,
  data_class text NOT NULL DEFAULT 'unclassified' CHECK (data_class IN ('synthetic','unclassified','scholarly_candidate','source_verified','scholarly_reviewed')),
  CHECK (valid_from IS NULL OR valid_until IS NULL OR valid_from <= valid_until),
  CHECK (published_on IS NULL OR revised_on IS NULL OR published_on <= revised_on)
);

CREATE TABLE authority_attestations (
  id text PRIMARY KEY,
  supersedes_id text REFERENCES authority_attestations(id),
  is_retraction boolean NOT NULL DEFAULT false,
  claim_version_id text NOT NULL REFERENCES claim_versions(id),
  tradition_id text REFERENCES traditions(id),
  subject_agent_id text REFERENCES agents(id),
  document_id text REFERENCES authority_documents(id),
  authority_kind text NOT NULL CHECK (authority_kind IN ('normative_adopted','official_institutional_guidance','historical_organizational_publication','individual_insider_view','external_description_or_criticism','scholarly_individual_analysis','plural_or_unresolved')),
  position_scope text NOT NULL DEFAULT 'insufficient_evidence' CHECK (position_scope IN ('documented_group_position','documented_local_position','historical_group_position','documented_individual_view','attributed_by_outsider','multiple_positions','insufficient_evidence')),
  perspective text NOT NULL DEFAULT 'unknown' CHECK (perspective IN ('community_self','outsider','scholar','individual','unknown')),
  quotation_status text NOT NULL DEFAULT 'unchecked' CHECK (quotation_status IN ('direct_checked','translation_checked','secondary_report','search_only','unchecked')),
  authority_status text NOT NULL DEFAULT 'unknown' CHECK (authority_status IN ('adoption_documented','issuer_documented','historical_only','individual_only','disputed','unknown')),
  argument_status text NOT NULL DEFAULT 'not_assessed' CHECK (argument_status IN ('documented_argument','externally_challenged','cross_checked','contested','not_assessed')),
  independent_review_status text NOT NULL DEFAULT 'none' CHECK (independent_review_status IN ('human_review_documented','published_critique_documented','none','pending')),
  statement text NOT NULL CHECK (length(btrim(statement)) > 0),
  jurisdiction text,
  valid_from date,
  valid_until date,
  as_of date,
  representativity text,
  proof_directness text NOT NULL DEFAULT 'unknown' CHECK (proof_directness IN ('direct','translation','secondary','search','unknown')),
  uncertainty text NOT NULL CHECK (length(btrim(uncertainty)) > 0),
  source_locator_id text REFERENCES source_locators(id),
  quotation_checked_by text REFERENCES agents(id),
  quotation_checked_at timestamptz,
  quotation_check_scope text,
  authority_checked_by text REFERENCES agents(id),
  authority_checked_at timestamptz,
  authority_check_scope text,
  argument_locator_id text REFERENCES source_locators(id),
  argument_counter_locator_id text REFERENCES source_locators(id),
  argument_checked_by text REFERENCES agents(id),
  argument_checked_at timestamptz,
  argument_check_scope text,
  independent_reviewer_agent_id text REFERENCES agents(id),
  independent_review_target_id text REFERENCES claim_versions(id),
  independent_review_locator_id text REFERENCES source_locators(id),
  independent_review_method text,
  independent_reviewed_at timestamptz,
  independent_review_verified boolean NOT NULL DEFAULT false,
  data_class text NOT NULL DEFAULT 'unclassified' CHECK (data_class IN ('synthetic','unclassified','scholarly_candidate','source_verified','scholarly_reviewed')),
  CHECK (valid_from IS NULL OR valid_until IS NULL OR valid_from <= valid_until),
  CHECK ((quotation_status <> 'direct_checked' OR proof_directness = 'direct') AND (quotation_status <> 'translation_checked' OR proof_directness = 'translation'))
);

-- A checked source is evidence of a location, not an authority or review judgment.
CREATE FUNCTION authority_locator_checked(p_id text, p_class text) RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT EXISTS (SELECT 1 FROM source_locators l JOIN sources s ON s.id=l.source_id
    WHERE l.id=p_id AND l.verification_status='checked' AND l.verified_at IS NOT NULL
      AND length(btrim(l.locator_value))>0
      AND ((p_class='synthetic' AND s.data_class='synthetic') OR
           (p_class IN ('scholarly_candidate','source_verified','scholarly_reviewed') AND s.data_class IN ('source_verified','scholarly_reviewed'))))
$$;

-- Re-evaluated on reads as well as inserts, so later changes cannot silently
-- turn stale documentary evidence into a current official position.
CREATE FUNCTION authority_adoption_valid(a authority_attestations) RETURNS boolean LANGUAGE sql STABLE AS $$
 SELECT COALESCE((SELECT
   a.authority_kind='normative_adopted' AND a.authority_status='adoption_documented'
   AND a.position_scope IN ('documented_group_position','documented_local_position')
   AND a.perspective='community_self' AND a.subject_agent_id=d.issuer_agent_id
   AND a.tradition_id=d.tradition_id AND a.data_class=d.data_class
   AND d.authority_kind='normative_adopted' AND d.formal_adoption_confirmed
   AND issuer.agent_kind IN ('institution','collective') AND issuer.data_class=a.data_class
   AND t.data_class=a.data_class AND cv.data_class=a.data_class
   AND a.jurisdiction=d.jurisdiction AND length(btrim(a.jurisdiction))>0
   AND a.valid_from=d.valid_from AND a.valid_until=d.valid_until
   AND a.as_of BETWEEN d.valid_from AND d.valid_until
   AND d.published_on IS NOT NULL AND d.revised_on IS NOT NULL
   AND d.published_on <= d.revised_on AND d.revised_on <= a.as_of
   AND d.valid_from IS NOT NULL AND d.valid_until IS NOT NULL
   AND length(btrim(d.edition_label))>0 AND length(btrim(d.language_code))>0
   AND d.verification_path IN ('direct','translation')
   AND a.proof_directness=d.verification_path
   AND ((d.verification_path='direct' AND a.quotation_status='direct_checked') OR (d.verification_path='translation' AND a.quotation_status='translation_checked'))
   AND d.adoption_verified_by IS NOT NULL AND d.adoption_verified_at IS NOT NULL
   AND a.authority_checked_by IS NOT NULL AND a.authority_checked_at IS NOT NULL AND length(btrim(a.authority_check_scope))>0
   AND length(btrim(d.adoption_basis))>0 AND length(btrim(a.representativity))>0
   AND d.rights_evidence_status='reviewed' AND d.rights_checked_by IS NOT NULL
   AND d.rights_checked_at IS NOT NULL AND length(btrim(d.rights_check_scope))>0
   AND authority_locator_checked(d.rights_evidence_locator_id,a.data_class)
   AND authority_locator_checked(d.source_locator_id,a.data_class)
   AND authority_locator_checked(d.adoption_locator_id,a.data_class)
   AND authority_locator_checked(d.issuer_tradition_evidence_locator_id,a.data_class)
   AND authority_locator_checked(a.source_locator_id,a.data_class)
   AND NOT EXISTS (SELECT 1 FROM source_locators l JOIN sources s ON s.id=l.source_id
       WHERE l.id = ANY(ARRAY[d.source_locator_id,d.adoption_locator_id,d.issuer_tradition_evidence_locator_id,a.source_locator_id])
         AND (s.source_kind <> 'official_document' OR s.creator IS DISTINCT FROM issuer.display_name))
   AND EXISTS (SELECT 1 FROM source_locators x JOIN source_locators y ON y.id=d.source_locator_id WHERE x.id=a.source_locator_id AND x.source_id=y.source_id)
   AND NOT EXISTS (SELECT 1 FROM source_locators l JOIN sources s ON s.id=l.source_id WHERE l.id = ANY(ARRAY[d.source_locator_id,a.source_locator_id]) AND (s.source_kind <> 'official_document' OR s.creator IS DISTINCT FROM issuer.display_name))
   AND EXISTS (SELECT 1 FROM claim_attributions ca WHERE ca.claim_version_id=a.claim_version_id AND ca.agent_id=d.issuer_agent_id AND ca.attribution_kind='official_doctrine' AND ca.attribution_status='verified' AND ca.source_locator_id=a.source_locator_id)
   FROM authority_documents d JOIN agents issuer ON issuer.id=d.issuer_agent_id
     JOIN traditions t ON t.id=a.tradition_id JOIN claim_versions cv ON cv.id=a.claim_version_id
   WHERE d.id=a.document_id),false)
$$;

CREATE FUNCTION authority_quotation_valid(a authority_attestations) RETURNS boolean LANGUAGE sql STABLE AS $$
 SELECT COALESCE(authority_locator_checked(a.source_locator_id,a.data_class)
   AND a.quotation_checked_by IS NOT NULL AND a.quotation_checked_at IS NOT NULL
   AND length(btrim(a.quotation_check_scope))>0
   AND ((a.quotation_status='direct_checked' AND a.proof_directness='direct') OR
        (a.quotation_status='translation_checked' AND a.proof_directness='translation')),false)
$$;
CREATE FUNCTION authority_issuer_valid(a authority_attestations) RETURNS boolean LANGUAGE sql STABLE AS $$
 SELECT COALESCE(EXISTS (SELECT 1 FROM authority_documents d JOIN agents issuer ON issuer.id=d.issuer_agent_id
   WHERE d.id=a.document_id AND d.tradition_id=a.tradition_id AND d.data_class=a.data_class
     AND issuer.agent_kind IN ('institution','collective') AND issuer.data_class=a.data_class
     AND d.authority_kind IN ('official_institutional_guidance','historical_organizational_publication')
     AND a.authority_kind=d.authority_kind AND d.published_on IS NOT NULL AND d.revised_on IS NOT NULL
     AND d.valid_from IS NOT NULL AND d.valid_until IS NOT NULL
     AND a.valid_from=d.valid_from AND a.valid_until=d.valid_until AND a.as_of BETWEEN d.valid_from AND d.valid_until
     AND d.revised_on <= a.as_of
     AND a.perspective='community_self' AND a.subject_agent_id=d.issuer_agent_id
     AND a.jurisdiction=d.jurisdiction AND length(btrim(d.jurisdiction))>0
     AND authority_locator_checked(d.source_locator_id,a.data_class) AND authority_locator_checked(a.source_locator_id,a.data_class)
     AND d.rights_evidence_status='reviewed' AND d.rights_checked_by IS NOT NULL AND d.rights_checked_at IS NOT NULL
     AND length(btrim(d.rights_check_scope))>0 AND authority_locator_checked(d.rights_evidence_locator_id,a.data_class)
     AND EXISTS (SELECT 1 FROM source_locators x JOIN source_locators y ON y.id=d.source_locator_id WHERE x.id=a.source_locator_id AND x.source_id=y.source_id)
     AND NOT EXISTS (SELECT 1 FROM source_locators l JOIN sources s ON s.id=l.source_id WHERE l.id = ANY(ARRAY[d.source_locator_id,a.source_locator_id]) AND (s.source_kind <> 'official_document' OR s.creator IS DISTINCT FROM issuer.display_name))
     AND EXISTS (SELECT 1 FROM claim_attributions ca WHERE ca.claim_version_id=a.claim_version_id AND ca.agent_id=d.issuer_agent_id AND ca.attribution_kind IN ('official_doctrine','institutional_statement') AND ca.attribution_status='verified' AND ca.source_locator_id=a.source_locator_id)
     AND a.authority_checked_by IS NOT NULL AND a.authority_checked_at IS NOT NULL
     AND length(btrim(a.authority_check_scope))>0),false)
$$;
CREATE FUNCTION authority_historical_valid(a authority_attestations) RETURNS boolean LANGUAGE sql STABLE AS $$
 SELECT COALESCE(EXISTS (SELECT 1 FROM authority_documents d JOIN agents issuer ON issuer.id=d.issuer_agent_id WHERE d.id=a.document_id
   AND issuer.agent_kind IN ('institution','collective') AND issuer.data_class=a.data_class
   AND a.perspective='community_self' AND a.subject_agent_id=d.issuer_agent_id
   AND d.authority_kind='historical_organizational_publication' AND a.authority_kind=d.authority_kind
   AND d.tradition_id=a.tradition_id AND d.data_class=a.data_class AND d.published_on IS NOT NULL
   AND d.valid_from IS NOT NULL AND d.valid_until IS NOT NULL
   AND a.valid_from=d.valid_from AND a.valid_until=d.valid_until AND a.as_of BETWEEN d.valid_from AND d.valid_until
   AND a.authority_checked_by IS NOT NULL AND a.authority_checked_at IS NOT NULL
   AND length(btrim(a.authority_check_scope))>0 AND authority_locator_checked(d.source_locator_id,a.data_class)
   AND authority_locator_checked(a.source_locator_id,a.data_class)
   AND d.rights_evidence_status='reviewed' AND d.rights_checked_by IS NOT NULL AND d.rights_checked_at IS NOT NULL
   AND length(btrim(d.rights_check_scope))>0 AND authority_locator_checked(d.rights_evidence_locator_id,a.data_class)
   AND EXISTS (SELECT 1 FROM source_locators x JOIN source_locators y ON y.id=d.source_locator_id WHERE x.id=a.source_locator_id AND x.source_id=y.source_id)
   AND EXISTS (SELECT 1 FROM claim_attributions ca WHERE ca.claim_version_id=a.claim_version_id AND ca.agent_id=d.issuer_agent_id AND ca.attribution_kind IN ('official_doctrine','institutional_statement') AND ca.attribution_status='verified' AND ca.source_locator_id=a.source_locator_id)),false)
$$;
CREATE FUNCTION authority_individual_valid(a authority_attestations) RETURNS boolean LANGUAGE sql STABLE AS $$
 SELECT COALESCE(EXISTS (SELECT 1 FROM authority_documents d JOIN agents ag ON ag.id=a.subject_agent_id
   WHERE d.id=a.document_id AND d.tradition_id=a.tradition_id AND d.data_class=a.data_class
   AND ag.agent_kind='person' AND ag.data_class=a.data_class
   AND ((a.authority_kind='individual_insider_view' AND a.perspective='individual') OR
        (a.authority_kind='scholarly_individual_analysis' AND a.perspective='scholar'))
   AND d.authority_kind=a.authority_kind AND d.published_on IS NOT NULL
   AND a.as_of IS NOT NULL AND a.as_of >= d.published_on
   AND a.authority_checked_by IS NOT NULL AND a.authority_checked_at IS NOT NULL AND length(btrim(a.authority_check_scope))>0
   AND authority_locator_checked(d.source_locator_id,a.data_class) AND authority_locator_checked(a.source_locator_id,a.data_class)
   AND d.rights_evidence_status='reviewed' AND d.rights_checked_by IS NOT NULL AND d.rights_checked_at IS NOT NULL
   AND length(btrim(d.rights_check_scope))>0 AND authority_locator_checked(d.rights_evidence_locator_id,a.data_class)
   AND EXISTS (SELECT 1 FROM source_locators x JOIN source_locators y ON y.id=d.source_locator_id WHERE x.id=a.source_locator_id AND x.source_id=y.source_id)
   AND EXISTS (SELECT 1 FROM claim_attributions ca WHERE ca.claim_version_id=a.claim_version_id AND ca.agent_id=a.subject_agent_id AND ca.attribution_kind IN ('individual_opinion','scholarly_interpretation') AND ca.attribution_status='verified' AND ca.source_locator_id=a.source_locator_id)),false)
$$;
CREATE FUNCTION authority_argument_valid(a authority_attestations) RETURNS boolean LANGUAGE sql STABLE AS $$
 SELECT COALESCE(a.argument_checked_by IS NOT NULL AND a.argument_checked_at IS NOT NULL
   AND length(btrim(a.argument_check_scope))>0 AND authority_locator_checked(a.argument_locator_id,a.data_class)
   AND (a.argument_status NOT IN ('cross_checked','contested') OR
       (authority_locator_checked(a.argument_counter_locator_id,a.data_class)
        AND EXISTS (SELECT 1 FROM source_locators x JOIN source_locators y ON y.id=a.argument_counter_locator_id
                    WHERE x.id=a.argument_locator_id AND x.source_id<>y.source_id))),false)
$$;
CREATE FUNCTION authority_review_valid(a authority_attestations) RETURNS boolean LANGUAGE sql STABLE AS $$
 SELECT COALESCE(a.independent_reviewer_agent_id IS NOT NULL AND a.independent_reviewed_at IS NOT NULL
   AND a.independent_review_target_id=a.claim_version_id
   AND a.independent_reviewer_agent_id IS DISTINCT FROM a.subject_agent_id
   AND NOT EXISTS (SELECT 1 FROM authority_documents d WHERE d.id=a.document_id AND d.issuer_agent_id=a.independent_reviewer_agent_id)
   AND EXISTS (SELECT 1 FROM agents ag WHERE ag.id=a.independent_reviewer_agent_id AND ag.data_class=a.data_class)
   AND length(btrim(a.independent_review_method))>0 AND authority_locator_checked(a.independent_review_locator_id,a.data_class)
   AND (a.independent_review_status <> 'human_review_documented' OR
      (a.independent_review_verified AND EXISTS (SELECT 1 FROM agents ag WHERE ag.id=a.independent_reviewer_agent_id AND ag.agent_kind='person' AND ag.data_class=a.data_class))),false)
$$;

CREATE FUNCTION authority_attestation_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.supersedes_id IS NOT NULL AND (NEW.supersedes_id=NEW.id OR NOT EXISTS (
    SELECT 1 FROM authority_attestations prior_attestation WHERE prior_attestation.id=NEW.supersedes_id
      AND prior_attestation.claim_version_id=NEW.claim_version_id AND prior_attestation.tradition_id IS NOT DISTINCT FROM NEW.tradition_id
      AND prior_attestation.data_class=NEW.data_class)) THEN RAISE EXCEPTION 'superseded observation must share the claim, tradition and class' USING ERRCODE='23514'; END IF;
  IF NEW.is_retraction AND (NEW.supersedes_id IS NULL OR NEW.authority_status<>'disputed') THEN
    RAISE EXCEPTION 'retraction must identify a disputed earlier observation' USING ERRCODE='23514'; END IF;
  IF NEW.authority_status='adoption_documented' AND NOT authority_adoption_valid(NEW) THEN
    RAISE EXCEPTION 'formal adoption requires scoped checked documentary evidence' USING ERRCODE='23514'; END IF;
  IF NEW.authority_status='issuer_documented' AND NOT authority_issuer_valid(NEW) THEN
    RAISE EXCEPTION 'institutional issuance requires documented scoped evidence' USING ERRCODE='23514'; END IF;
  IF NEW.authority_status='individual_only' AND NOT authority_individual_valid(NEW) THEN
    RAISE EXCEPTION 'individual view requires documented personal attribution' USING ERRCODE='23514'; END IF;
  IF NEW.authority_status='historical_only' AND NOT authority_historical_valid(NEW) THEN
    RAISE EXCEPTION 'historical position requires dated evidence and review context' USING ERRCODE='23514'; END IF;
  IF NEW.quotation_status IN ('direct_checked','translation_checked') AND NOT authority_quotation_valid(NEW) THEN
    RAISE EXCEPTION 'checked quotation requires checked locator and review context' USING ERRCODE='23514'; END IF;
  IF NEW.argument_status <> 'not_assessed' AND NOT authority_argument_valid(NEW) THEN
    RAISE EXCEPTION 'assessed argument requires evidence and review context' USING ERRCODE='23514'; END IF;
  IF NEW.independent_review_status IN ('human_review_documented','published_critique_documented') AND NOT authority_review_valid(NEW) THEN
    RAISE EXCEPTION 'review requires documented reviewer, scope and source' USING ERRCODE='23514'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER authority_attestation_evidence_guard BEFORE INSERT OR UPDATE ON authority_attestations FOR EACH ROW EXECUTE FUNCTION authority_attestation_guard();

-- Authority is an observation, not a mutable verdict. Insert a new observation
-- for corrections; users cannot rewrite history with UPDATE/DELETE/TRUNCATE.
CREATE TRIGGER authority_documents_append_only BEFORE UPDATE OR DELETE OR TRUNCATE ON authority_documents FOR EACH STATEMENT EXECUTE FUNCTION scriptura_reject_audit_mutation();
CREATE TRIGGER authority_attestations_append_only BEFORE UPDATE OR DELETE OR TRUNCATE ON authority_attestations FOR EACH STATEMENT EXECUTE FUNCTION scriptura_reject_audit_mutation();

CREATE VIEW authority_readings AS
SELECT a.*,
       CASE WHEN a.quotation_status IN ('direct_checked','translation_checked') AND NOT authority_quotation_valid(a)
            THEN 'unchecked' ELSE a.quotation_status END AS effective_quotation_status,
       CASE WHEN a.is_retraction OR EXISTS(SELECT 1 FROM authority_attestations later WHERE later.supersedes_id=a.id) THEN 'unknown'
            WHEN (a.authority_status='adoption_documented' AND NOT authority_adoption_valid(a)) OR
                 (a.authority_status='issuer_documented' AND NOT authority_issuer_valid(a)) OR
                 (a.authority_status='historical_only' AND NOT authority_historical_valid(a)) OR
                 (a.authority_status='individual_only' AND NOT authority_individual_valid(a))
            THEN 'unknown' ELSE a.authority_status END AS effective_authority_status,
       CASE WHEN a.argument_status<>'not_assessed' AND NOT authority_argument_valid(a)
            THEN 'not_assessed' ELSE a.argument_status END AS effective_argument_status,
       CASE WHEN a.independent_review_status IN ('human_review_documented','published_critique_documented') AND NOT authority_review_valid(a)
            THEN 'pending' ELSE a.independent_review_status END AS effective_independent_review_status,
       (authority_adoption_valid(a) AND NOT a.is_retraction AND NOT EXISTS(SELECT 1 FROM authority_attestations later WHERE later.supersedes_id=a.id)) AS official_proof_sufficient,
       EXISTS(SELECT 1 FROM authority_attestations later WHERE later.supersedes_id=a.id) AS is_superseded
FROM authority_attestations a;

-- Safe, separately permissioned API surface. This function returns no raw
-- research prose and runs under a trusted migration owner with a locked search
-- path; the read role requires only schema usage, execute on this function, and
-- SELECT on the safe view. Never grant it raw tables or the internal view.
SET LOCAL check_function_bodies = off;
CREATE FUNCTION authority_safe_rows() RETURNS TABLE (
  id text, claim_version_id text, tradition_id text, authority_kind text,
  position_scope text, perspective text,
  effective_quotation_status text, effective_authority_status text,
  effective_argument_status text, effective_independent_review_status text,
  official_proof_sufficient boolean, proof_directness text, jurisdiction text,
  as_of date, valid_from date, valid_until date,
  statement text, representativity text, uncertainty text, locator_value text,
  published_on date, revised_on date, edition_label text, language_code text,
  issuer_name text, data_class text, claim_data_class text, claim_review_status text,
  is_superseded boolean, is_retraction boolean, classification_consistent boolean
) LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,public AS $$
SELECT a.id,a.claim_version_id,a.tradition_id,
       CASE WHEN (a.authority_kind='normative_adopted' AND NOT a.official_proof_sufficient)
              OR (a.authority_kind='official_institutional_guidance' AND a.effective_authority_status<>'issuer_documented')
              OR (a.authority_kind='historical_organizational_publication' AND a.effective_authority_status<>'historical_only')
              OR (a.authority_kind IN ('individual_insider_view','scholarly_individual_analysis') AND a.effective_authority_status<>'individual_only')
            THEN 'plural_or_unresolved' ELSE a.authority_kind END,
       CASE WHEN (a.authority_kind='normative_adopted' AND NOT a.official_proof_sufficient)
              OR (a.authority_kind='official_institutional_guidance' AND a.effective_authority_status<>'issuer_documented')
              OR (a.authority_kind='historical_organizational_publication' AND a.effective_authority_status<>'historical_only')
              OR (a.authority_kind IN ('individual_insider_view','scholarly_individual_analysis') AND a.effective_authority_status<>'individual_only')
            THEN 'insufficient_evidence' ELSE a.position_scope END,
       a.perspective,
       a.effective_quotation_status,a.effective_authority_status,a.effective_argument_status,
       a.effective_independent_review_status,a.official_proof_sufficient,
       CASE WHEN a.effective_quotation_status='unchecked' THEN 'unknown' ELSE a.proof_directness END,
       a.jurisdiction,a.as_of,a.valid_from,a.valid_until,
       CASE WHEN a.data_class='synthetic' THEN a.statement ELSE '[권리 검토 전 내용 숨김]' END,
       CASE WHEN a.data_class='synthetic' THEN a.representativity ELSE NULL END,
       CASE WHEN a.data_class='synthetic' THEN a.uncertainty ELSE NULL END,
       CASE WHEN a.data_class='synthetic' THEN l.locator_value ELSE NULL END,
       d.published_on,d.revised_on,d.edition_label,d.language_code,ag.display_name,
       a.data_class,cv.data_class,cv.review_status,a.is_superseded,a.is_retraction,
       CASE WHEN a.data_class='synthetic' THEN
         (cv.data_class='synthetic' AND (t.id IS NULL OR t.data_class='synthetic')
          AND (d.id IS NULL OR d.data_class='synthetic') AND (ag.id IS NULL OR ag.data_class='synthetic')
          AND (l.id IS NULL OR src.data_class='synthetic'))
       ELSE
         (a.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed')
          AND cv.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed')
          AND (t.id IS NULL OR t.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed'))
          AND (d.id IS NULL OR d.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed'))
          AND (ag.id IS NULL OR ag.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed'))
          AND (l.id IS NULL OR src.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed')))
       END
FROM authority_readings a
JOIN claim_versions cv ON cv.id=a.claim_version_id
LEFT JOIN traditions t ON t.id=a.tradition_id
LEFT JOIN authority_documents d ON d.id=a.document_id
LEFT JOIN agents ag ON ag.id=d.issuer_agent_id
LEFT JOIN source_locators l ON l.id=a.source_locator_id
LEFT JOIN sources src ON src.id=l.source_id
WHERE CASE WHEN a.data_class='synthetic' THEN
  (cv.data_class='synthetic' AND (t.id IS NULL OR t.data_class='synthetic')
   AND (d.id IS NULL OR d.data_class='synthetic') AND (ag.id IS NULL OR ag.data_class='synthetic')
   AND (l.id IS NULL OR src.data_class='synthetic'))
ELSE
  (a.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed')
   AND cv.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed')
   AND (t.id IS NULL OR t.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed'))
   AND (d.id IS NULL OR d.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed'))
   AND (ag.id IS NULL OR ag.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed'))
   AND (l.id IS NULL OR src.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed')))
END
$$;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_namespace n, LATERAL aclexplode(COALESCE(n.nspacl,acldefault('n',n.nspowner))) a
    WHERE n.nspname=current_schema() AND a.grantee=0 AND a.privilege_type='CREATE') THEN
    RAISE EXCEPTION 'authority schema must not allow CREATE to PUBLIC';
  END IF;
  EXECUTE format('ALTER FUNCTION %I.authority_safe_rows() SET search_path = pg_catalog, %I, pg_temp',current_schema(),current_schema());
END $$;
SET LOCAL check_function_bodies = on;
CREATE VIEW authority_safe_readings WITH (security_barrier=true) AS SELECT * FROM authority_safe_rows();
REVOKE ALL ON authority_documents,authority_attestations,authority_readings,authority_safe_readings FROM PUBLIC;
REVOKE ALL ON FUNCTION authority_locator_checked(text,text),authority_adoption_valid(authority_attestations),
  authority_quotation_valid(authority_attestations),authority_issuer_valid(authority_attestations),
  authority_historical_valid(authority_attestations),authority_individual_valid(authority_attestations),
  authority_argument_valid(authority_attestations),authority_review_valid(authority_attestations),authority_safe_rows() FROM PUBLIC;
COMMIT;
