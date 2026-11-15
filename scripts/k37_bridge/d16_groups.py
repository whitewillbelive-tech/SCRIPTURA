"""Read-only D16 group references with exact passage/corpus boundaries.

Only bounded aggregates and opaque keys may be emitted as diagnostics. Raw
source IDs and values stay in memory. No text, relationship assertion, or
rights grant is inferred from group membership.
"""
from collections import Counter, defaultdict
import re
from k2_bridge.receipt import _K2_BOOKS, _valid_bible_reference, _d12_passage_map
from j2_bridge import candidate_readonly as base

_TOKEN = object()
_SCHEME = re.compile(r'^d16_scheme_[1-9][0-9]{0,3}$')
_CORPUS = re.compile(r'^(Bible|Quran)_[1-9][0-9]{0,3}$')
_KEY = re.compile(r'^d(?:[1-9][0-9]{0,2}):claims:[1-9][0-9]{0,6}$')
_BOOK_CHAPTER = re.compile(r'^(?:[1-3]\s*)?(?:'+_K2_BOOKS+r')\s+\d{1,3}$', re.I)
_BOOK_LIST = re.compile(r'^(?:[1-3]\s*)?(?:'+_K2_BOOKS+r')\s+\d{1,3}:\d{1,3}(?:\s*[,–-]\s*\d{1,3})+$', re.I)


def safe_d16_passage(value):
    """Validate a safe opaque scheme and conventional reference, without I/O."""
    if not isinstance(value, dict):
        return None
    corpus, scheme, ref = (value.get(k) for k in ('corpus', 'scheme', 'reference'))
    if not all(isinstance(x, str) for x in (corpus, scheme, ref)):
        return None
    cm = _CORPUS.fullmatch(corpus)
    if not cm or not _SCHEME.fullmatch(scheme) or len(ref) > 100:
        return None
    if cm.group(1) == 'Bible':
        valid = (_valid_bible_reference(ref) or bool(_BOOK_CHAPTER.fullmatch(ref)) or bool(_BOOK_LIST.fullmatch(ref)))
        if not valid or base._QURAN_PREFIX.match(ref):
            return None
    elif not base._QURAN_REF.fullmatch(ref):
        return None
    return {'corpus': corpus, 'scheme': scheme, 'reference': ref, 'alignment_status': 'pending'}


def build_passage_map(layers):
    """Return private ID→safe reference map; never print or expose its keys."""
    if not hasattr(layers, 'items'):
        raise ValueError('d16_passages_invalid')
    entries = []
    for stage, tables in layers.items():
        if not isinstance(stage, str) or not hasattr(tables, 'get'):
            continue
        for item in tables.get('passages', []):
            value = item.get('value') if isinstance(item, dict) else None
            if isinstance(value, dict) and isinstance(value.get('id'), str):
                entries.append((stage, value))
    corpora = sorted({r['corpus'] for _, r in entries if isinstance(r.get('corpus'), str)})
    schemes = sorted({r['reference_scheme'] for _, r in entries if isinstance(r.get('reference_scheme'), str)})
    by_corpus = {}
    counts = Counter()
    for raw in corpora:
        lower = raw.casefold()
        kind = 'Bible' if 'bible' in lower and 'quran' not in lower else ('Quran' if 'quran' in lower and 'bible' not in lower else None)
        if kind:
            counts[kind] += 1
            by_corpus[raw] = f'{kind}_{counts[kind]}'
    scheme_map = {raw: f'd16_scheme_{i+1}' for i, raw in enumerate(schemes)}
    legacy = _d12_passage_map(layers) if 'd12' in layers else {}
    values = defaultdict(list)
    for stage, row in entries:
        if stage == 'd12':
            safe = legacy.get(row['id'])
        else:
            safe = safe_d16_passage({'corpus': by_corpus.get(row.get('corpus')), 'scheme': scheme_map.get(row.get('reference_scheme')), 'reference': row.get('reference')})
        values[row['id']].append(safe)
    return {ident: items[0] for ident, items in values.items() if all(item == items[0] for item in items)}


class D16GroupIndex:
    __slots__ = ('__entries', '__summary')
    def __init__(self, token, entries, summary):
        if token is not _TOKEN:
            raise ValueError('d16_groups_invalid')
        self.__entries = entries
        self.__summary = summary
    def __repr__(self):
        return '<D16GroupIndex redacted>'
    def entries(self):
        return [dict(x, claim_keys=list(x['claim_keys'])) for x in self.__entries]
    def summary(self):
        return dict(self.__summary)


def build_d16_index(layers, records, groups):
    """Partition each verified set by exact referenced passage; never merge.

    A group is accepted only if every claimed member and passage resolves and
    every member independently intersects the referenced passages. For each
    resulting exact address, only members actually linked to that passage are
    included. Thus multi-corpus comparisons remain separate candidates.
    """
    try:
        if not hasattr(layers, 'items') or not isinstance(records, list) or not isinstance(groups, list):
            raise ValueError('d16_groups_invalid')
        valid_keys = {r.get('key') for r in records if isinstance(r, dict) and isinstance(r.get('key'), str) and _KEY.fullmatch(r['key'])}
        claim_ids = defaultdict(list)
        for stage, tables in layers.items():
            if not isinstance(stage, str) or not hasattr(tables, 'get'):
                continue
            for item in tables.get('claims', []):
                row = item.get('value') if isinstance(item, dict) else None
                line = item.get('line') if isinstance(item, dict) else None
                if isinstance(row, dict) and isinstance(row.get('id'), str) and type(line) is int and line > 0:
                    key = f'{stage}:claims:{line}'
                    if key in valid_keys:
                        claim_ids[row['id']].append((key, row))
        passage_map = build_passage_map(layers)
        entries = []
        line_counts = Counter(entry.get('line') for entry in groups
                              if isinstance(entry, dict) and type(entry.get('line')) is int)
        summary = {'input_groups': len(groups), 'validated_groups': 0, 'pending_groups': 0, 'partitioned_entries': 0, 'claim_refs': 0, 'passage_refs': 0}
        for entry in groups:
            row = entry.get('value') if isinstance(entry, dict) else None
            line = entry.get('line') if isinstance(entry, dict) else None
            if not isinstance(row, dict) or type(line) is not int or line <= 0 or line_counts[line] != 1:
                summary['pending_groups'] += 1
                continue
            ids = row.get('claim_ids')
            passage_ids = row.get('passage_ids') or ([row['passage_id']] if isinstance(row.get('passage_id'), str) else [])
            if (not isinstance(ids, list) or len(ids) < 2 or not all(isinstance(x, str) and x for x in ids)
                or len(set(ids)) != len(ids) or not isinstance(passage_ids, list) or not passage_ids
                or not all(isinstance(x, str) and x for x in passage_ids) or len(set(passage_ids)) != len(passage_ids)):
                summary['pending_groups'] += 1
                continue
            if any(len(claim_ids.get(x, [])) != 1 for x in ids) or any(not passage_map.get(x) for x in passage_ids):
                summary['pending_groups'] += 1
                continue
            claims = [claim_ids[x][0] for x in ids]
            if any(not isinstance(r.get('passage_ids'), list)
                   or not all(isinstance(p, str) and p for p in r['passage_ids'])
                   or not set(r['passage_ids']).intersection(passage_ids) for _, r in claims):
                summary['pending_groups'] += 1
                continue
            # Resolution alone does not establish that a passage belongs to
            # this comparison. Require an explicit member link for *each*
            # listed address, or retain the whole group as pending.
            if any(not any(pid in r['passage_ids'] for _, r in claims)
                   for pid in passage_ids):
                summary['pending_groups'] += 1
                continue
            summary['validated_groups'] += 1
            summary['claim_refs'] += len(ids)
            summary['passage_refs'] += len(passage_ids)
            for pid in passage_ids:
                member_keys = [key for key, r in claims if pid in r['passage_ids']]
                safe = passage_map[pid]
                entries.append({'key': f'd16:comparison_sets:{line}', 'corpus': safe['corpus'], 'scheme': safe['scheme'], 'reference': safe['reference'], 'claim_keys': member_keys, 'status': 'recorded_unverified'})
        summary['partitioned_entries'] = len(entries)
        return D16GroupIndex(_TOKEN, entries, summary)
    except Exception:
        raise ValueError('d16_groups_invalid') from None


def get_d16_sets(dataset):
    if not isinstance(dataset, dict):
        return []
    index = dataset.get('_d16_group_index')
    return index.entries() if type(index) is D16GroupIndex else []


def d16_summary(dataset):
    if not isinstance(dataset, dict):
        return {}
    index = dataset.get('_d16_group_index')
    return index.summary() if type(index) is D16GroupIndex else {}
