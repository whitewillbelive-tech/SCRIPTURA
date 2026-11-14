# SCRIPTURA Work D-13 / D-14~D-16 — schema-only compatibility contract

**Important:** This document exposes field names, paths, aggregate counts, and already-known hashes only. No original research text, titles, author identities, URLs, original IDs, or raw records are included. It is enough to develop a synthetic receiver fixture and a file-format adapter; real-data acceptance still requires private read-only tests in an environment that can actually open both archives.

## Immutable inputs

| Input | SHA-256 | Internal shape |
|---|---|---|
| `SCRIPTURA_D13_DATA_RESEARCH.zip` | `b109240d6e47df1e6a822fb530285bc4f0bfc39594123c72c90eaf7a277e72fe` | `baseline/SCRIPTURA_D12_DATA_RESEARCH.zip` + `d13/records/*.jsonl` |
| `SCRIPTURA_D14_D16_RESEARCH.zip` | `d78dd6ce2e467db91ba615ed7bf4a1fe962e137ac43ceafd9bc77ab80c95e800` | `MANIFEST.json`, `SHA256SUMS.txt`, `baseline/BASELINE_REFERENCE.json`, `d14/records`, `d15/records`, `d16/records` |

The newer archive references the older one by hash; it does not embed the older ZIP. The K-3 generic importer presently assumes lowercase `manifest.json` with `records/*.jsonl` and does **not** accept this historical Work layout.

## D-13 tables

All paths are `d13/records/<table>.jsonl`. Approximate counts are fixed by the baseline: `sources` 47, `editions` 47, `locators` 47, `passages` 19, `claims` 47, `evidence` 47, `rights` 423, `relationships` 1, `source_access_events` 47, `passage_coverage` 19.

- Source: `id`, `title`, `creator` / occasionally `author`, `publication_year`, `url` and rights/verifications. Never assume `creator` and `speaker` are the same entity.
- Edition: `id`, `source_id`; optional publication year, language, version details.
- Locator: `id`, `source_id`, `edition_id`, `location`; optional `verification_status` / `source_checked`.
- Passage: `id`, `corpus`, `reference_scheme`, `reference`.
- Claim: `id`, `source_id`, `source_locator_id`, `passage_ids` (list), `statement_ko`, `reasoning_ko`, `speaker`, `attribution_kind`, `source_verification_status`; possible `edition_id`. Actual original quotation or legal grant is not implied by `statement_ko`.
- Evidence: `id`, `claim_id`, `locator_id`, `status` / `kind`.
- Rights: `id`, `edition_id`, `action`, `decision` (unknown where not independently resolved).

D-13 also has contribution JSONL under `d13/contributions/`; these are **not additional records to concatenate with the matching consolidated `d13/records/` tables**. Count only consolidated records once.

## D-14 tables

Paths: `d14/records/<table>.jsonl`. Fixed count expectations: sources=96, editions=96, locators=98, passages=45, claims=98, evidence=98, rights=864. There are 2 change-history records and optionally 0 relationship records.

- Source: `id`, `title`, `author` (not always `creator`), `url` / `source_url`, `publication_year`; publisher and verification vary.
- Edition: `id`, `source_id`, `edition_description`, `translation_rights`, `url`.
- Locator: `id`, `source_id`, `edition_id`, `location` / `locator`, `verification`, `verified_scope`.
- Passage: `id`, `corpus`, `reference_scheme`, `reference`; `alignment_status` may be pending.
- Claim: `id`, `source_id`, `source_locator_id`, `passage_ids`, `statement_ko`, `reasoning_ko`, `speaker`, `attribution_kind`, `formal_adoption`; no implied official status.
- Evidence: `id`, `claim_id`, **`source_locator_id`** (where D-13 used `locator_id`), `relation`, `method`.
- Rights: `id`, `edition_id`, `action`, `decision` (all 864 currently recorded as unknown).

## D-15 and D-16

- `d15/records/claim_review_events.jsonl`: 47 audit rows that reference older claim IDs.
- `d15/records/d12_field_audit.jsonl`: 44 audit rows. These are review results, **not newly granted display rights**.
- `d15/records/relation_evidence.jsonl`: 1 pending relation observation.
- `d15/records/source_duplicate_review.jsonl`: 3 possible duplicate reviews.
- `d16/records/comparison_sets.jsonl`: 80 comparison groups. Core fields: `id`, `claim_ids` (list), `passage_id`, `relation`, `scope`, `direct_rebuttal_asserted`, `issue_ko`.
- `d16/records/relationships.jsonl`: 1 review-status record, not automatically a confirmed rebuttal.
- `d16/records/rights_evidence.jsonl`: 24 evidence rows.

Build an adapter with **two local ZIP inputs**, independent SHA anchors, bounded archive reads, path/CRC/checksum validation, cross-archive references, no data mutations, and explicit per-field display eligibility. Do not mistake correlation for rebuttal, author for speaker, or a publication-source role for official church adoption.

## Execution and acceptance rule

1. In a development environment without the two original ZIPs, implement and run **only synthetic format-contract tests** using this schema; do not claim actual D-13/D-14 integration complete.
2. For real acceptance, run the private input preflight plus read-only importer and local browser UI within an environment that can open those exact bytes.
3. Keep counts of accepted / quarantined / hidden records and verified UI search results. Original values, private paths, URLs, individual identifiers, and text never go to GitHub or CI logs.
4. Existing K-2/K-2.1 user-visible functionality must remain intact; Windows user acceptance comes after verified real-data integration.