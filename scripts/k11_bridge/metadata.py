"""Private metadata projection; untrusted archive flags never grant display.

Real evidence must be independently reviewed by trusted application code; an
archive checksum, a recorded source status, or caller-supplied JSON cannot
supply that review. The application configures no such real verifier yet.
Values stay in memory and are intentionally opaque to diagnostics.
"""
from datetime import date
from contextlib import redirect_stderr, redirect_stdout
import re
from urllib.parse import urlsplit
from j3_bridge.private_io import _PRIVATE_READ_LOCK, _DISCARD

FIELDS = frozenset(('source_title', 'source_creator', 'source_publisher', 'source_year', 'community_name'))
BASES = frozenset(('licensed_permission', 'public_domain', 'applicable_law_private_factual_metadata'))
_SEAL = object()


class VerifiedMetadataIndex:
    __slots__ = ('__dataset', '__records')

    def __init__(self, seal, dataset, records):
        if seal is not _SEAL:
            raise ValueError('metadata_verification_required')
        self.__dataset = dataset
        self.__records = {key: dict(value) for key, value in records.items()}

    def __repr__(self):
        return '<VerifiedMetadataIndex redacted>'

    def for_record(self, dataset, key):
        if dataset != self.__dataset or not isinstance(key, str):
            return {}
        return dict(self.__records.get(key, {}))


def _valid_date(value):
    try:
        return isinstance(value, str) and date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _synthetic_url(value):
    try:
        url = urlsplit(value)
        return (url.scheme == 'https' and url.hostname == 'example.invalid'
                and url.path not in ('', '/') and not url.username and not url.password
                and url.port in (None, 443))
    except (ValueError, TypeError):
        return False


def build_verified_index(dataset, records, reviews, *, today, independent_verifier):
    """Bind field-level verification to source, edition and actual field value.

    ``independent_verifier`` must be trusted application code that independently
    confirms the evidence and usage basis; no bool or marker from a research
    archive is proof. The application does not currently configure a real
    verifier. Local Python encapsulation protects against accidental input
    confusion, not malicious in-process code.
    """
    if dataset not in ('D8', 'D9', 'D10', 'synthetic') or not _valid_date(today):
        raise ValueError('invalid_metadata_request')
    if not isinstance(records, dict) or not isinstance(reviews, list) or not callable(independent_verifier):
        raise ValueError('invalid_metadata_request')
    valid = {}
    duplicates, seen = set(), set()
    for review in reviews:
        if not isinstance(review, dict):
            continue
        key, field = review.get('key'), review.get('field')
        if not isinstance(key, str) or field not in FIELDS:
            continue
        marker = (key, field)
        if marker in seen:
            valid.pop(marker, None)
            duplicates.add(marker)
            continue
        seen.add(marker)
        row = records.get(key)
        if not isinstance(row, dict):
            continue
        fields = row.get('fields')
        if not isinstance(fields, dict):
            continue
        value = fields.get(field)
        if not isinstance(value, str) or not value.strip() or len(value) > 500 or any(ord(c) < 32 for c in value):
            continue
        if field == 'source_year' and (len(value) != 4 or not value.isascii() or not value.isdigit() or not 1000 <= int(value) <= 2100):
            continue
        if not (all(isinstance(review.get(name), str) and review[name].strip()
                    for name in ('source_id', 'edition_id', 'reviewer'))
                and row.get('source_id') == review['source_id']
                and row.get('edition_id') == review['edition_id']
                and review.get('value') == value
                and review.get('source_confirmation') == 'independently_confirmed'
                and review.get('rights_review') == 'independently_confirmed'
                and review.get('privacy_review') == 'cleared'
                and review.get('scope') == 'private_local_display_and_search'
                and isinstance(review.get('jurisdiction'), str) and review['jurisdiction'].strip()
                and review.get('basis') in BASES
                and review.get('conflict') is False):
            continue
        start, end, checked = (review.get(name) for name in ('valid_from', 'valid_until', 'reviewed_at'))
        if not all(_valid_date(x) for x in (start, end, checked)) or not start <= checked <= today <= end:
            continue
        try:
            # The review callback receives private data. Reuse the reader's
            # process-wide Python stream guard against accidental print calls;
            # the lock coordinates only callers using the same guard. Native fd
            # writes, pre-existing log handlers and subprocesses are outside
            # this mechanism and the verifier must not emit private data.
            with _PRIVATE_READ_LOCK, redirect_stdout(_DISCARD), redirect_stderr(_DISCARD):
                verified = independent_verifier(row, review) is True
        except Exception:
            verified = False
        if verified:
            valid[marker] = value
    out = {}
    for (key, field), value in valid.items():
        out.setdefault(key, {})[field] = value
    return VerifiedMetadataIndex(_SEAL, dataset, out)


def synthetic_index_for_tests(dataset, records, reviews, *, today):
    """Synthetic evidence simulation; never validates a real research field."""
    def synthetic_verifier(row, review):
        value = row['fields'][review['field']]
        return (all(review[name].startswith('synthetic:') for name in ('source_id', 'edition_id', 'reviewer'))
                and review['jurisdiction'] == 'synthetic:test'
                and all(_synthetic_url(review.get(name)) for name in ('source_evidence', 'rights_evidence'))
                and ((review['field'] == 'source_year' and value in ('2098', '2099'))
                     or (review['field'] != 'source_year' and value.startswith('SYNTHETIC-'))))
    return build_verified_index(dataset, records, reviews, today=today, independent_verifier=synthetic_verifier)


def metadata_for_record(index, dataset, key):
    if type(index) is not VerifiedMetadataIndex:
        return {}
    return index.for_record(dataset, key)


class PrivateMetadataCandidates:
    """Unverified source values for the local verifier; never an API response."""
    __slots__ = ('__dataset', '__records')

    def __init__(self, dataset, records):
        self.__dataset = dataset
        self.__records = records

    def __repr__(self):
        return '<PrivateMetadataCandidates redacted>'

    def plan_public_matches(self, public_records):
        """Compare in memory only; matches never grant use or API access.

        The caller must obtain its public snapshot independently of the private
        dataset. No source IDs, titles, names or DOI values are used to select
        network requests. A separate verifier must authenticate the snapshot,
        check individual usage and privacy conditions, and issue any grant.
        """
        from k12_bridge.matching import plan_private_matches
        return plan_private_matches(self.__records, public_records)

    def attach_public_snapshot(self, dataset, snapshot):
        """Attach only fields matched against an authenticated public snapshot.

        Unknown snapshots are rejected by the loader. Matching, review policy,
        and field copying occur locally without network access or diagnostics.
        A snapshot-level review covers bibliographic fields only, not community
        names, research text, or any scholarly/theological conclusion.
        """
        from k12_bridge.matching import plan_private_matches
        from k12_bridge.snapshot import _snapshot_contents
        if not isinstance(dataset, dict) or dataset.get('dataset') != self.__dataset:
            raise ValueError('metadata_dataset_mismatch')
        public_rows, policy = _snapshot_contents(snapshot)
        plan = plan_private_matches(self.__records, public_rows)
        matches = plan._PrivateMatchPlan__matches
        eligible = {}
        for key, fields in matches.items():
            row = self.__records.get(key)
            if not isinstance(row, dict):
                continue
            if policy.get('synthetic_only') is True:
                if not all(isinstance(row.get(name), str) and row[name].startswith('synthetic:')
                           for name in ('source_id', 'edition_id')):
                    continue
            selected = {}
            for field, value in fields.items():
                if field not in policy['allowed_fields']:
                    continue
                if policy.get('synthetic_only') is True:
                    if field == 'source_year' and value not in ('2098', '2099'):
                        continue
                    if field != 'source_year' and not value.startswith('SYNTHETIC-'):
                        continue
                try:
                    # Static trusted application code must confirm privacy for
                    # this specific source, edition, field and value. Snapshot
                    # JSON and HTTP callers cannot supply that callback.
                    with _PRIVATE_READ_LOCK, redirect_stdout(_DISCARD), redirect_stderr(_DISCARD):
                        privacy_ok = policy['privacy_verifier'](row, field, value) is True
                except Exception:
                    privacy_ok = False
                if not privacy_ok:
                    continue
                selected[field] = value
            if selected:
                eligible[key] = selected
        result = dict(dataset)
        result['_verified_metadata_index'] = VerifiedMetadataIndex(_SEAL, self.__dataset, eligible)
        return result

    def attach_reviewed(self, dataset, reviews, *, today, independent_verifier):
        """Return a new dataset with individually verified fields attached.

        The verifier is trusted, independently implemented application code;
        untrusted archive records cannot provide a callback. Do not log
        arguments or caught exceptions. The current app configures no verifier.
        """
        if not isinstance(dataset, dict) or dataset.get('dataset') != self.__dataset:
            raise ValueError('metadata_dataset_mismatch')
        index = build_verified_index(self.__dataset, self.__records, reviews,
                                     today=today, independent_verifier=independent_verifier)
        result = dict(dataset)
        result['_verified_metadata_index'] = index
        return result


def prepare_private_candidates(dataset, layers):
    """Join candidate coordinates to source/edition in memory without approval.

    A source card with multiple editions and a claim with a missing or mismatched
    source/edition chain have no candidate here. Community names require their
    own reviewed schema mapping and are intentionally not inferred.
    """
    if not isinstance(dataset, dict) or not isinstance(dataset.get('records'), list):
        raise ValueError('metadata_dataset_invalid')
    sources, editions, source_to_editions = {}, {}, {}
    for stage, tables in layers.items():
        for entry in tables.get('sources', []):
            value = entry.get('value')
            if not isinstance(value, dict):
                continue
            coordinate = f'{stage}:sources:{entry.get("line")}'
            sources[coordinate] = value
        for entry in tables.get('editions', []):
            value = entry.get('value')
            if not isinstance(value, dict):
                continue
            coordinate = f'{stage}:editions:{entry.get("line")}'
            editions[coordinate] = value
            source_to_editions.setdefault(value.get('source_id'), []).append(value)
    result = {}
    for row in dataset['records']:
        if not isinstance(row, dict):
            continue
        key = row.get('key')
        source = sources.get(key if row.get('record_kind') == 'source' else row.get('source_key'))
        if not isinstance(key, str) or not isinstance(source, dict) or not isinstance(source.get('id'), str):
            continue
        if row.get('record_kind') == 'source':
            possibilities = source_to_editions.get(source['id'], [])
            edition = possibilities[0] if len(possibilities) == 1 else None
        else:
            edition = editions.get(row.get('edition_key'))
        if not isinstance(edition, dict) or edition.get('source_id') != source['id'] or not isinstance(edition.get('id'), str):
            continue
        fields = {target: source.get(raw) for target, raw in
                  (('source_title', 'title'), ('source_creator', 'creator'), ('source_publisher', 'publisher'))
                  if isinstance(source.get(raw), str)}
        year = source.get('publication_year')
        if isinstance(year, int) and not isinstance(year, bool):
            year = str(year)
        if not isinstance(year, str) or not re.fullmatch(r'[0-9]{4}', year):
            day = source.get('publication_date')
            year = day[:4] if isinstance(day, str) and _valid_date(day) else None
        if isinstance(year, str):
            fields['source_year'] = year
        # DOI is an internal comparison key only. It is neither an approved
        # display field nor a search value and must never enter API responses,
        # diagnostics, exception messages, or outbound requests.
        identifiers = {}
        doi = source.get('doi')
        if isinstance(doi, str) and doi.strip() and len(doi) <= 512:
            identifiers['doi'] = doi.strip()
        result[key] = {'source_id': source['id'], 'edition_id': edition['id'],
                       'fields': fields, 'identifiers': identifiers}
    return PrivateMetadataCandidates(dataset.get('dataset'), result)
