"""Read-only source-attribution links. Raw records stay in memory.

Relationships are statements in the research archive, not independently
verified facts. Coordinates are generated for local lookup; no original
identifiers, names or evidence text are returned in these projections.
"""
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import date
import calendar
import re

_TABLES = ('claims', 'sources', 'editions', 'locators', 'evidence', 'agents',
           'communities', 'affiliations', 'authority_documents')
_KINDS = frozenset(('official_doctrine', 'institutional_statement',
                    'community_self_explanation', 'individual_opinion',
                    'scholarly_interpretation', 'academic_interpretation',
                    'reported_view', 'external_critique'))
_STATUS = frozenset(('unknown', 'pending', 'unverified', 'source_checked',
                     'source_verified', 'disputed', 'rejected'))
_AFFILIATION_ROLES = frozenset(('member', 'clergy', 'leader', 'researcher',
                                'employee', 'founder', 'representative', 'affiliate'))
_TOKEN = object()


def _status(value):
    return value if type(value) is str and value in _STATUS else 'unknown'


def _date_interval(value):
    if value is None or value == '':
        return None
    if type(value) is not str:
        return False
    try:
        if re.fullmatch(r'[0-9]{4}', value):
            year = int(value)
            return value, date(year, 1, 1), date(year, 12, 31)
        if re.fullmatch(r'[0-9]{4}-[0-9]{2}', value):
            year, month = map(int, value.split('-'))
            return value, date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
        day = date.fromisoformat(value)
        return (value, day, day) if day.isoformat() == value else False
    except ValueError:
        return False


class RelationIndex:
    """Opaque research links; never stringify input records or identifiers."""
    __slots__ = ('__claims', '__affiliations', '__summary')

    def __init__(self, token, claims, affiliations, summary):
        if token is not _TOKEN:
            raise ValueError('untrusted_relation_index')
        self.__claims = claims
        self.__affiliations = affiliations
        self.__summary = summary

    def __repr__(self):
        return '<RelationIndex redacted>'

    def for_claim(self, coordinate):
        if type(coordinate) is not str:
            return None
        row = self.__claims.get(coordinate)
        if row is None:
            return None
        return {k: (dict(v) if isinstance(v, dict) else v) for k, v in row.items()}

    def affiliations(self):
        return tuple(deepcopy(item) for item in self.__affiliations)

    def summary(self):
        return dict(self.__summary)


def build_relation_index(receipt):
    """Build links from accepted records without mutating or promoting them.

    A valid citation chain is necessary for asserting a recorded relationship,
    but it never proves identity, formal doctrine, or human scholarly review.
    A single missing, ambiguous or conflicting reference leaves the edge pending.
    """
    try:
        tables = {}
        for name in _TABLES:
            value = receipt.accepted_records(name)
            if not isinstance(value, (tuple, list)):
                raise ValueError('relation_input_invalid')
            tables[name] = value
        lookup = {}
        for name, entries in tables.items():
            grouped = defaultdict(list)
            for ordinal, row in enumerate(entries, 1):
                if not isinstance(row, dict):
                    continue
                ident = row.get('id')
                if isinstance(ident, str) and ident:
                    grouped[ident].append((f'k4:{name}:{ordinal}', row))
            lookup[name] = grouped

        def find(table, ident):
            if not isinstance(ident, str) or not ident:
                return None
            hits = lookup[table].get(ident, ())
            return hits[0] if len(hits) == 1 else None

        def citation(locator_id):
            loc = find('locators', locator_id)
            if not loc:
                return None
            edition = find('editions', loc[1].get('edition_id'))
            if not edition:
                return None
            source = find('sources', edition[1].get('source_id'))
            if not source:
                return None
            if loc[1].get('source_id') not in (None, '', edition[1].get('source_id')):
                return None
            return {'source': source[0], 'edition': edition[0], 'locator': loc[0]}

        claims = {}
        summary = Counter()
        for ordinal, claim in enumerate(tables['claims'], 1):
            if not isinstance(claim, dict):
                summary['invalid_claims'] += 1
                continue
            claim_key = f'k4:claims:{ordinal}'
            ident = claim.get('id')
            if not isinstance(ident, str) or not ident or find('claims', ident) is None:
                summary['invalid_claims'] += 1
                continue
            chain = citation(claim.get('source_locator_id') or claim.get('locator_id'))
            kind = claim.get('attribution_kind')
            kind = kind if type(kind) is str and kind in _KINDS else 'unmapped'
            input_kind = kind
            if kind == 'official_doctrine':
                # The archive's assertion is not proof of formal adoption.
                kind = 'unconfirmed_official_claim'
            actor = find('agents', claim.get('speaker_id'))
            target = find('communities', claim.get('target_community_id'))
            community = find('communities', claim.get('community_id'))
            role = claim.get('community_id_role')
            community_edge = {'role': 'unspecified', 'community': None, 'status': 'pending'}
            conflicting_target = bool(claim.get('target_community_id') and claim.get('community_id')
                                      and claim['target_community_id'] != claim['community_id'])
            conflicting_target = conflicting_target or bool(
                claim.get('target_community_id') and
                (kind == 'community_self_explanation' or (kind == 'external_critique' and role == 'self')))
            if chain and community and not conflicting_target and kind == 'community_self_explanation' and role == 'self':
                community_edge = {'role': 'reported_self', 'community': community[0], 'status': 'recorded_unverified'}
            elif chain and community and not conflicting_target and kind == 'external_critique' and role == 'target':
                community_edge = {'role': 'critique_target', 'community': community[0], 'status': 'recorded_unverified'}
            elif chain and target and not conflicting_target and kind == 'external_critique':
                community_edge = {'role': 'critique_target', 'community': target[0], 'status': 'recorded_unverified'}
            # A speaker name on a source is a bibliographic attribution, not a
            # claim speaker; only an explicit claim speaker reference is linked.
            actor_edge = {'actor': actor[0] if actor and chain else None,
                          'status': 'recorded_unverified' if actor and chain else 'pending'}
            result = {'kind': kind, 'input_attribution': input_kind,
                      'citation': chain, 'speaker': actor_edge,
                      'community': community_edge,
                      'input_verification_status': _status(claim.get('verification_status')),
                      'input_authority_status': _status(claim.get('authority_status')),
                      'effective_official_status': 'pending',
                      'independent_scholarly_review': 'pending'}
            claims[claim_key] = result
            summary['claims'] += 1
            summary['citation_linked' if chain else 'citation_pending'] += 1
            summary['speaker_recorded' if actor_edge['actor'] else 'speaker_pending'] += 1
            summary['community_recorded' if community_edge['community'] else 'community_pending'] += 1

        affiliations = []
        for row in tables['affiliations']:
            if not isinstance(row, dict):
                continue
            actor = find('agents', row.get('agent_id'))
            community = find('communities', row.get('community_id'))
            chain = citation(row.get('source_locator_id') or row.get('locator_id'))
            start, end = _date_interval(row.get('valid_from')), _date_interval(row.get('valid_until'))
            valid = bool(actor and community and chain and start is not False and end is not False
                         and (not start or not end or start[1] <= end[2]))
            if valid:
                role = row.get('role')
                affiliations.append({'actor': actor[0], 'community': community[0],
                                     'citation': chain, 'valid_from': start[0] if start else None,
                                     'valid_until': end[0] if end else None,
                                     'role': role if type(role) is str and role in _AFFILIATION_ROLES else 'unmapped',
                                     'status': 'recorded_unverified',
                                     'input_verification_status': _status(row.get('verification_status'))})
            summary['affiliations_recorded' if valid else 'affiliations_pending'] += 1
        for key in ('claims', 'invalid_claims', 'citation_linked', 'citation_pending',
                    'speaker_recorded', 'speaker_pending', 'community_recorded',
                    'community_pending', 'affiliations_recorded', 'affiliations_pending'):
            summary.setdefault(key, 0)
        return RelationIndex(_TOKEN, claims, tuple(affiliations), dict(summary))
    except Exception:
        # Research ids, paths and caught exception text must never escape.
        raise ValueError('relation_build_failed') from None
