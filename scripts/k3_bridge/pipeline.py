"""Compose authenticated research increments entirely in local memory.

This is an opt-in v1 contract, not an adapter for historical Work archives.
The caller must obtain every expected archive and manifest digest through an
independently authenticated channel. No untrusted archive can grant trust.
"""
from collections import Counter, defaultdict, deque
from copy import deepcopy
import hashlib
import unicodedata

from k3_bridge.receipt import TABLES, ReceiptError, receive, _REQUIRED, _OPTIONAL
from k4_bridge.relations import build_relation_index
from k5_bridge.comparison import build_private_index


class PipelineError(ValueError):
    """Fixed error codes only; never expose research content or paths."""


class _MergedReceipt:
    __slots__ = ('__records',)

    def __init__(self, records):
        self.__records = records

    def accepted_records(self, table):
        if table not in TABLES:
            raise PipelineError('invalid_table')
        return deepcopy(self.__records.get(table, ()))

    def __repr__(self):
        return '<MergedReceipt redacted>'


def _semantic_quarantine(baseline, increment):
    """Reject inconsistent cross-baseline citation chains and dependants.

    The lower-level receipt validates IDs and kinds; this pass compares the
    referenced objects themselves, including independently trusted baseline
    rows. Never infer relationships or change the baseline.
    """
    objects = {row['id']: (table, row) for table, rows in baseline.items() for row in rows}
    delta = {row['id']: (table, row) for table, rows in increment.items() for row in rows}
    objects.update(delta)
    invalid, reverse = set(), defaultdict(list)
    for ident, (table, row) in delta.items():
        refs = [row.get(key) for key in _REQUIRED.get(table, {})]
        refs.extend(row.get(key) for key in _OPTIONAL.get(table, {}) if row.get(key) is not None)
        if table == 'claims':
            refs.extend(row.get('passage_ids', ()))
        if table == 'relationships':
            refs.extend(row.get(key) for key in ('from_claim_id', 'to_claim_id', 'subject_id', 'object_id') if row.get(key) is not None)
            locator_id = row.get('source_locator_id') or row.get('locator_id')
            if locator_id:
                if not isinstance(locator_id, str):
                    invalid.add(ident)
                else:
                    refs.append(locator_id)
                    if objects.get(locator_id, (None,))[0] != 'locators':
                        invalid.add(ident)
        for target in refs:
            if target in delta:
                reverse[target].append(ident)
        if table == 'locators':
            edition = objects.get(row.get('edition_id'), (None, {}))[1]
            if edition.get('source_id') != row.get('source_id'):
                invalid.add(ident)
        elif table == 'claims':
            loc = objects.get(row.get('source_locator_id'), (None, {}))[1]
            if ((row.get('source_id') and row['source_id'] != loc.get('source_id')) or
                    (row.get('edition_id') and row['edition_id'] != loc.get('edition_id'))):
                invalid.add(ident)
        elif table == 'evidence':
            # Supporting evidence can live in a different source from the
            # claim itself. Verify its own locator, edition and source chain.
            loc = objects.get(row.get('locator_id'), (None, {}))[1]
            edition = objects.get(loc.get('edition_id'), (None, {}))[1]
            if not loc or not edition or edition.get('source_id') != loc.get('source_id'):
                invalid.add(ident)
        elif table == 'rights':
            edition = objects.get(row.get('edition_id'), (None, {}))[1] if row.get('edition_id') else {}
            loc = objects.get(row.get('locator_id'), (None, {}))[1] if row.get('locator_id') else {}
            if ((row.get('source_id') and edition and edition.get('source_id') != row['source_id']) or
                    (row.get('source_id') and loc and loc.get('source_id') != row['source_id']) or
                    (row.get('edition_id') and loc and loc.get('edition_id') != row['edition_id'])):
                invalid.add(ident)
    queue = deque(invalid)
    while queue:
        for dependent in reverse.get(queue.popleft(), ()):
            if dependent not in invalid:
                invalid.add(dependent)
                queue.append(dependent)
    return {table: [row for row in rows if row['id'] not in invalid]
            for table, rows in increment.items()}, len(invalid)


def _normal(value):
    return ' '.join(unicodedata.normalize('NFKC', value).split()).casefold() if isinstance(value, str) else ''


def _duplicate_candidates(before, after):
    """Aggregate probable bibliography duplicates, without merging records."""
    dois = {_normal(row.get('doi')) for row in before} - {''}
    pairs = {(_normal(row.get('title')), _normal(row.get('creator'))) for row in before}
    pairs = {pair for pair in pairs if all(pair)}
    counts = Counter()
    seen_doi, seen_pairs = set(dois), set(pairs)
    for row in after:
        doi = _normal(row.get('doi'))
        pair = (_normal(row.get('title')), _normal(row.get('creator')))
        if doi and doi in seen_doi:
            counts['duplicate_doi_candidates'] += 1
        if all(pair) and pair in seen_pairs:
            counts['duplicate_title_creator_candidates'] += 1
        if doi:
            seen_doi.add(doi)
        if all(pair):
            seen_pairs.add(pair)
    return dict(counts)


class ResearchPipeline:
    """Immutable sequence anchored in a separately verified baseline ZIP.

    Bootstrap is deliberately restricted to a self-contained baseline. Each
    successor manifest must refer to the exact preceding archive digest, and
    each archive and manifest digest must be authenticated out of band.
    Quarantined delta rows never mutate or remove accepted baseline records.
    """
    __slots__ = ('__archive_digest', '__records', '__increments', '__last', '__version')

    def __init__(self, archive_digest, records, increments, last, version):
        self.__archive_digest = archive_digest
        self.__records = records
        self.__increments = increments
        self.__last = last
        self.__version = version

    def __repr__(self):
        return '<ResearchPipeline redacted>'

    @classmethod
    def bootstrap(cls, blob, *, archive_sha256, manifest_sha256, root_sha256):
        try:
            if type(blob) is not bytes or hashlib.sha256(blob).hexdigest() != archive_sha256:
                raise PipelineError('untrusted_baseline')
            receipt = receive(blob, trusted_manifest_sha256=manifest_sha256,
                              trusted_baseline_sha256=root_sha256, baseline_ids={})
            counts = receipt.aggregate()
            if counts['accepted_rows'] != counts['input_rows']:
                raise PipelineError('baseline_quarantined')
            records = {table: receipt.accepted_records(table) for table in TABLES}
            records, semantic_errors = _semantic_quarantine({}, records)
            if semantic_errors:
                raise PipelineError('baseline_quarantined')
            return cls(archive_sha256, records, 0, counts, receipt.version())
        except (ReceiptError, TypeError, ValueError, KeyError):
            raise PipelineError('baseline_invalid') from None

    def advance(self, blob, *, archive_sha256, manifest_sha256):
        """Return a new pipeline; do not modify the current baseline."""
        try:
            if type(blob) is not bytes or hashlib.sha256(blob).hexdigest() != archive_sha256:
                raise PipelineError('untrusted_increment')
            baseline_ids = {}
            for table, rows in self.__records.items():
                for row in rows:
                    ident = row['id']
                    if ident in baseline_ids:
                        raise PipelineError('baseline_invalid')
                    baseline_ids[ident] = table
            receipt = receive(blob, trusted_manifest_sha256=manifest_sha256,
                              trusted_baseline_sha256=self.__archive_digest,
                              baseline_ids=baseline_ids, trusted_baseline_version=self.__version)
            delta = {table: receipt.accepted_records(table) for table in TABLES}
            delta, extra_quarantine = _semantic_quarantine(self.__records, delta)
            counts = receipt.aggregate()
            counts['accepted_rows'] -= extra_quarantine
            counts['quarantined_semantic'] = extra_quarantine
            counts.update(_duplicate_candidates(self.__records['sources'], delta['sources']))
            records = {table: deepcopy(rows) for table, rows in self.__records.items()}
            for table in TABLES:
                records[table].extend(delta[table])
            return ResearchPipeline(archive_sha256, records, self.__increments + 1,
                                    counts, receipt.version())
        except (ReceiptError, TypeError, ValueError, KeyError):
            raise PipelineError('increment_invalid') from None

    def summary(self):
        counts = Counter({table: len(self.__records[table]) for table in TABLES})
        counts['increments'] = self.__increments
        counts['last_input_rows'] = self.__last['input_rows']
        counts['last_accepted_rows'] = self.__last['accepted_rows']
        counts['last_quarantined_rows'] = self.__last['input_rows'] - self.__last['accepted_rows']
        counts['last_quarantined_semantic'] = self.__last.get('quarantined_semantic', 0)
        counts['last_duplicate_doi_candidates'] = self.__last.get('duplicate_doi_candidates', 0)
        counts['last_duplicate_title_creator_candidates'] = self.__last.get('duplicate_title_creator_candidates', 0)
        return dict(counts)

    def relation_index(self):
        return build_relation_index(_MergedReceipt(self.__records))

    def comparison_index(self, reviews, *, verifier):
        """Only trusted application code may supply the independent verifier.

        Research archives cannot configure callbacks. No verifier is enabled
        by default and these indexes are not wired to any public API.
        """
        return build_private_index(deepcopy(self.__records), reviews, verifier=verifier)
