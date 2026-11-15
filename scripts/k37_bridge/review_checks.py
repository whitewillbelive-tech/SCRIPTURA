"""Read-only D15/D16 review reference assessment.

Only bounded counts leave this module. Input IDs and values stay in memory.
Recorded review events, source links and relationship labels do not establish
formal adoption, direct rebuttal, rights permission, or scholarly review.
"""
from collections import Counter, defaultdict


# review-table → (reference field, expected table, required)
_SPECS = {
    'claim_review_events': (('baseline_claim_id', 'claims', True),
                            ('baseline_source_id', 'sources', False),
                            ('baseline_locator_id', 'locators', False)),
    'd12_field_audit': (('baseline_claim_id', 'claims', True),
                        ('baseline_source_id', 'sources', False)),
    'source_duplicate_review': (('new_source_id', 'sources', True),
                                ('prior_source_id', 'sources', True)),
    'relation_evidence': (('baseline_relation_id', 'relationships', True),
                          ('baseline_subject_claim_id', 'claims', True),
                          ('baseline_object_claim_id', 'claims', True)),
    'relationships': (('baseline_relation_id', 'relationships', False),
                      ('subject_id', 'claims', True),
                      ('object_id', 'claims', True),
                      ('locator_id', 'locators', False)),
    'rights_evidence': (('source_id', 'sources', True),
                        ('edition_id', 'editions', True)),
}


def _row(entry):
    if not isinstance(entry, dict):
        return None
    val = entry.get('value')
    return val if isinstance(val, dict) else entry


def _indexes(layers):
    # Identical historical rows can recur in nested snapshots; conflicting
    # identities, including cross-table conflicts, are never silently chosen.
    lookup = defaultdict(list)
    for _, tables in layers.items():
        if not hasattr(tables, 'items'):
            continue
        for table, entries in tables.items():
            if not isinstance(table, str):
                continue
            for entry in entries:
                row = _row(entry)
                ident = row.get('id') if isinstance(row, dict) else None
                if isinstance(ident, str) and ident:
                    lookup[ident].append((table, row))
    unique = {}
    for ident, occurrences in lookup.items():
        table, row = occurrences[0]
        if all(t == table and r == row for t, r in occurrences):
            unique[ident] = (table, row)
    return unique, len(lookup) - len(unique)


def validate_review_refs(layers, tables):
    """Assess references/obvious source-chain conflicts, returning counts only.

    Missing optional fields are counted separately from unresolved references;
    no raw identifiers, free text, per-row data or theological decisions leave
    this function. Only explicitly modelled schemas are checked.
    """
    try:
        if not hasattr(layers, 'items') or not isinstance(tables, dict):
            raise ValueError('review_refs_invalid')
        index, ambiguous = _indexes(layers)
        out = {'ambiguous_baseline_ids': ambiguous}
        for table, specs in _SPECS.items():
            entries = tables.get(table, [])
            if not isinstance(entries, (list, tuple)):
                raise ValueError('review_refs_invalid')
            c = Counter(rows=len(entries))
            for item in entries:
                row = _row(item)
                if not isinstance(row, dict):
                    c['malformed'] += 1
                    continue
                resolved = {}
                bad = False
                for field, expected, required in specs:
                    value = row.get(field)
                    if value is None or value == '':
                        c['missing_required' if required else 'missing_optional'] += 1
                        bad |= required
                        continue
                    if not isinstance(value, str):
                        c['unresolved'] += 1
                        bad = True
                        continue
                    hit = index.get(value)
                    if not hit or hit[0] != expected:
                        c['unresolved'] += 1
                        bad = True
                        continue
                    c['resolved'] += 1
                    resolved[field] = hit[1]
                conflict = False
                if table in ('claim_review_events', 'd12_field_audit'):
                    claim = resolved.get('baseline_claim_id')
                    if claim:
                        for field, expected in (('baseline_source_id', claim.get('source_id')),
                                                ('baseline_locator_id', claim.get('source_locator_id') or claim.get('locator_id'))):
                            if field in resolved and row.get(field) != expected:
                                conflict = True
                    locator = resolved.get('baseline_locator_id')
                    if locator and 'baseline_source_id' in resolved and locator.get('source_id'):
                        conflict |= locator.get('source_id') != row.get('baseline_source_id')
                if table in ('relation_evidence', 'relationships'):
                    relation = resolved.get('baseline_relation_id')
                    if relation:
                        subject_field = 'baseline_subject_claim_id' if table == 'relation_evidence' else 'subject_id'
                        object_field = 'baseline_object_claim_id' if table == 'relation_evidence' else 'object_id'
                        for field, expected in ((subject_field, relation.get('subject_id') or relation.get('from_claim_id')),
                                                (object_field, relation.get('object_id') or relation.get('to_claim_id'))):
                            if expected and field in resolved and row.get(field) != expected:
                                conflict = True
                if table == 'source_duplicate_review' and all(field in resolved for field in ('new_source_id', 'prior_source_id')):
                    conflict |= row.get('new_source_id') == row.get('prior_source_id')
                if table == 'rights_evidence' and 'edition_id' in resolved and 'source_id' in resolved:
                    conflict |= resolved['edition_id'].get('source_id') != row.get('source_id')
                if conflict:
                    c['chain_conflicts'] += 1
                    bad = True
                c['pending' if bad else 'references_valid'] += 1
            for key in ('rows','resolved','missing_required','missing_optional','unresolved','chain_conflicts','malformed','pending','references_valid'):
                out[f'{table}_{key}'] = int(c[key])
        return out
    except Exception:
        raise ValueError('review_refs_invalid') from None
