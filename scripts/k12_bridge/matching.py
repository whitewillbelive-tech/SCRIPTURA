"""Compare an already obtained public snapshot to private rows in memory.

This module never performs I/O and does not grant display rights. A match is
only a candidate for a separately authenticated public source, privacy and
permitted-use review. Neither the match plan nor any value is an API response.
"""
from collections import defaultdict
import re
import unicodedata

_FIELDS = ('source_title', 'source_creator', 'source_publisher', 'source_year')
_DOI = re.compile(r'10\.[0-9]{4,9}/[^\s\x00-\x1f]{1,255}', re.IGNORECASE)


def _text(value):
    if not isinstance(value, str):
        return ''
    return ' '.join(unicodedata.normalize('NFKC', value).split()).casefold()


def _doi(value):
    if not isinstance(value, str):
        return ''
    value = value.strip()
    for prefix in ('https://doi.org/', 'http://doi.org/', 'doi:'):
        if value.casefold().startswith(prefix):
            value = value[len(prefix):].strip()
            break
    return value.casefold() if _DOI.fullmatch(value) else ''


class PrivateMatchPlan:
    """Opaque unapproved matches: intentionally cannot issue a display grant."""
    __slots__ = ('__matches', '__summary')

    def __init__(self, matches, summary):
        self.__matches = matches
        self.__summary = summary

    def __repr__(self):
        return '<PrivateMatchPlan redacted; no display grant>'

    def summary(self):
        return dict(self.__summary)


def plan_private_matches(private_records, public_records):
    """Return fixed counts and opaque candidate matches; never raise raw data.

    Public rows have standardized ``doi`` and ``fields``. A unique DOI,
    exact title and complete author-field equality are required. Conflicting
    years, duplicate public DOIs, and a DOI attached to different private
    source/edition pairs deny the entire match. Other fields are matched and
    counted independently. The caller must authenticate the snapshot and
    assess usage/privacy separately before making a field available.
    """
    if not isinstance(private_records, dict) or not isinstance(public_records, list):
        raise ValueError('invalid_match_input')
    public = defaultdict(list)
    for item in public_records:
        if not isinstance(item, dict) or not isinstance(item.get('fields'), dict):
            continue
        doi = _doi(item.get('doi'))
        if doi:
            public[doi].append(item['fields'])
    private = defaultdict(set)
    for row in private_records.values():
        if not isinstance(row, dict) or not isinstance(row.get('identifiers'), dict):
            continue
        doi = _doi(row['identifiers'].get('doi'))
        source, edition = row.get('source_id'), row.get('edition_id')
        if doi and isinstance(source, str) and source and isinstance(edition, str) and edition:
            private[doi].add((source, edition))
    summary = {'private_cards': len(private_records), 'doi_candidates': 0,
               'ambiguous_private': 0, 'ambiguous_public': 0, 'identity_mismatch': 0,
               'matched_cards': 0, **{field: 0 for field in _FIELDS}}
    matched = {}
    for key, row in private_records.items():
        if not isinstance(key, str) or not isinstance(row, dict):
            continue
        ids, fields = row.get('identifiers'), row.get('fields')
        if not isinstance(ids, dict) or not isinstance(fields, dict):
            continue
        doi = _doi(ids.get('doi'))
        if not doi or not public.get(doi):
            continue
        summary['doi_candidates'] += 1
        if len(private[doi]) != 1:
            summary['ambiguous_private'] += 1
            continue
        if len(public[doi]) != 1:
            summary['ambiguous_public'] += 1
            continue
        verified = public[doi][0]
        title, author = _text(fields.get('source_title')), _text(fields.get('source_creator'))
        local_year, public_year = _text(fields.get('source_year')), _text(verified.get('source_year'))
        if (not title or not author or title != _text(verified.get('source_title'))
                or author != _text(verified.get('source_creator'))
                or (local_year and public_year and local_year != public_year)):
            summary['identity_mismatch'] += 1
            continue
        each = {field: fields[field] for field in _FIELDS
                if _text(fields.get(field)) and _text(fields.get(field)) == _text(verified.get(field))}
        if not each:
            continue
        matched[key] = each
        summary['matched_cards'] += 1
        for field in each:
            summary[field] += 1
    return PrivateMatchPlan(matched, summary)
