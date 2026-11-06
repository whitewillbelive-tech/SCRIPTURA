"""Synthetic-only evidence contract. Never grants access to actual research.

A later real implementation needs independently reviewed, authenticated source
and license evidence; matching the frozen ledger alone does not constitute it.
"""
from datetime import date
from urllib.parse import urlsplit

FIELDS = frozenset(('source_title', 'source_creator'))
_SCOPE = ('entity_id', 'edition_id', 'locator_id', 'action', 'purpose', 'jurisdiction')


def _day(value):
    try:
        result = date.fromisoformat(value)
        return result if result.isoformat() == value else None
    except (TypeError, ValueError):
        return None


def synthetic_display_allowed(evidence, request, *, today):
    """Boolean-only simulation; all identities and evidence must be synthetic."""
    if not isinstance(evidence, dict) or not isinstance(request, dict):
        return False
    required = _SCOPE + ('field', 'decision', 'rights_decision', 'reviewer',
                         'reviewed_at', 'valid_from', 'valid_until', 'license_evidence',
                         'source_evidence', 'rights_evidence', 'verification_method',
                         'transformation', 'other_subfields_default_hidden')
    if any(k not in evidence for k in required):
        return False
    for name in ('entity_id', 'edition_id', 'locator_id', 'reviewer'):
        if not isinstance(evidence[name], str) or not evidence[name].startswith('synthetic:'):
            return False
    if any(request.get(name) != evidence[name] for name in _SCOPE + ('field',)):
        return False
    if evidence['field'] not in FIELDS or evidence['decision'] != 'candidate_visible_local':
        return False
    if evidence['action'] != 'browse' or evidence['purpose'] != 'private_local_candidate_review_only':
        return False
    if evidence['jurisdiction'] != 'synthetic:test' or evidence['rights_decision'] != 'allowed':
        return False
    if evidence['verification_method'] != 'independently_checked' or evidence['transformation'] != 'identity':
        return False
    if evidence['other_subfields_default_hidden'] is not True:
        return False
    try:
        for name in ('license_evidence', 'source_evidence', 'rights_evidence'):
            url = urlsplit(evidence[name])
            if url.scheme != 'https' or url.hostname != 'example.invalid' or not url.path or url.path == '/' or url.username or url.password or url.port not in (None, 443):
                return False
    except (TypeError, ValueError):
        return False
    start, end, checked = (_day(evidence[key]) for key in ('valid_from', 'valid_until', 'reviewed_at'))
    now = _day(today)
    return bool(start and end and checked and now and start <= checked <= now <= end)
