"""Read-only receipt for the two pinned private Work archives.

Research data remains in memory and errors are fixed codes. Neither the source
archives nor their private identifiers are included in public diagnostics.
"""
import hashlib
import hmac
import os
from zipfile import ZipFile
from io import BytesIO
from collections import Counter

import k37_work_archive_compat as audit
from i3_bridge import d6 as prior
from j2_bridge import candidate_readonly as base
from k2_bridge import receipt as k2
from k13_bridge.local_candidate import prepare_local_candidate_index

_TABLES = ('sources', 'editions', 'locators', 'passages', 'claims', 'evidence', 'rights', 'relationships', 'source_access_events')
_EXPECTED = {'d13': {'sources': 47, 'claims': 47, 'passages': 19},
             'd14': {'sources': 96, 'claims': 98, 'passages': 45}}


def _tables(z, stage):
    errors = Counter()
    out = {}
    names = set(z.namelist())
    for table in _TABLES:
        path = f'{stage}/records/{table}.jsonl'
        out[table] = prior._records(z, path, errors) if path in names else []
    if errors or any(len(out[t]) != n for t, n in _EXPECTED[stage].items()):
        raise base.CandidateError('archive_invalid')
    # Preserve the original ZIP while supporting either bibliographic field.
    fixed = []
    for item in out['sources']:
        row = dict(item['value'])
        if not row.get('creator') and isinstance(row.get('author'), str):
            row['creator'] = row['author']
        fixed.append({'line': item['line'], 'value': row})
    out['sources'] = fixed
    return out


def _quarantine_increment(prior_rows, tables):
    """Return a filtered copy and aggregate findings; never mutate inputs."""
    masks = {}
    findings = audit.reference_assessment(
        prior_rows,
        {table: [item['value'] for item in tables[table]] for table in audit.TABLES},
        quarantine_positions=masks)
    filtered = dict(tables)
    for table, positions in masks.items():
        filtered[table] = [row for pos, row in enumerate(tables[table])
                           if pos not in positions]
    return filtered, findings


def _extend_prior(prior_rows, accepted_tables):
    """Make only the accepted increment visible to the next validation."""
    result = {table: dict(stages) for table, stages in prior_rows.items()}
    for table in audit.TABLES:
        stages = result.setdefault(table, {})
        stage = '__accepted_increment__'
        while stage in stages:
            stage += '_'
        stages[stage] = [item['value'] for item in accepted_tables[table]]
    return result


def _receipt_counts(input_counts, d13, d14):
    """Distinguish archive row totals from rows accepted into the projection."""
    return {'d13_sources': len(d13['sources']), 'd13_claims': len(d13['claims']),
            'd14_sources': len(d14['sources']), 'd14_claims': len(d14['claims']),
            'd14_passages': len(d14['passages']), 'input_counts': input_counts}


def load_d16_archive(base_path, delta_path):
    """Build a private D16 projection from both user-selected local archives."""
    try:
        base_path = os.fspath(base_path)
        delta_path = os.fspath(delta_path)
        assessment = audit.audit(base_path, delta_path)
        if not (assessment.get('d13_anchor_verified') is True and
                assessment.get('d14_d16_anchor_verified') is True and
                assessment.get('lineage_expected_verified') is True and
                assessment.get('d13_expected_counts_verified') is True and
                assessment.get('file_hashes_checked') == 45):
            raise base.CandidateError('archive_invalid')
        d13 = audit.read_local_unchanged(base_path)
        delta = audit.read_local_unchanged(delta_path)
        if not (hmac.compare_digest(hashlib.sha256(d13).hexdigest(), audit.D13_SHA) and
                hmac.compare_digest(hashlib.sha256(delta).hexdigest(), audit.DELTA_SHA)):
            raise base.CandidateError('archive_changed')
        with audit.secure_zip(d13) as z:
            children = [i.filename for i in z.infolist() if i.filename.startswith('baseline/') and i.filename.endswith('.zip')]
            if len(children) != 1:
                raise base.CandidateError('baseline_invalid')
            d12 = z.read(children[0])
            d13_tables = _tables(z, 'd13')
        with audit.secure_zip(delta) as z:
            d14_tables = _tables(z, 'd14')
            errors = Counter()
            groups = prior._records(z, 'd16/records/comparison_sets.jsonl', errors)
            review_tables = {table: prior._records(z, f'{stage}/records/{table}.jsonl', errors)
                             for stage, table in (('d15', 'claim_review_events'),
                                                  ('d15', 'd12_field_audit'),
                                                  ('d15', 'source_duplicate_review'),
                                                  ('d15', 'relation_evidence'),
                                                  ('d16', 'relationships'),
                                                  ('d16', 'rights_evidence'))}
            if errors or len(groups) != 80:
                raise base.CandidateError('archive_invalid')
        input_counts = {stage: {table: len(rows) for table, rows in tables.items()}
                        for stage, tables in (('d13', d13_tables), ('d14', d14_tables))}
        old = k2.load_k2_archive(d12)
        if old.get('dataset') != 'D12' or len(old.get('records', [])) != 621:
            raise base.CandidateError('baseline_invalid')
        layers, _ = k2._read_layers(d12)
        prior_rows, _ = audit.old_layers(d12)
        # Validate each increment against the accepted earlier lineage. An
        # invalid D13 row must not satisfy a D14 dependency, and intact D12
        # and sibling records remain available.
        d13_tables, d13_findings = _quarantine_increment(prior_rows, d13_tables)
        layers['d13'] = d13_tables
        d14_tables, d14_findings = _quarantine_increment(
            _extend_prior(prior_rows, d13_tables), d14_tables)
        layers['d14'] = d14_tables
        from k37_bridge.review_checks import validate_review_refs, verified_rights_actions
        review_summary = validate_review_refs(layers, review_tables)
        rights_actions, rights_summary = verified_rights_actions(layers, review_tables['rights_evidence'])
        layers['d16'] = {'rights_actions': rights_actions}
        projected = base._build_projection(layers)
        additions = [r for r in projected if r.get('stage') in ('d13', 'd14') and r.get('record_kind') in ('source', 'claim')]
        expected_additions = sum(len(layers[s][t]) for s in ('d13', 'd14')
                                 for t in ('sources', 'claims'))
        if len(additions) != expected_additions or len({r.get('key') for r in additions}) != expected_additions:
            raise base.CandidateError('archive_invalid')
        from k37_bridge.d16_groups import build_passage_map
        safe_passages = build_passage_map(layers)
        claim_rows = {f'{stage}:claims:{item["line"]}': item['value']
                      for stage in ('d13', 'd14') for item in layers[stage]['claims']}
        for record in additions:
            claim = claim_rows.get(record.get('key'))
            if not claim:
                continue
            ids = claim.get('passage_ids')
            record['passages'] = [safe_passages[x] for x in ids
                                  if isinstance(x, str) and safe_passages.get(x)] if isinstance(ids, list) else []
            first = record['passages'][0] if record['passages'] else {}
            record['passage_corpus'] = first.get('corpus')
            record['passage_scheme'] = first.get('scheme')
            record['passage_reference'] = first.get('reference')
        result = dict(old)
        result['dataset'] = 'D16'
        result['records'] = list(old['records']) + additions
        # New restrictions also narrow the previously sealed D12 statement
        # and tradition indices. This can remove values but never add them.
        from k37_bridge.real_content import apply_k2_review_restrictions
        result['_k2_summary_index'], result['_k2_tradition_index'] = apply_k2_review_restrictions(
            layers, result['records'], result.get('_k2_summary_index'), result.get('_k2_tradition_index'))
        result['_local_candidate_index'] = prepare_local_candidate_index(result, layers)
        from k37_bridge.real_content import build_content_index
        result['_d16_content_index'] = build_content_index(layers, additions, result['_local_candidate_index'])
        result['counts'] = dict(old.get('counts', {}))
        result['counts']['by_stage'] = dict(result['counts'].get('by_stage', {}))
        for stage in ('d13', 'd14'):
            result['counts']['by_stage'][stage] = {t: len(rows) for t, rows in layers[stage].items()}
        result['d16_receipt'] = _receipt_counts(input_counts, d13_tables, d14_tables)
        result['d16_receipt'].update({'comparison_sets': len(groups),
                                     'quarantined': d13_findings['quarantined'] + d14_findings['quarantined'],
                                     'd13_quarantined': d13_findings['quarantined'],
                                     'd14_quarantined': d14_findings['quarantined'],
                                     'checksums_verified': 45,
                                     'rights_action_summary': rights_summary,
                                     'review_summary': review_summary})
        # The D16 group builder attaches a separately sealed address index.
        from k37_bridge.d16_groups import build_d16_index
        result['_d16_group_index'] = build_d16_index(layers, result['records'], groups)
        if (not hmac.compare_digest(hashlib.sha256(audit.read_local_unchanged(base_path)).hexdigest(), audit.D13_SHA)
                or not hmac.compare_digest(hashlib.sha256(audit.read_local_unchanged(delta_path)).hexdigest(), audit.DELTA_SHA)):
            raise base.CandidateError('archive_changed')
        return result
    except base.CandidateError as exc:
        code = exc.args[0] if len(exc.args) == 1 and exc.args[0] in ('archive_invalid', 'archive_changed', 'baseline_invalid') else 'archive_invalid'
        raise base.CandidateError(code) from None
    except Exception:
        raise base.CandidateError('archive_invalid') from None
