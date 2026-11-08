"""Authentication boundary for independently obtained public snapshots.

No snapshot is currently registered: loading any real input fails closed. A
future reviewed change may register the exact digest of a fixed public corpus,
its source and metadata-use/privacy policy. This loader never downloads data.
"""
from datetime import date
import hashlib
import json
from types import MappingProxyType
from urllib.parse import urlsplit

_MAX_BYTES = 32 * 1024 * 1024
_MAX_RECORDS = 200000
_FIELDS = frozenset(('source_title', 'source_creator', 'source_publisher', 'source_year'))
_BASES = frozenset(('licensed_permission', 'public_domain', 'applicable_law_private_factual_metadata'))
_TOKEN = object()

# No actual source has been vetted and registered in this repository.
_TRUSTED_POLICIES = MappingProxyType({})


def _date(value):
    try:
        return isinstance(value, str) and date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _reference(value):
    try:
        parsed = urlsplit(value)
        return (parsed.scheme == 'https' and bool(parsed.hostname)
                and not parsed.username and not parsed.password)
    except (TypeError, ValueError):
        return False


class AuthenticatedPublicSnapshot:
    __slots__ = ('__rows', '__policy')

    def __init__(self, token, rows, policy):
        if token is not _TOKEN:
            raise ValueError('public_snapshot_untrusted')
        self.__rows = rows
        self.__policy = policy

    def __repr__(self):
        return '<AuthenticatedPublicSnapshot redacted>'


def load_authenticated_snapshot(snapshot_id, content, *, today):
    """Load a fixed registered snapshot; reject all unknown/unreviewed input.

    The static policy must document and verify source identity, exact snapshot
    digest, private-local metadata display/search, jurisdiction, privacy and
    review dates. A title/author match alone does not satisfy these conditions.
    Exceptions never contain snapshot bytes, values, paths or identifiers.
    """
    try:
        policy = _TRUSTED_POLICIES.get(snapshot_id) if isinstance(snapshot_id, str) else None
        if not isinstance(policy, dict) or not isinstance(content, bytes) or len(content) > _MAX_BYTES:
            raise ValueError('public_snapshot_untrusted')
        expected = policy.get('sha256')
        if not isinstance(expected, str) or len(expected) != 64 or hashlib.sha256(content).hexdigest() != expected:
            raise ValueError('public_snapshot_untrusted')
        fields = policy.get('allowed_fields')
        if not (policy.get('source_verified') is True and policy.get('rights_verified') is True
                and policy.get('privacy_verified') is True
                # A fixed corpus-level assertion is not individual privacy
                # clearance. This callback is trusted static application code,
                # never supplied by the snapshot JSON or an HTTP request.
                and callable(policy.get('privacy_verifier'))
                and policy.get('scope') == 'private_local_display_and_search'
                and policy.get('basis') in _BASES and isinstance(fields, (tuple, frozenset))
                and fields and set(fields) <= _FIELDS
                and _reference(policy.get('source_reference'))
                and _reference(policy.get('rights_reference'))
                and isinstance(policy.get('jurisdiction'), str) and policy['jurisdiction'].strip()
                and isinstance(policy.get('reviewer'), str) and policy['reviewer'].strip()):
            raise ValueError('public_snapshot_untrusted')
        start, end, checked = (policy.get(x) for x in ('valid_from', 'valid_until', 'reviewed_at'))
        if not all(_date(x) for x in (start, end, checked, today)) or not start <= checked <= today <= end:
            raise ValueError('public_snapshot_untrusted')
        obj = json.loads(content)
        rows = obj.get('records') if isinstance(obj, dict) else None
        if not isinstance(rows, list) or len(rows) > _MAX_RECORDS:
            raise ValueError('public_snapshot_untrusted')
        return AuthenticatedPublicSnapshot(_TOKEN, rows, dict(policy))
    except Exception:
        raise ValueError('public_snapshot_untrusted') from None


def _snapshot_contents(snapshot):
    """Private integration helper; do not log or serialize its return value."""
    if type(snapshot) is not AuthenticatedPublicSnapshot:
        raise ValueError('public_snapshot_untrusted')
    return snapshot._AuthenticatedPublicSnapshot__rows, snapshot._AuthenticatedPublicSnapshot__policy
