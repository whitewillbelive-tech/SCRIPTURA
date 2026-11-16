"""Deterministic evidence dossier from the server's existing safe projection.

The caller must pass only the authenticated in-process ``compare_passages``
result, never data supplied in an HTTP request. This module calls no model,
makes no semantic comparison, and grants no rights or factual status.
"""
import re

_REF = re.compile(r'^(?:base|d[5-9]|d1[0-6]):(claims|sources):[1-9][0-9]{0,6}$')
_FIELDS = frozenset(('recorded_unverified', 'local_input_candidate'))
_METADATA_STATES = frozenset(('recorded_unverified', 'source_confirmed', 'restricted', 'missing_or_unmapped'))
_SAFE_STATUSES = frozenset(('source_confirmed', 'recorded_unverified', 'verified_fields_only',
                            'source_checked', 'unconfirmed', 'unreviewed', 'pending', 'pending_review',
                            'unmapped', 'unknown', 'disputed', 'reviewed', 'individual',
                            'external_criticism', 'official_confirmed', 'not_granted', 'restricted',
                            'verified', 'unverified', 'not_reviewed', 'not_applicable'))
_LIMIT = 100


def _value(value, limit):
    return value if isinstance(value, str) and value.strip() and len(value) <= limit and not any(ord(c) < 32 or ord(c) == 127 for c in value) else None


def _ref(value, table):
    if not isinstance(value, str):
        return None
    match = _REF.fullmatch(value)
    return value if match and match.group(1) == table else None


def _content(row, key, marker, expected_marker, allowed, limit):
    state = row.get(key + '_status')
    if marker != expected_marker or state not in allowed:
        return {'value': None, 'status': 'pending_review'}
    value = _value(row.get(key), limit)
    item = {'value': value, 'status': state if value else 'pending_review'}
    if value and state == 'local_input_candidate':
        item['notice'] = '비공개 연구 입력 · 독립 확인, 비인용 여부 및 재사용 권리 미확인'
    return item


def _metadata(row, key, marker, limit):
    item = row.get('candidate_metadata')
    item = item.get(key) if marker == 'k1.3-local-candidate' and isinstance(item, dict) else None
    if isinstance(item, dict) and item.get('status') in _METADATA_STATES:
        state = item['status']
        value = _value(item.get('value'), limit) if state in ('recorded_unverified', 'source_confirmed') else None
        return {'value': value, 'status': state if value or state in ('restricted', 'missing_or_unmapped') else 'missing_or_unmapped'}
    verified = row.get('verified_metadata')
    if marker == 'k1.1-verified' and isinstance(verified, dict):
        value = _value(verified.get(key), limit)
        if value:
            return {'value': value, 'status': 'source_confirmed'}
    return {'value': None, 'status': 'missing_or_unmapped'}


def _status(value):
    return value if isinstance(value, str) and value in _SAFE_STATUSES else 'unconfirmed'


def build_dossier(comparison, *, source_refs=None):
    """Produce local candidate evidence, never AI-generated analysis.

    Projection markers and each field status are independent gates; they do
    not establish attribution, scholarly review, rights, or publication grants.
    Existing server checks remain the authority for the projection and keys.
    """
    if not isinstance(comparison, dict) or not isinstance(comparison.get('claims'), list):
        raise ValueError('invalid_comparison_projection')
    if source_refs is None:
        source_refs = frozenset()
    if not isinstance(source_refs, (set, frozenset)):
        raise ValueError('invalid_source_refs')
    selected = comparison.get('selected')
    if selected is not None:
        if not isinstance(selected, dict):
            raise ValueError('invalid_comparison_projection')
        selected = {key: _value(selected.get(key), 200) for key in ('corpus', 'scheme', 'reference')}
        if not all(selected.values()):
            raise ValueError('invalid_comparison_projection')
    entries = []
    for row in comparison['claims'] if selected is not None else ():
        if not isinstance(row, dict):
            continue
        ref = _ref(row.get('key'), 'claims')
        if not ref:
            continue
        if len(entries) == _LIMIT:
            break
        source_ref = _ref(row.get('source_key'), 'sources')
        if source_ref not in source_refs:
            source_ref = None
        marker = comparison.get('metadata_projection')
        source = {'ref': source_ref, 'title': _metadata(row, 'source_title', marker, 1024),
                  'creator': _metadata(row, 'source_creator', marker, 512)}
        # A bibliography field without an actual linked source must not look
        # like a traceable citation, even if the field was locally displayable.
        if not source_ref:
            source = {'ref': None, 'title': {'value': None, 'status': 'missing_or_unmapped'},
                      'creator': {'value': None, 'status': 'missing_or_unmapped'}}
        entries.append({
            'ref': ref,
            'subject': _content(row, 'subject', comparison.get('subject_projection'),
                                'k37-reviewed-subject', frozenset(('source_confirmed',)), 512),
            'recorded_speaker': _content(row, 'reported_speaker', comparison.get('reported_speaker_projection'),
                                         'k37-recorded-speaker', frozenset(('recorded_unverified',)), 512),
            'summary': _content(row, 'summary', comparison.get('summary_projection'),
                                'k2-reviewed-summary', _FIELDS, 500),
            'reasoning': _content(row, 'reasoning', comparison.get('reasoning_projection'),
                                  'k37-reviewed-reasoning', _FIELDS, 1000),
            'source': source,
            'statuses': {'source_status': _status(row.get('source_verification_status')) if source_ref else 'unconfirmed',
                         'academic_status': 'unconfirmed',
                         'reported_academic_status': _status(row.get('reported_independent_review_status')),
                         'authority_status': 'unconfirmed',
                         'recorded_authority_status': _status(row.get('input_authority_status')),
                         'rights_status': _status(row.get('rights_status'))},
        })
    return {
        'status': 'evidence_only', 'selected': selected, 'entries': entries,
        'truncated': len(comparison['claims']) > _LIMIT,
        'model_status': 'model_unavailable',
        # Ordered research outline, not assertions or generated analysis.
        # Availability reports only locally displayable recorded candidates.
        'analysis_outline': [
            {'section': 'scope', 'status': 'selected' if selected else 'not_selected'},
            {'section': 'interpretations', 'status': 'recorded_candidates_available' if any(e['summary']['value'] for e in entries) else 'not_available'},
            {'section': 'arguments', 'status': 'recorded_candidates_available' if any(e['reasoning']['value'] for e in entries) else 'not_available'},
            {'section': 'sources_and_locations', 'status': 'linked_sources_available' if any(e['source']['ref'] for e in entries) else 'not_available'},
            {'section': 'similarities_and_differences', 'status': 'not_assessed'},
            {'section': 'rebuttals_and_disagreements', 'status': 'not_assessed'},
            {'section': 'methodological_perspectives', 'status': 'not_assessed'},
            {'section': 'uncertainties', 'status': 'review_needed'},
            {'section': 'ai_scope', 'status': 'model_unavailable'},
        ],
        'unresolved': ['원전 확인·공식성·독립 학술 심사와 권리 상태는 각각 확인해야 합니다.',
                       '공통점, 차이와 직접 반론은 별도의 확인된 근거 없이 자동 판정하지 않습니다.',
                       'AI 모델이 연결되지 않아 AI 분석을 생성하지 않았습니다.'],
    }
