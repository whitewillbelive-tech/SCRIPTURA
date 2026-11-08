"""Pinned D10 read-only receipt; research values never go to diagnostic output.

The D10 source additions and the display ledger stay quarantined.  The latter
contains a conditional candidate, not independently verified display rights.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import io
import os
import re
from zipfile import ZipFile

from i3_bridge import d6 as prior
from j2_bridge import candidate_readonly as base
from j3_bridge.candidate_archive import load_versioned_archive
from j3_bridge.d9_validation import TABLE_COUNTS
from j3_bridge.private_io import read_checked_d8_layers
from k11_bridge.metadata import prepare_private_candidates

D10_SHA = '0420be8eee136cbef3559caac23436c5e4fcbe9b8602db77010a35343fc7bb9e'
_D10_TABLES = {'sources': 16, 'editions': 5, 'locators': 16,
               'rights': 45, 'rights_actions': 36, 'review_queue': 11}
_STATUS = ('candidate_visible_local', 'metadata_candidate', 'unknown', 'unmapped')
_GROUPS = frozenset(('bibliography', 'own_summary', 'short_quote', 'full_text', 'private_link'))


def _one_suffix(z, suffix):
    matches = [n for n in z.namelist() if n.endswith(suffix) and not n.endswith('/')]
    if len(matches) != 1:
        raise base.CandidateError('archive_invalid')
    return matches[0]


def _manifest_counts(z, manifest_name):
    """Verify a checksum list in memory, returning only bounded counts."""
    names = {i.filename for i in z.infolist() if not i.is_dir()}
    try:
        lines = z.read(manifest_name).decode('utf-8').splitlines()
    except (KeyError, UnicodeError):
        raise base.CandidateError('archive_invalid') from None
    result = {'entries': len(lines), 'matched': 0, 'missing': 0, 'invalid': 0}
    seen = set()
    for line in lines:
        match = re.fullmatch(r'([0-9a-f]{64})  (.+)', line)
        if not match:
            result['invalid'] += 1
            continue
        expected, target = match.groups()
        hits = [name for name in names if name == target or name.endswith('/' + target)]
        if not hits:
            result['missing'] += 1
        elif len(hits) != 1 or hits[0] in seen or hits[0] == manifest_name:
            result['invalid'] += 1
        else:
            seen.add(hits[0])
            if prior._sha(z.read(hits[0])) == expected:
                result['matched'] += 1
            else:
                result['invalid'] += 1
    result['all_members_covered'] = seen == names - {manifest_name}
    return result


def _ledger_summary(entries):
    if not isinstance(entries, list):
        raise base.CandidateError('archive_invalid')
    seen, counts = set(), Counter()
    for item in entries:
        if not isinstance(item, dict) or not isinstance(item.get('value'), dict):
            raise base.CandidateError('archive_invalid')
        value = item['value']
        entity, group, status = value.get('entity_id'), value.get('field_group'), value.get('decision')
        if not isinstance(entity, str) or not entity or group not in _GROUPS or status not in _STATUS:
            raise base.CandidateError('archive_invalid')
        if (entity, group) in seen:
            raise base.CandidateError('archive_invalid')
        seen.add((entity, group)); counts[status] += 1
    result = {name: counts[name] for name in _STATUS}
    result['total'] = len(entries)
    return result


def _ledger_references(entries, layers):
    """Validate entity kinds, complete field groups and the one target chain."""
    index = defaultdict(list)
    for tables in layers.values():
        for table, rows in tables.items():
            for item in rows:
                value = item.get('value') if isinstance(item, dict) else None
                if isinstance(value, dict) and isinstance(value.get('id'), str):
                    index[value['id']].append((table, value))
    expected = {'source': 'sources', 'edition': 'editions', 'locator': 'locators', 'claim': 'claims'}
    groups, issues, candidate = defaultdict(set), 0, []
    for item in entries:
        row = item['value']; ident = row.get('entity_id'); kind = row.get('entity_kind')
        hits = index.get(ident, [])
        if kind not in expected or len(hits) != 1 or hits[0][0] != expected.get(kind):
            issues += 1
        groups[ident].add(row.get('field_group'))
        if row.get('decision') == 'candidate_visible_local':
            candidate.append(row)
    groups_ok = all(v == _GROUPS for v in groups.values())
    chain_ok = False
    if len(candidate) == 1:
        row = candidate[0]
        src = index.get(row.get('entity_id'), [])
        ed = index.get(row.get('source_edition_id'), [])
        loc = index.get(row.get('source_locator_id'), [])
        fields = row.get('exact_display_field')
        chain_ok = bool(row.get('entity_kind') == 'source' and row.get('field_group') == 'bibliography'
                        and isinstance(fields, list) and len(fields) == 2
                        and set(fields) == {'title', 'creator'}
                        and row.get('other_subfields_default_hidden') is True
                        and len(src) == len(ed) == len(loc) == 1
                        and src[0][0] == 'sources' and ed[0][0] == 'editions' and loc[0][0] == 'locators'
                        and ed[0][1].get('source_id') == row.get('entity_id')
                        and loc[0][1].get('edition_id') == row.get('source_edition_id'))
    return {'entity_count': len(groups), 'incomplete_groups': sum(v != _GROUPS for v in groups.values()),
            'invalid_entity_references': issues, 'groups_complete': groups_ok, 'candidate_chain_valid': chain_ok}


def _nonempty_text(value):
    return value.strip().casefold() if isinstance(value, str) and value.strip() else ''


def _source_duplicate_counts(old, new):
    """Return counts only; no real values or identifiers are retained."""
    if not isinstance(old, list) or not isinstance(new, list):
        raise base.CandidateError('archive_invalid')
    if any(not isinstance(x, dict) for x in old + new):
        raise base.CandidateError('archive_invalid')
    result = {}
    for field in ('id', 'title', 'doi', 'url'):
        before = {_nonempty_text(v.get(field)) for v in old} - {''}
        values = [_nonempty_text(v.get(field)) for v in new]
        values = [v for v in values if v]
        result['cross_' + field] = sum(v in before for v in values)
        result['within_' + field] = len(values) - len(set(values))
    if result['cross_id'] or result['within_id'] or any(not _nonempty_text(v.get('id')) for v in new):
        raise base.CandidateError('archive_invalid')
    return result


def _linkage_counts(layers, new):
    """Count resolved/ambiguous references without returning any source values."""
    index = defaultdict(list)
    for tables in layers.values():
        for table, entries in tables.items():
            for entry in entries:
                value = entry.get('value') if isinstance(entry, dict) else None
                if isinstance(value, dict) and isinstance(value.get('id'), str) and value['id']:
                    index[value['id']].append(table)
    result = {}
    for table, field, target in (('editions', 'source_id', 'sources'),
                                  ('locators', 'edition_id', 'editions'),
                                  ('locators', 'source_id', 'sources'),
                                  ('rights', 'edition_id', 'editions'),
                                  ('rights_actions', 'source_id', 'sources'),
                                  ('review_queue', 'baseline_target_id', None)):
        present = resolved = 0
        for item in new[table]:
            value = item['value']; target_id = value.get(field)
            if not target_id:
                continue
            present += 1
            hits = index.get(target_id, [])
            if len(hits) == 1 and (target is None or hits[0] == target):
                resolved += 1
        result[table + '_' + field + '_present'] = present
        result[table + '_' + field + '_resolved'] = resolved
    return result


def _read_d10(blob):
    errors = Counter()
    archive = prior._safe_archive(blob, errors)
    if archive is None:
        raise base.CandidateError('archive_invalid')
    with archive as d10:
        manifests = [n for n in d10.namelist() if 'sha256' in n.lower() and not n.endswith('/')]
        primary = [n for n in manifests if len(d10.read(n).splitlines()) == 38]
        secondary = [n for n in manifests if len(d10.read(n).splitlines()) == 8]
        if len(primary) != 1 or len(secondary) != 1:
            raise base.CandidateError('archive_invalid')
        primary_summary = _manifest_counts(d10, primary[0])
        secondary_summary = _manifest_counts(d10, secondary[0])
        if primary_summary != {'entries': 38, 'matched': 38, 'missing': 0, 'invalid': 0, 'all_members_covered': True}:
            raise base.CandidateError('archive_invalid')
        baseline = d10.read(_one_suffix(d10, '/SCRIPTURA_D9_RESEARCH.zip'))
        original = load_versioned_archive(baseline)
        if original.get('dataset') != 'D9' or len(original.get('records', [])) != 528:
            raise base.CandidateError('baseline_invalid')
        with ZipFile(io.BytesIO(baseline)) as d9:
            with ZipFile(io.BytesIO(d9.read('baseline/SCRIPTURA_D8_RESEARCH.zip'))) as d8:
                snapshot = read_checked_d8_layers(d8)
            if snapshot.error_count:
                raise base.CandidateError('baseline_invalid')
            layers = snapshot.layers
            layers['d9'] = {table: prior._records(d9, 'd9/records/' + table + '.jsonl', errors)
                            for table in TABLE_COUNTS}
        new = {table: prior._records(d10, _one_suffix(d10, '/records/' + table + '.jsonl'), errors)
               for table in _D10_TABLES}
        if errors or any(len(new[table]) != count for table, count in _D10_TABLES.items()):
            raise base.CandidateError('archive_invalid')
        ledger = prior._records(d10, _one_suffix(d10, '/DISPLAY_ELIGIBILITY.jsonl'), errors)
        summary = _ledger_summary(ledger)
        if errors or summary != {'candidate_visible_local': 1, 'metadata_candidate': 8,
                                 'unknown': 751, 'unmapped': 510, 'total': 1270}:
            raise base.CandidateError('archive_invalid')
        old_sources = [item['value'] for tables in layers.values() for item in tables.get('sources', [])]
        duplicate_counts = _source_duplicate_counts(old_sources, [item['value'] for item in new['sources']])
        layers['d10'] = new
        references = _ledger_references(ledger, layers)
        if references != {'entity_count': 254, 'incomplete_groups': 0, 'invalid_entity_references': 0,
                          'groups_complete': True, 'candidate_chain_valid': True}:
            raise base.CandidateError('archive_invalid')
        links = _linkage_counts(layers, new)
        # Do not mix new sources into browse results or infer a single work from
        # matching title/URL/DOI. All prior rows remain byte-for-byte projected
        # as returned by the validated D9 loader.
        result = dict(original)
        result['dataset'] = 'D10'
        # Keep unverified input opaque and in memory, solely for a separately
        # configured independent verifier. It is never an HTTP response or
        # grant. No real verifier is configured in the application yet.
        result['_private_metadata_candidates'] = prepare_private_candidates(result, layers)
        result['visibility_summary'] = summary
        result['d10_receipt'] = {'source_count': len(new['sources']),
                                 'quarantined_source_count': len(new['sources']),
                                 'duplicate_counts': duplicate_counts,
                                 'linkage_counts': links,
                                 'ledger_reference_counts': references,
                                 'primary_manifest': primary_summary,
                                 'secondary_manifest': secondary_summary,
                                 'conditional_candidate_count': 1,
                                 'effective_visible_fields': 0}
        result['counts'] = dict(original['counts'])
        result['counts']['d10'] = {k: len(v) for k, v in new.items()}
        result['counts']['by_stage'] = dict(original['counts'].get('by_stage', {}))
        result['counts']['by_stage']['d10'] = result['counts']['d10'].copy()
        result['unmapped_summary'] = dict(original['unmapped_summary'])
        result['unmapped_summary']['d10'] = {k: {'input_count': len(v), 'mapping': 'unmapped'} for k, v in new.items()}
        return result


def load_k1_archive(path):
    """Fixed D8, D9, or D10 only. All errors use non-sensitive fixed codes."""
    try:
        if isinstance(path, bytes):
            if len(path) > 64 * 1024 * 1024:
                raise base.CandidateError('archive_invalid')
            read = lambda: path
        else:
            location = os.fspath(path)
            if not isinstance(location, str) or location.startswith(('\\\\', '//', '\\/', '/\\')) or re.match(r'^[A-Za-z][A-Za-z0-9+.-]+:', location):
                raise base.CandidateError('archive_not_local')
            read = lambda: prior._bounded_read(path)
        blob = read()
        if prior._sha(blob) != D10_SHA:
            return load_versioned_archive(path)
        result = _read_d10(blob)
        if prior._sha(read()) != D10_SHA:
            raise base.CandidateError('archive_changed')
        return result
    except base.CandidateError as exc:
        allowed = {'archive_invalid', 'archive_not_local', 'archive_not_recognized', 'archive_changed', 'baseline_invalid'}
        code = exc.args[0] if len(exc.args) == 1 and type(exc.args[0]) is str and exc.args[0] in allowed else 'archive_invalid'
        raise base.CandidateError(code) from None
    except Exception:
        raise base.CandidateError('archive_invalid') from None
