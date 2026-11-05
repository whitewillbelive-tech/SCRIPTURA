#!/usr/bin/env python3
"""Pinned D-3 read-only reception, preview, and opt-in private provenance."""
import argparse
from collections import defaultdict
import json
import os
import re
import stat
import sys
from pathlib import Path

from d3_bridge.validator import validate_archive

ROOT = Path(__file__).resolve().parents[1]
LINK_FIELDS = {
    'editions': ('source_id',), 'locators': ('edition_id',),
    'rights': ('edition_id',), 'claims': ('agent_id', 'locator_id', 'passage_ids'),
    'evidence': ('claim_id', 'locator_id'),
    'relations': ('from_claim_id', 'to_claim_id', 'locator_id'),
    'alignments': ('from_passage_id', 'to_passage_id', 'locator_id'),
    'affiliations': ('agent_id', 'locator_id'), 'reviews': ('target_id',),
    'bibliographic_edges': ('from_source_id', 'to_source_id', 'locator_id'),
}
COVERAGE_FIELDS = ('work_label', 'comparison_unit', 'opc_wcf_listing_status',
                   'usccb_bible_listing_status', 'chabad_tanakh_listing_status',
                   'oca_institutional_explanation_status', 'd3_address_coverage',
                   'd3_merged_passage_records', 'd3_merged_claim_links', 'review_status')


def private_review(records):
    """Only identifiers and provenance; never copy free-text sources or URLs."""
    rows = []
    for table, entries in records.items():
        for entry in entries:
            data = entry['data']
            links = {}
            for field in LINK_FIELDS.get(table, ()):
                value = data.get(field)
                if isinstance(value, str):
                    links[field] = value
                elif isinstance(value, list) and all(isinstance(v, str) for v in value):
                    links[field] = value
            status = data.get('review_status', data.get('verification_status'))
            if table == 'reviews':
                status = data.get('decision')
            rights = ({'action': data.get('action'), 'decision': data.get('decision')}
                      if table == 'rights' else None)
            rows.append({'table': table, 'original_id': data['id'], 'origin_file': entry['file'],
                         'row_number': entry['row_number'], 'line_sha256': entry['sha256'],
                         'disposition': entry['disposition'], 'reason_codes': entry['reasons'],
                         'reference_ids': links, 'original_status': status,
                         'rights_decision': rights})
    coverage = [{k: entry['data'].get(k) for k in COVERAGE_FIELDS} for entry in records['coverage']]
    # A recorded affiliation is an attributed association only. It is not a
    # doctrine, and its date cannot be inferred to cover the claim's context.
    passages = {entry['data']['id']: entry['data'] for entry in records.get('passages', [])}
    affiliations = defaultdict(list)
    for entry in records.get('affiliations', []):
        affiliations[entry['data']['agent_id']].append(entry['data'])
    groups = defaultdict(set)
    for entry in records.get('claims', []):
        claim = entry['data']
        for affiliation in affiliations.get(claim.get('agent_id'), []):
            for passage_id in claim.get('passage_ids', []):
                passage = passages.get(passage_id)
                if passage is None:
                    continue
                key = (str(passage.get('work', '')), str(affiliation.get('tradition', '')),
                       str(affiliation.get('review_status', 'unclassified')),
                       str(claim.get('review_status', 'unclassified')),
                       str(claim.get('attribution_kind', 'unclassified')))
                groups[key].add(claim['id'])
    cross_tab = [{'work': key[0], 'tradition': key[1], 'affiliation_status': key[2],
                  'claim_status': key[3], 'attribution_kind': key[4], 'claim_count': len(ids)}
                 for key, ids in sorted(groups.items())]
    return {'schema_version': 'i1-private-1', 'canonical_promotion': False,
            'rows': rows, 'coverage_by_work': coverage, 'affiliation_claim_coverage': cross_tab,
            'note': ('Local review only. Affiliation counts associate a claim with its agent; '
                     'they do not establish temporal coverage or official doctrine. Canon listings '
                     'do not prove textual alignment or independent scholarly review.')}


def write_private(name, data):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,100}[.]json', name):
        raise ValueError('invalid_private_report_name')
    parent = ROOT / '.local'
    if parent.is_symlink():
        raise ValueError('unsafe_private_directory')
    parent.mkdir(mode=0o700, exist_ok=True)
    folder = parent / 'i1'
    if folder.is_symlink():
        raise ValueError('unsafe_private_directory')
    folder.mkdir(mode=0o700, exist_ok=True)
    st = folder.stat()
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077:
        raise ValueError('unsafe_private_directory')
    target = folder / name
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(target, flags, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as out:
        json.dump(data, out, ensure_ascii=False, indent=2, sort_keys=True)
        out.write('\n')
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description='Validate the pinned D-3 ZIP without a database connection.')
    parser.add_argument('command', choices=('validate', 'dry-run', 'ingest-preview'))
    parser.add_argument('archive', type=Path)
    parser.add_argument('--output', type=Path, help='Create a new public aggregate JSON; no overwrite')
    parser.add_argument('--private-trace', metavar='NAME.json', help='Create a local-only 0600 provenance and coverage report under .local/i1')
    parser.add_argument('--quarantine-output', type=Path, help='Create a new aggregate/hash-only quarantine summary')
    args = parser.parse_args(argv)
    report, records = validate_archive(args.archive)
    report['mode'] = args.command
    report['operation'] = {'validate': 'integrity_and_semantic_validation',
                           'dry-run': 'validation_with_quarantine_plan',
                           'ingest-preview': 'validation_with_virtual_mapping_only'}[args.command]
    report['database_write'] = False
    report['canonical_promotion'] = False
    if args.command == 'ingest-preview':
        report['preview'] = {'kind': 'virtual_mapping_only', 'source_ids_converted_to_version_ids': False,
                             'all_unmapped_records_quarantined': True, 'sql_generated': False}
    if args.private_trace:
        if report['status'] != 'pass':
            print('Private trace requires a valid pinned archive.', file=sys.stderr)
            return 1
        try:
            write_private(args.private_trace, private_review(records))
        except (OSError, ValueError, KeyError, TypeError):
            print('Cannot safely create private trace; no existing file was overwritten.', file=sys.stderr)
            return 2
    if args.quarantine_output:
        if report['status'] != 'pass':
            print('Quarantine summary requires a valid pinned archive.', file=sys.stderr)
            return 1
        summary = {key: report[key] for key in ('schema_version', 'archive_sha256',
                   'baseline_sha256', 'dispositions', 'quarantine_reasons', 'records')}
        summary.update({'status': 'pass', 'database_write': False, 'canonical_promotion': False})
        try:
            with args.quarantine_output.open('x', encoding='utf-8') as out:
                json.dump(summary, out, ensure_ascii=False, indent=2, sort_keys=True)
                out.write('\n')
        except OSError:
            print('Cannot create quarantine summary; no existing file was overwritten.', file=sys.stderr)
            return 2
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + '\n'
    if args.output:
        try:
            with args.output.open('x', encoding='utf-8') as out:
                out.write(payload)
        except OSError:
            print('Cannot create report; no existing file was overwritten.', file=sys.stderr)
            return 2
    else:
        sys.stdout.write(payload)
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
