#!/usr/bin/env python3
"""SCRIPTURA v0.1 fixture contract checks (Python stdlib only).

This is a contract smoke test, NOT a complete JSON Schema validator, legal review,
or scholarly verification. Rejects common dangerous reference and rights errors.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

TABLES = (
    'corpora', 'works', 'reference_schemes', 'passages', 'traditions', 'agents',
    'sources', 'source_locators', 'claims', 'claim_versions',
    'claim_attributions', 'claim_passages', 'claim_evidence',
    'claim_relations', 'passage_relations'
)


def validate(data):
    errors = []
    def err(message):
        errors.append(message)
    if not isinstance(data, dict):
        return ['Root must be an object']
    meta = data.get('metadata', {})
    if not isinstance(meta, dict) or meta.get('schema_version') != '0.1':
        err('metadata.schema_version must be 0.1')
    if meta.get('is_synthetic') and meta.get('approved_for_public_display'):
        err('Synthetic fixtures cannot be marked approved_for_public_display')

    indexed = {}
    for table in TABLES:
        rows = data.get(table, [])
        if not isinstance(rows, list):
            err(f'{table} must be a list')
            rows = []
        by_id = {}
        for no, row in enumerate(rows, 1):
            if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not row.get('id'):
                err(f'{table}[{no}] requires a nonempty id')
                continue
            if row['id'] in by_id:
                err(f'{table}: duplicate ID {row["id"]}')
            by_id[row['id']] = row
        indexed[table] = by_id

    def exists(table, value, origin, required=True):
        if value is None and not required:
            return
        if value not in indexed[table]:
            err(f'{origin}: missing {table} reference {value!r}')

    for work in indexed['works'].values():
        exists('corpora', work.get('corpus_id'), f'work {work["id"]}')
    for scheme in indexed['reference_schemes'].values():
        exists('corpora', scheme.get('corpus_id'), f'scheme {scheme["id"]}')
    seen_refs = set()
    for passage in indexed['passages'].values():
        context = f'passage {passage["id"]}'
        exists('corpora', passage.get('corpus_id'), context)
        exists('works', passage.get('work_id'), context)
        exists('reference_schemes', passage.get('scheme_id'), context)
        work = indexed['works'].get(passage.get('work_id'))
        scheme = indexed['reference_schemes'].get(passage.get('scheme_id'))
        if work and work.get('corpus_id') != passage.get('corpus_id'):
            err(f'{context}: work corpus mismatch')
        if scheme and scheme.get('corpus_id') != passage.get('corpus_id'):
            err(f'{context}: scheme corpus mismatch')
        key = (passage.get('scheme_id'), passage.get('work_id'), passage.get('external_ref'), passage.get('granularity'))
        if key in seen_refs:
            err(f'{context}: duplicate passage locator')
        seen_refs.add(key)
        if not passage.get('external_ref') or not passage.get('granularity'):
            err(f'{context}: external_ref and granularity required')
    for source in indexed['sources'].values():
        if not source.get('title'):
            err(f'source {source["id"]}: title required')
        policy = source.get('storage_policy', 'metadata_only')
        status = source.get('license_status', 'unknown')
        if policy not in ('metadata_only', 'link_only', 'snippet_only', 'full_text_allowed'):
            err(f'source {source["id"]}: unknown storage_policy')
        if policy == 'full_text_allowed' and (status != 'verified' or not (source.get('license_identifier') or source.get('license_url'))):
            err(f'source {source["id"]}: full text requires verified rights and license identifier or URL')
    for locator in indexed['source_locators'].values():
        exists('sources', locator.get('source_id'), f'locator {locator["id"]}')
        if not locator.get('locator_value'):
            err(f'locator {locator["id"]}: precise location required')
    for cv in indexed['claim_versions'].values():
        exists('claims', cv.get('claim_id'), f'claim version {cv["id"]}')
        if not cv.get('statement'):
            err(f'claim version {cv["id"]}: statement required')
        if cv.get('review_status') not in ('imported', 'extracted', 'source_verified', 'scholarly_reviewed', 'disputed', 'retired'):
            err(f'claim version {cv["id"]}: invalid review_status')
    attribution_by_version = defaultdict(list)
    for attribution in indexed['claim_attributions'].values():
        ctx = f'attribution {attribution["id"]}'
        exists('claim_versions', attribution.get('claim_version_id'), ctx)
        exists('agents', attribution.get('agent_id'), ctx)
        exists('source_locators', attribution.get('source_locator_id'), ctx, required=False)
        attribution_by_version[attribution.get('claim_version_id')].append(attribution)
        kind = attribution.get('attribution_kind')
        agent = indexed['agents'].get(attribution.get('agent_id'))
        if kind in ('official_doctrine', 'institutional_statement') and agent and agent.get('agent_kind') == 'person':
            err(f'{ctx}: an individual person cannot serve as the institutional issuer')
        if attribution.get('attribution_status') == 'verified':
            loc = indexed['source_locators'].get(attribution.get('source_locator_id'))
            if not loc or loc.get('verification_status') != 'checked':
                err(f'{ctx}: verified attribution requires checked source locator')

    passage_by_version = defaultdict(list)
    for claim_passage in indexed['claim_passages'].values():
        ctx = f'claim passage {claim_passage["id"]}'
        exists('claim_versions', claim_passage.get('claim_version_id'), ctx)
        exists('passages', claim_passage.get('passage_id'), ctx)
        passage_by_version[claim_passage.get('claim_version_id')].append(claim_passage)
    evidence_by_version = defaultdict(list)
    for evidence in indexed['claim_evidence'].values():
        ctx = f'evidence {evidence["id"]}'
        exists('claim_versions', evidence.get('claim_version_id'), ctx)
        for key, table in (('source_locator_id','source_locators'), ('passage_id','passages'), ('related_claim_version_id','claim_versions')):
            exists(table, evidence.get(key), ctx, required=False)
        if not any(evidence.get(k) for k in ('source_locator_id', 'passage_id', 'related_claim_version_id')):
            err(f'{ctx}: no evidence target')
        evidence_by_version[evidence.get('claim_version_id')].append(evidence)
    for cv in indexed['claim_versions'].values():
        if cv.get('review_status') in ('source_verified', 'scholarly_reviewed'):
            version_id = cv['id']
            if not passage_by_version[version_id]:
                err(f'claim version {version_id}: verified claim needs passage link')
            if not any(a.get('attribution_status') == 'verified' for a in attribution_by_version[version_id]):
                err(f'claim version {version_id}: verified claim needs verified attribution')
            checked_evidence = any(
                indexed['source_locators'].get(e.get('source_locator_id'), {}).get('verification_status') == 'checked'
                and e.get('review_status') == 'verified'
                for e in evidence_by_version[version_id]
            )
            if not checked_evidence:
                err(f'claim version {version_id}: verified claim needs checked and verified source evidence')

    for relation in indexed['claim_relations'].values():
        ctx = f'claim relation {relation["id"]}'
        exists('claim_versions', relation.get('from_version_id'), ctx)
        exists('claim_versions', relation.get('to_version_id'), ctx)
        exists('source_locators', relation.get('source_locator_id'), ctx, required=False)
        if relation.get('from_version_id') == relation.get('to_version_id'):
            err(f'{ctx}: self reference forbidden')
        if relation.get('review_status') == 'verified':
            loc = indexed['source_locators'].get(relation.get('source_locator_id'))
            if not loc or loc.get('verification_status') != 'checked':
                err(f'{ctx}: verified relation requires checked source locator')
    for relation in indexed['passage_relations'].values():
        ctx = f'passage relation {relation["id"]}'
        exists('passages', relation.get('from_passage_id'), ctx)
        exists('passages', relation.get('to_passage_id'), ctx)
        exists('source_locators', relation.get('source_locator_id'), ctx, required=False)
        if relation.get('relation_type') == 'interpretively_linked':
            exists('agents', relation.get('asserted_by_agent_id'), ctx)
        if relation.get('from_passage_id') == relation.get('to_passage_id'):
            err(f'{ctx}: self reference forbidden')
        if relation.get('review_status') == 'verified':
            loc = indexed['source_locators'].get(relation.get('source_locator_id'))
            if not loc or loc.get('verification_status') != 'checked':
                err(f'{ctx}: verified relation requires checked source locator')
    return errors


def main(argv):
    if len(argv) != 2:
        print('Usage: python scripts/validate_fixture.py FILE.json', file=sys.stderr)
        return 2
    path = Path(argv[1])
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        print(f'ERROR: unable to read JSON: {exc}', file=sys.stderr)
        return 2
    errors = validate(data)
    if errors:
        print(f'FAIL: {len(errors)} contract error(s)')
        for error in errors:
            print(' - ' + error)
        return 1
    print(f'PASS: dataset {data["metadata"]["dataset_id"]} satisfies starter contract (not scholarly review)')
    for table in TABLES:
        print(f'  {table}: {len(data.get(table, []))}')
    return 0

if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
