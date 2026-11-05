# S-1B.1 PostgreSQL isolation and review

Use a dedicated SCRIPTURA database only; never apply these migrations to UTT or any other project. PostgreSQL 15+ is required. Install `001_schema.sql`, `002_append_only.sql`, and `003_research_integrity.sql` in order with `psql -X -v ON_ERROR_STOP=1 "$DATABASE_URL" -f ...`. The migration is additive: existing source, claim and base records get `unclassified`, not an assumption that they are scholarly or synthetic. The API must exclude unclassified records and keep the synthetic and research views separate. `data_class` distinguishes synthetic, unclassified, candidate, source-verified, and scholarly-reviewed data; `license_status` and `storage_policy` independently express rights. Source verification does not establish scholarly consensus or theological truth.

`003` rejects a verified relationship without a checked, dated, non-empty locator. Approving a claim requires checked and dated source locators and verified attribution and evidence tied to verified sources. A synthetic claim cannot be promoted to scholarly data. Once a claim is verified, first mark it disputed to change its support or the identity/classification of a source it depends on. Checked source locator identity cannot be changed while referenced by verified records. The admin review function updates the claim and inserts both review and provenance events atomically; the existing `002` audit triggers reject UPDATE/DELETE/TRUNCATE. Privileged owners and superusers can alter triggers or data, so this is not tamper-proof against database administrators. Review source verification and scholarly review are distinct steps.

## Database roles

Provision separate non-superuser credentials for reads and reviews. Migrations should be owned by a trusted non-login owner; untrusted roles must not be able to CREATE in the migration schema or alter the function, triggers, tables, or memberships. The migration checks that PUBLIC cannot CREATE in its schema; database administrators must also ensure no other untrusted role has CREATE there. The review function is SECURITY DEFINER, has `pg_catalog`, the migration schema, then `pg_temp` as a fixed search path, and has no PUBLIC EXECUTE privilege. Its owner needs the applicable table permissions. Example for schema `public`, after substituting appropriate already-created roles:

```sql
GRANT USAGE ON SCHEMA public TO scriptura_read, scriptura_review;
GRANT SELECT ON corpora, works, reference_schemes, passages, traditions, agents,
  sources, source_locators, passage_alignments, agent_affiliations, claims,
  claim_versions, claim_attributions, claim_passages, claim_evidence,
  claim_relations, passage_relations TO scriptura_read;
GRANT SELECT ON review_events, provenance_events TO scriptura_review;
GRANT EXECUTE ON FUNCTION public.scriptura_review_claim(text,text,text,text,text,text) TO scriptura_review;
-- Do not grant DML on claim or audit tables, CREATE in the schema,
-- ownership, role membership with broader privileges, or superuser to either role.
```

Set `DATABASE_URL` to the read credential and the review-specific URL to a distinct, least-privileged credential. Keep secrets outside Git. The API must pin the reviewer ID server-side and never trust one supplied in an HTTP request. A holder of the review DB credential can pass any reviewer ID to the function: this prototype records a configured service reviewer, **not verified individual identity**. Individual authentication, authorization, independent reviewer identity and secure credential provisioning remain future work. Distinct URL names alone do not prove database grants are safe; inspect role membership, ownership and effective privileges.

## Tests, fixture and rollback

In a new disposable database, run `psql -X -v ON_ERROR_STOP=1 "$DATABASE_URL" -f tests/database_s1b1.sql`. It uses a transaction and rolls back; it creates a test role within that transaction, so the test DB user needs CREATEROLE. The test checks approval and audit atomicity, verified evidence/source protections, privilege separation and resistance to temporary-table shadowing. `tests/database.sql` and `tests/reverify-alignments.sql` remain available for regression.

`tests/seed_synthetic_pg.sql` is exclusively for a separate empty database whose name starts with `scriptura_synthetic_`. It inserts the existing explicitly synthetic fixture and labels its rows `synthetic`; it must not be used in a research database. The fixture is not real academic data and contains no collected external originals. Its checked/unverified statuses do not establish real facts.

For an empty dedicated database stop all writers, then run `db/003_research_integrity.down.sql`, `db/002_append_only.down.sql`, and `db/001_schema.down.sql` in that order. The 003 rollback refuses to discard any explicit classification; 002 refuses to remove audit protection when audit records exist; 001 refuses to drop nonempty tables. The scripts never erase classified or audited data to force rollback. For nonempty datasets, a separately reviewed preservation/migration plan is needed. A prior backup and change control remain necessary outside disposable tests.

A metadata-only policy is not itself proof that free-form claim statements contain no protected original. No external ingestion, embedding, bulk storage or redistribution is implemented here; ingest pipelines and rights enforcement for such features must be designed and tested before enabling them.

The approval checks and protections have not been validated under adversarial concurrent transactions or multiple independent writers. Row-level locking of a claim during review does not by itself establish serialization against every change to source, attribution, and evidence records. Use a single trusted writer for this prototype; transaction isolation, privilege boundaries, and concurrent update behavior require further design and tests before real scholarly data is admitted or the service is exposed to multiple administrators.
