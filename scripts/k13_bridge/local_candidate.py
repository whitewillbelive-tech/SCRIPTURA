"""Private-local candidate bibliography, distinct from source confirmation.

Research values stay in memory. Only an authenticated loopback API may request
individual projected records. No network, file or diagnostic I/O occurs here.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
import re

FIELDS = ('source_title', 'source_creator', 'source_publisher', 'source_year', 'community_name')
STATUSES = frozenset(('recorded_unverified', 'source_confirmed', 'restricted', 'missing_or_unmapped'))
REASONS = frozenset(('no_record', 'ambiguous_source', 'ambiguous_edition',
                     'explicit_restriction', 'conditional_use', 'sensitive_or_personal',
                     'unsafe_format', 'unmapped_relationship', 'community_unlinked',
                     'community_role_unconfirmed'))
_SEAL = object()
_DISPLAY_ACTIONS = frozenset(('browse', 'display_metadata', 'metadata_display',
                              'local_display', 'private_display', 'display'))
_DENIED = frozenset(('denied', 'deny', 'prohibited', 'restricted', 'blocked',
                     'not_allowed', 'not_permitted', 'not_granted', 'disallowed',
                     'disallow', 'forbidden', 'rejected'))
_SENSITIVE = frozenset(('private', 'confidential', 'sensitive', 'personal',
                        'restricted', 'do_not_display', 'non_public'))
_SENSITIVE_KEYS = ('privacy', 'privacy_status', 'sensitivity', 'sensitivity_status',
                   'visibility', 'visibility_status', 'metadata_policy',
                   'metadata_visibility', 'local_display_policy')
_SENSITIVE_FLAGS = ('is_private', 'confidential', 'personal_data', 'restricted')
_FIELD_ALIASES = {'source_title': frozenset(('source_title', 'title')),
                  'source_creator': frozenset(('source_creator', 'creator', 'author')),
                  'source_publisher': frozenset(('source_publisher', 'publisher')),
                  'source_year': frozenset(('source_year', 'publication_year', 'publication_date')),
                  'community_name': frozenset(('community_name', 'canonical_name'))}
_PLACEHOLDERS = frozenset(('unknown', 'n/a', 'none', 'not available', 'not recorded', '미상', '알 수 없음'))
_URL = re.compile(r'(?:https?://|www\.)', re.IGNORECASE)
_EMAIL = re.compile(r'\b[^\s@]+@[^\s@]+\.[^\s@]+\b')
_TELEPHONE = re.compile(r'(?<!\d)(?:\+\d{1,3}[ .-]?)?0\d{1,3}[ .-]\d{3,4}[ .-]\d{4}(?!\d)')
_NATIONAL_ID = re.compile(r'(?<!\d)\d{6}[- ]?[1-4]\d{6}(?!\d)')


def _empty(reason='no_record', status='missing_or_unmapped'):
    return {'value': None, 'status': status, 'reason': reason}


def _field(value, field):
    if value is None or value == '':
        return _empty()
    if field == 'source_year' and isinstance(value, int) and not isinstance(value, bool):
        value = str(value)
    if not isinstance(value, str):
        return _empty('unsafe_format', 'restricted')
    value = value.strip()
    if not value:
        return _empty()
    if value.casefold() in _PLACEHOLDERS:
        return _empty()
    if (len(value) > (1024 if field == 'source_title' else 512)
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in value)
            or '<' in value or '>' in value):
        return _empty('unsafe_format', 'restricted')
    if _URL.search(value) or _EMAIL.search(value) or _TELEPHONE.search(value) or _NATIONAL_ID.search(value):
        return _empty('sensitive_or_personal', 'restricted')
    if field == 'source_year' and (not re.fullmatch(r'[0-9]{4}', value) or not 1000 <= int(value) <= 2100):
        return _empty('unsafe_format', 'restricted')
    return {'value': value, 'status': 'recorded_unverified', 'reason': None}


def _flags(record):
    if not isinstance(record, dict):
        return None
    if any(record.get(key) is True for key in _SENSITIVE_FLAGS):
        return 'sensitive_or_personal'
    for key in _SENSITIVE_KEYS:
        value = record.get(key)
        if isinstance(value, str) and value.strip().casefold() in _SENSITIVE:
            return 'sensitive_or_personal'
        if isinstance(value, str) and value.strip().casefold() in _DENIED:
            return 'explicit_restriction'
    return None


def _display_restriction(entries):
    decisions = []
    for row in entries:
        if not isinstance(row, dict) or str(row.get('action', '')).strip().casefold() not in _DISPLAY_ACTIONS:
            continue
        for name in ('decision', 'new_decision', 'permission'):
            decision = row.get(name)
            if isinstance(decision, str):
                decisions.append(re.sub(r'[\s-]+', '_', decision.strip().casefold()))
            elif decision is not None:
                # A malformed explicit decision is not a safe local grant.
                return 'explicit_restriction'
    if any(value in _DENIED for value in decisions):
        return 'explicit_restriction'
    if 'conditional' in decisions:
        return 'conditional_use'
    return None


def _field_restriction(record, field):
    if not isinstance(record, dict):
        return None
    aliases = _FIELD_ALIASES[field]
    for name in ('restricted_fields', 'private_fields', 'personal_fields', 'sensitive_fields'):
        values = record.get(name)
        if isinstance(values, (list, tuple, set)) and any(v in aliases for v in values if isinstance(v, str)):
            return 'sensitive_or_personal' if name != 'restricted_fields' else 'explicit_restriction'
    values = record.get('field_restrictions')
    if isinstance(values, dict):
        for name in aliases:
            value = values.get(name)
            if value is True:
                return 'explicit_restriction'
            if isinstance(value, str) and value.strip().casefold() in _DENIED | _SENSITIVE:
                return 'explicit_restriction'
            if isinstance(value, str) and value.strip().casefold() == 'conditional':
                return 'conditional_use'
    return None


def _contains_protected_name(value, names):
    if not isinstance(value, str):
        return False
    candidate = value.strip().casefold()
    for name in names:
        if candidate == name:
            return True
        if len(name) >= 2 and re.search(r'(?<!\w)' + re.escape(name) + r'(?!\w)', candidate):
            return True
    return False


def _year(source):
    value = source.get('publication_year')
    if isinstance(value, (int, str)) and not isinstance(value, bool) and str(value).strip():
        return value
    # A general posted/observed date is not necessarily the publication date.
    for key in ('publication_date',):
        value = source.get(key)
        if isinstance(value, str):
            if re.fullmatch(r'[0-9]{4}', value):
                return value
            if re.fullmatch(r'[0-9]{4}-[0-9]{2}', value):
                try:
                    date.fromisoformat(value + '-01')
                    return value[:4]
                except ValueError:
                    continue
            try:
                if date.fromisoformat(value).isoformat() == value:
                    return value[:4]
            except ValueError:
                pass
    return None


class LocalCandidateIndex:
    """Sealed in-memory projection; repr and aggregate never contain data."""
    __slots__ = ('__dataset', '__rows', '__summary')

    def __init__(self, token, dataset, rows, summary):
        if token is not _SEAL:
            raise ValueError('local_candidate_untrusted')
        self.__dataset = dataset
        self.__rows = rows
        self.__summary = summary

    def __repr__(self):
        return '<LocalCandidateIndex redacted>'

    def for_record(self, dataset, key):
        if dataset != self.__dataset or not isinstance(key, str):
            return {}
        row = self.__rows.get(key)
        return {field: dict(value) for field, value in row.items()} if row else {}

    def summary(self, dataset):
        if dataset != self.__dataset:
            return {}
        return {group: {field: dict(counts) for field, counts in values.items()}
                for group, values in self.__summary.items()}


def candidate_metadata_for_record(index, dataset, key):
    if type(index) is not LocalCandidateIndex:
        return {}
    return index.for_record(dataset, key)


def candidate_restriction_summary(index, dataset):
    if type(index) is not LocalCandidateIndex:
        return {}
    return index.summary(dataset)


def _summaries(rows, kinds):
    result = {}
    for group, allowed_kinds in (('cards', frozenset(('source', 'claim'))),
                                 ('sources', frozenset(('source',)))):
        result[group] = {}
        for field in FIELDS:
            counts = Counter()
            for key, values in rows.items():
                if kinds.get(key) not in allowed_kinds:
                    continue
                item = values[field]
                counts['total'] += 1
                counts[item['status']] += 1
                if item['reason']:
                    counts[item['reason']] += 1
            result[group][field] = {name: counts[name] for name in ('total', *sorted(STATUSES), *sorted(REASONS))}
    return result


def prepare_local_candidate_index(dataset, layers):
    """Project recorded fields with per-source restrictions, never approval.

    A source card is its recorded source, not a claim about a specific edition.
    A claim needs an exact source-to-edition chain. Full-text/storage/embedding
    actions never grant or block bibliography. Unknown is not a denial; known
    conditional or denied display/browse decisions are not silently ignored.
    Names remain bibliographic creator values and never become a claim speaker.
    Community identity needs an explicit verified role and is not inferred.
    """
    if not isinstance(dataset, dict) or dataset.get('dataset') not in ('D8', 'D9', 'D10', 'synthetic') or not isinstance(dataset.get('records'), list):
        raise ValueError('local_candidate_invalid')
    if not hasattr(layers, 'items'):
        raise ValueError('local_candidate_invalid')
    sources, editions, source_editions, claims = {}, {}, defaultdict(list), {}
    communities, agents, protected_names = defaultdict(list), defaultdict(list), set()
    rights_by_edition, rights_by_source = defaultdict(list), defaultdict(list)
    for stage, tables in layers.items():
        if not isinstance(stage, str) or not isinstance(tables, dict):
            continue
        for entry in tables.get('sources', []):
            if isinstance(entry, dict) and isinstance(entry.get('value'), dict):
                sources[f'{stage}:sources:{entry.get("line")}'] = entry['value']
        for entry in tables.get('editions', []):
            if isinstance(entry, dict) and isinstance(entry.get('value'), dict):
                edition = entry['value']
                editions[f'{stage}:editions:{entry.get("line")}'] = edition
                if isinstance(edition.get('source_id'), str):
                    source_editions[edition['source_id']].append(edition)
        for entry in tables.get('claims', []):
            if isinstance(entry, dict) and isinstance(entry.get('value'), dict):
                claims[f'{stage}:claims:{entry.get("line")}'] = entry['value']
        for table, index, name_field in (('communities', communities, 'canonical_name'),
                                         ('agents', agents, 'name')):
            for entry in tables.get(table, []):
                value = entry.get('value') if isinstance(entry, dict) else None
                if not isinstance(value, dict) or not isinstance(value.get('id'), str):
                    continue
                index[value['id']].append(value)
                name = value.get(name_field)
                if _flags(value) and isinstance(name, str) and name.strip():
                    protected_names.add(name.strip().casefold())
        for table in ('rights', 'rights_delta', 'rights_actions', 'rights_overrides'):
            for entry in tables.get(table, []):
                row = entry.get('value') if isinstance(entry, dict) else None
                if not isinstance(row, dict):
                    continue
                edition_id = row.get('edition_id') or row.get('baseline_edition_id')
                if isinstance(edition_id, str):
                    rights_by_edition[edition_id].append(row)
                if isinstance(row.get('source_id'), str):
                    rights_by_source[row['source_id']].append(row)
    result, kinds = {}, {}
    for row in dataset['records']:
        if not isinstance(row, dict) or not isinstance(row.get('key'), str):
            continue
        key, kind = row['key'], row.get('record_kind')
        if kind not in ('source', 'claim'):
            continue
        fields = {field: _empty() for field in FIELDS}
        source = sources.get(key if kind == 'source' else row.get('source_key'))
        if not isinstance(source, dict) or not isinstance(source.get('id'), str):
            fields = {field: _empty('ambiguous_source') for field in FIELDS}
            result[key], kinds[key] = fields, kind
            continue
        if kind == 'claim':
            edition = editions.get(row.get('edition_key'))
            if not isinstance(edition, dict) or edition.get('source_id') != source['id']:
                fields = {field: _empty('ambiguous_edition') for field in FIELDS}
                result[key], kinds[key] = fields, kind
                continue
            relevant_editions = [edition]
        else:
            relevant_editions = source_editions.get(source['id'], [])
        restrictions = [_flags(source), _display_restriction(rights_by_source[source['id']])]
        for edition in relevant_editions:
            restrictions.extend((_flags(edition), _display_restriction(rights_by_edition.get(edition.get('id'), []))))
        reason = ('sensitive_or_personal' if 'sensitive_or_personal' in restrictions else
                  'explicit_restriction' if 'explicit_restriction' in restrictions else
                  'conditional_use' if 'conditional_use' in restrictions else None)
        values = {'source_title': source.get('title'), 'source_creator': source.get('creator'),
                  'source_publisher': source.get('publisher'), 'source_year': _year(source)}
        for field, value in values.items():
            fields[field] = _field(value, field)
            field_reason = reason or _field_restriction(source, field)
            if not field_reason:
                field_reason = next((_field_restriction(edition, field) for edition in relevant_editions
                                     if _field_restriction(edition, field)), None)
            if field in ('source_title', 'source_creator', 'source_publisher') and _contains_protected_name(value, protected_names):
                field_reason = 'sensitive_or_personal'
            if field == 'source_creator':
                linked_ids = []
                for name in ('creator_id', 'author_id', 'creator_ids', 'author_ids'):
                    linked = source.get(name)
                    if isinstance(linked, str):
                        linked_ids.append(linked)
                    elif isinstance(linked, (list, tuple)):
                        linked_ids.extend(item for item in linked if isinstance(item, str))
                if any(_flags(agent) for linked in linked_ids for agent in agents.get(linked, [])):
                    field_reason = 'sensitive_or_personal'
            if field_reason and fields[field]['status'] == 'recorded_unverified':
                fields[field] = _empty(field_reason, 'restricted')
        # Only an explicit, unambiguous relationship may identify a community.
        fields['community_name'] = _empty()
        claim = claims.get(key) if kind == 'claim' else None
        if isinstance(claim, dict) and isinstance(claim.get('community_id'), str):
            matches = communities.get(claim['community_id'], [])
            role = claim.get('community_id_role')
            role = role.strip().casefold() if isinstance(role, str) else ''
            attribution = claim.get('attribution_kind')
            target = role in ('target', 'target_community') and attribution in ('external_critique', 'criticism', 'critique')
            self_description = role in ('self', 'source', 'speaker_community') and attribution in ('self_explanation', 'self_description', 'community_self_explanation', 'community_self_description')
            if len(matches) != 1:
                fields['community_name'] = _empty('community_unlinked')
            elif not (target or self_description):
                fields['community_name'] = _empty('community_role_unconfirmed')
            else:
                community = matches[0]
                fields['community_name'] = _field(community.get('canonical_name'), 'community_name')
                protection = _flags(community) or _flags(claim) or _field_restriction(community, 'community_name')
                if protection and fields['community_name']['status'] == 'recorded_unverified':
                    fields['community_name'] = _empty(protection, 'restricted')
                elif fields['community_name']['status'] == 'recorded_unverified':
                    fields['community_name']['relationship_role'] = 'target' if target else 'self'
        result[key], kinds[key] = fields, kind
    return LocalCandidateIndex(_SEAL, dataset['dataset'], result, _summaries(result, kinds))
