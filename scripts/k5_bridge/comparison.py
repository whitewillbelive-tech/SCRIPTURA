"""Evidence-bound private comparison; the caller supplies trusted verification.

These helpers never read an archive, write research data, or access a network.
The receipt layer must have already checked structural integrity. An archive's
own markers are not independent verification and do not configure a verifier.
"""
from collections import defaultdict
from contextlib import redirect_stdout, redirect_stderr
import re
from j3_bridge.private_io import _PRIVATE_READ_LOCK, _DISCARD

_FIELDS = ('statement_ko', 'reasoning_ko')
_RELATIONS = frozenset(('supports', 'qualifies', 'contrasts', 'contradicts', 'rebuts'))
_RELATION_ALIASES = {'support': 'supports', 'qualify': 'qualifies', 'contrast': 'contrasts',
                     'contradict': 'contradicts', 'direct_rebuttal': 'rebuts'}
_DENY = frozenset(('denied', 'prohibited', 'restricted', 'blocked', 'conditional', 'unknown'))
_TOKEN = object()
_EMAIL = re.compile(r'\b[^\s@]+@[^\s@]+\.[^\s@]+\b')
_PHONE = re.compile(r'(?<!\d)(?:\+\d{1,3}[ .-]?)?0\d{1,3}[ .-]\d{3,4}[ .-]\d{4}(?!\d)')
_NATIONAL_ID = re.compile(r'(?<!\d)\d{6}[- ]?[1-4]\d{6}(?!\d)')


class PrivateComparisonIndex:
    """Opaque in-memory index. Its results are private local projections."""
    __slots__ = ('__fields', '__relations', '__coordinates')

    def __init__(self, token, fields, relations, coordinates):
        if token is not _TOKEN:
            raise ValueError('comparison_untrusted')
        self.__fields = fields
        self.__relations = relations
        self.__coordinates = coordinates

    def __repr__(self):
        return '<PrivateComparisonIndex redacted>'

    def for_claim(self, key):
        if not isinstance(key, str):
            return {}
        values = self.__fields.get(key, {})
        return {field: dict(result) for field, result in values.items()}

    def relations_for(self, key):
        if not isinstance(key, str):
            return []
        return [dict(value) for value in self.__relations.get(key, ())]

    def reference_for_claim(self, key):
        """Return a local opaque coordinate; never return the original ID."""
        return self.__coordinates.get(key) if isinstance(key, str) else None


def _unique(rows):
    """IDs are private: return only a map, never include IDs in errors."""
    out, duplicate = {}, set()
    if not isinstance(rows, list):
        return out
    for row in rows:
        if not isinstance(row, dict):
            continue
        ident = row.get('id')
        if not isinstance(ident, str) or not ident:
            continue
        if ident in out:
            duplicate.add(ident)
        else:
            out[ident] = row
    for ident in duplicate:
        out.pop(ident, None)
    return out


def _verified(callback, *args):
    """Verifier is trusted application code, never user-provided JSON."""
    try:
        # Python-level mitigation only: logging handlers / OS fds are not
        # isolated. Never place actual research values in diagnostics.
        with _PRIVATE_READ_LOCK, redirect_stdout(_DISCARD), redirect_stderr(_DISCARD):
            return callback(*args) is True
    except Exception:
        return False


def _clean_text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 2000:
        return None
    if any(ord(ch) < 32 and ch not in '\n\t' for ch in value):
        return None
    # These prevent obvious verbatim/unsafe fields from being displayed; they
    # are not a comprehensive copyright or privacy determination.
    if any(s in value.casefold() for s in ('http://', 'https://', 'www.', '<', '>', '“', '”', '「', '」', '"')):
        return None
    if _EMAIL.search(value) or _PHONE.search(value) or _NATIONAL_ID.search(value):
        return None
    return value.strip()


def _chain(claim, review, sources, editions, locators, evidence):
    locator_id = claim.get('source_locator_id') or claim.get('locator_id')
    locator = locators.get(locator_id) if isinstance(locator_id, str) else None
    if not locator:
        return None
    edition_id, source_id = locator.get('edition_id'), locator.get('source_id')
    edition = editions.get(edition_id) if isinstance(edition_id, str) else None
    source = sources.get(source_id) if isinstance(source_id, str) else None
    if not edition or not source or edition.get('source_id') != source.get('id'):
        return None
    if claim.get('source_id') and claim['source_id'] != source.get('id'):
        return None
    if claim.get('edition_id') and claim['edition_id'] != edition.get('id'):
        return None
    # An argument may cite a different source from the claim's own location.
    # Require an explicit evidence ID so multiple valid evidence rows are not
    # silently conflated; duplicate IDs were removed by _unique.
    evidence_id = review.get('evidence_id')
    proof = evidence.get(evidence_id) if isinstance(evidence_id, str) else None
    if not proof or proof.get('claim_id') != claim.get('id'):
        return None
    proof_locator_id = proof.get('source_locator_id') or proof.get('locator_id')
    proof_locator = locators.get(proof_locator_id) if isinstance(proof_locator_id, str) else None
    if not proof_locator:
        return None
    proof_edition_id, proof_source_id = proof_locator.get('edition_id'), proof_locator.get('source_id')
    proof_edition = editions.get(proof_edition_id) if isinstance(proof_edition_id, str) else None
    proof_source = sources.get(proof_source_id) if isinstance(proof_source_id, str) else None
    if not proof_edition or not proof_source or proof_edition.get('source_id') != proof_source.get('id'):
        return None
    if proof.get('source_id') and proof['source_id'] != proof_source.get('id'):
        return None
    if proof.get('edition_id') and proof['edition_id'] != proof_edition.get('id'):
        return None
    # Different evidence locations require explicitly reviewed coordinates;
    # nothing is inferred merely from related claims or shared passages.
    if proof_locator_id != locator_id and any(review.get(k) != v.get('id') for k, v in
        (('evidence_source_id', proof_source), ('evidence_edition_id', proof_edition),
         ('evidence_locator_id', proof_locator))):
        return None
    return source, edition, locator, proof, proof_source, proof_edition, proof_locator


def _prohibited(item, field):
    for key in ('restricted_fields', 'private_fields', 'sensitive_fields', 'personal_fields'):
        if isinstance(item.get(key), (list, tuple, set)) and field in item[key]:
            return True
    flags = item.get('field_restrictions')
    if isinstance(flags, dict):
        v = flags.get(field)
        if v is True or isinstance(v, str) and v.strip().casefold() in _DENY:
            return True
    if any(item.get(key) is True for key in ('is_private', 'confidential', 'personal_data', 'restricted')):
        return True
    for key in ('privacy', 'privacy_status', 'sensitivity', 'visibility', 'metadata_policy', 'local_display_policy'):
        value = item.get(key)
        if isinstance(value, str) and value.strip().casefold().replace('-', '_') in (
                'private', 'confidential', 'personal', 'sensitive', 'non_public', 'do_not_display',
                'denied', 'prohibited', 'restricted', 'blocked', 'conditional'):
            return True
    return False


def build_private_index(tables, reviews, *, verifier):
    """Validate each claim text and explicit relationship independently.

    ``verifier`` must be trusted application code, perform field-specific
    provenance, use-rights, and privacy review, and return exactly True.
    ``reviews`` alone (including booleans or self-reported rights) never grant
    anything. A missing verifier grants nothing. No API currently installs a
    real-data verifier. Output remains local and no academic approval follows.
    """
    if not isinstance(tables, dict) or not isinstance(reviews, list) or not callable(verifier):
        raise ValueError('comparison_invalid')
    claims, sources, editions, locators, evidence = (
        _unique(tables.get(table, [])) for table in ('claims', 'sources', 'editions', 'locators', 'evidence'))
    rights = tables.get('rights', [])
    if not isinstance(rights, list):
        raise ValueError('comparison_invalid')
    results, seen, conflicts = defaultdict(dict), set(), set()
    for review in reviews:
        if not isinstance(review, dict):
            continue
        claim_id, field = review.get('claim_id'), review.get('field')
        if not isinstance(claim_id, str) or field not in _FIELDS:
            continue
        marker = (claim_id, field)
        if marker in seen:
            conflicts.add(marker)
            results[claim_id].pop(field, None)
            continue
        seen.add(marker)
        claim = claims.get(claim_id)
        if not claim:
            continue
        chain = _chain(claim, review, sources, editions, locators, evidence)
        value = _clean_text(claim.get(field))
        if not chain or value is None:
            continue
        source, edition, locator, proof, proof_source, proof_edition, proof_locator = chain
        if any(review.get(k) != v.get('id') for k, v in
               (('source_id', source), ('edition_id', edition), ('locator_id', locator), ('evidence_id', proof))):
            continue
        if any(_prohibited(obj, field) for obj in (claim, source, edition, locator, proof,
                                                    proof_source, proof_edition, proof_locator)):
            continue
        related = [item for item in rights if isinstance(item, dict)
                   and (item.get('edition_id') in (edition['id'], proof_edition['id'])
                        or item.get('source_id') in (source['id'], proof_source['id']))]
        actions = ('browse', 'local_display', 'private_display', 'display', 'own_summary', field)
        if any(str(item.get('action', '')).strip().casefold().replace('-', '_') in actions
               and any(str(item.get(k, '')).strip().casefold().replace('-', '_') in _DENY
                       for k in ('decision', 'permission', 'new_decision')) for item in related):
            continue
        if (review.get('scope') != 'private_local_display'
                or review.get('self_authored') is not True
                or review.get('nonquotation') is not True
                or review.get('privacy_cleared') is not True
                or review.get('rights_cleared') is not True):
            continue
        if _verified(verifier, claim, field, chain, review, related):
            results[claim_id][field] = {'value': value, 'status': 'recorded_unverified'}
    for claim_id, field in conflicts:
        results[claim_id].pop(field, None)
    # Deterministic within this receipt only. These are ephemeral coordinates,
    # not canonical identifiers and not proof of matching across snapshots.
    coordinates = {ident: 'k5:claims:' + str(i + 1) for i, ident in enumerate(claims)}
    rels = defaultdict(list)
    relations = tables.get('relationships', [])
    if not isinstance(relations, list):
        raise ValueError('comparison_invalid')
    for row in relations:
        if not isinstance(row, dict):
            continue
        raw_kind = row.get('relation_type')
        if not isinstance(raw_kind, str):
            continue
        kind = _RELATION_ALIASES.get(raw_kind, raw_kind)
        legacy_subject, from_claim = row.get('subject_id'), row.get('from_claim_id')
        legacy_target, to_claim = row.get('object_id'), row.get('to_claim_id')
        if (legacy_subject is not None and from_claim is not None and legacy_subject != from_claim) or \
           (legacy_target is not None and to_claim is not None and legacy_target != to_claim):
            continue
        subject, target = legacy_subject or from_claim, legacy_target or to_claim
        # No relation is inferred from co-occurrence or textual difference.
        if (not isinstance(subject, str) or not isinstance(target, str)
                or kind not in _RELATIONS or subject not in claims or target not in claims or subject == target):
            continue
        locator_id = row.get('source_locator_id') or row.get('locator_id')
        locator = locators.get(locator_id) if isinstance(locator_id, str) else None
        if not locator:
            continue
        relation_edition_id, relation_source_id = locator.get('edition_id'), locator.get('source_id')
        relation_edition = editions.get(relation_edition_id) if isinstance(relation_edition_id, str) else None
        relation_source = sources.get(relation_source_id) if isinstance(relation_source_id, str) else None
        if not relation_edition or not relation_source or relation_edition.get('source_id') != relation_source.get('id'):
            continue
        if any(_prohibited(obj, 'relationship') for obj in (row, relation_source, relation_edition, locator)):
            continue
        relation_rights = [item for item in rights if isinstance(item, dict)
                           and (item.get('source_id') == relation_source_id or item.get('edition_id') == relation_edition_id)]
        if any(str(item.get('action', '')).strip().casefold().replace('-', '_') in ('browse', 'local_display', 'private_display', 'display', 'relationship')
               and any(str(item.get(k, '')).strip().casefold().replace('-', '_') in _DENY for k in ('decision', 'new_decision', 'permission'))
               for item in relation_rights):
            continue
        if _verified(verifier, row, 'relationship', (relation_source, relation_edition, locator), None, relation_rights):
            rels[subject].append({'kind': kind, 'target_key': coordinates[target], 'status': 'recorded_unverified'})
        else:
            # The source asserts a relation, but it is not established. In
            # particular this must never appear as an actual direct rebuttal.
            rels[subject].append({'kind': 'unconfirmed_relation', 'reported_kind': kind,
                                  'target_key': coordinates[target], 'status': 'pending_evidence_review'})
    return PrivateComparisonIndex(_TOKEN, dict(results), dict(rels), coordinates)


def exact_passage_claims(claims, selected):
    """Group only identical corpus, canon scheme, and reference; never align."""
    if not isinstance(claims, list) or not isinstance(selected, dict):
        raise ValueError('comparison_invalid')
    fields = ('corpus', 'scheme', 'reference')
    if any(not isinstance(selected.get(k), str) or not selected[k] for k in fields):
        raise ValueError('comparison_invalid')
    out = []
    for item in claims:
        if (not isinstance(item, dict) or not isinstance(item.get('key'), str)
                or not re.fullmatch(r'(?:d[0-9]{1,6}|k5):claims:[1-9][0-9]{0,8}', item['key'])):
            continue
        addresses = item.get('passages')
        if isinstance(addresses, list) and any(isinstance(p, dict) and all(p.get(k) == selected[k] for k in fields) for p in addresses):
            out.append(item['key'])
    return out
