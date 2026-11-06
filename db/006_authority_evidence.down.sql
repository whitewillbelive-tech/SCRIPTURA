-- Roll back only when no authority evidence exists; never delete recorded rows.
BEGIN;
LOCK TABLE authority_attestations, authority_documents IN ACCESS EXCLUSIVE MODE;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM authority_attestations) OR EXISTS (SELECT 1 FROM authority_documents) THEN
    RAISE EXCEPTION 'rollback refused: authority evidence exists';
  END IF;
END $$;
DROP VIEW authority_safe_readings;
DROP FUNCTION authority_safe_rows();
DROP VIEW authority_readings;
DROP TRIGGER authority_attestations_append_only ON authority_attestations;
DROP TRIGGER authority_attestation_evidence_guard ON authority_attestations;
DROP FUNCTION authority_attestation_guard();
DROP FUNCTION authority_adoption_valid(authority_attestations);
DROP FUNCTION authority_quotation_valid(authority_attestations);
DROP FUNCTION authority_issuer_valid(authority_attestations);
DROP FUNCTION authority_historical_valid(authority_attestations);
DROP FUNCTION authority_individual_valid(authority_attestations);
DROP FUNCTION authority_argument_valid(authority_attestations);
DROP FUNCTION authority_review_valid(authority_attestations);
DROP TRIGGER authority_documents_append_only ON authority_documents;
DROP TABLE authority_attestations;
DROP TABLE authority_documents;
DROP FUNCTION authority_locator_checked(text,text);
COMMIT;
