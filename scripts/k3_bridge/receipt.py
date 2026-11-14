"""Authenticated, bounded, non-destructive generic research ZIP receipt.

This is a new opt-in contract, not an assertion about the format of any existing
Work ZIP. Trust anchors must arrive out of band, never from the archive itself.
No research text, identifier, path, or digest is emitted in diagnostics.
"""
from collections import Counter, defaultdict, deque
from copy import deepcopy
import hashlib
import io
import json
import re
import stat
import unicodedata
from zipfile import BadZipFile, ZipFile

MAX_ARCHIVE = 64 * 1024 * 1024
MAX_UNPACKED = 128 * 1024 * 1024
MAX_FILE = 32 * 1024 * 1024
MAX_FILES = 128
MAX_ROWS = 200_000
MAX_LINE = 1_048_576
TABLES = frozenset(('sources', 'editions', 'locators', 'passages', 'claims',
                    'evidence', 'rights', 'relationships', 'communities', 'agents',
                    'affiliations', 'authority_documents'))
_VERSION = re.compile(r'D[1-9][0-9]{0,5}')
_SHA = re.compile(r'[0-9a-f]{64}')
_PATH = re.compile(r'records/([a-z_]+)\.jsonl')
_SEAL = object()
_RIGHT_ACTIONS = frozenset(('browse', 'display', 'display_metadata', 'collect_metadata',
                            'store', 'index', 'short_quote', 'full_text', 'embed',
                            'redistribute', 'ai_processing'))
_RIGHT_DECISIONS = frozenset(('allowed', 'denied', 'conditional', 'unknown', 'not_recorded'))
_RELATIONS = frozenset(('support', 'qualify', 'contrast', 'contradict', 'direct_rebuttal',
                        'supports', 'qualifies', 'contrasts', 'contradicts', 'rebuts', 'unknown'))
_REQUIRED = {
    'editions': {'source_id': 'sources'},
    'locators': {'source_id': 'sources', 'edition_id': 'editions'},
    'claims': {'source_locator_id': 'locators'},
    'evidence': {'claim_id': 'claims', 'locator_id': 'locators'},
    'affiliations': {'agent_id': 'agents', 'community_id': 'communities'},
    'authority_documents': {'source_id': 'sources', 'community_id': 'communities'},
}
_OPTIONAL = {
    'claims': {'source_id': 'sources', 'edition_id': 'editions'},
    'rights': {'source_id': 'sources', 'edition_id': 'editions', 'locator_id': 'locators'},
}


class ReceiptError(ValueError):
    """Fixed error codes only; never include source data in exceptions."""


class ResearchReceipt:
    """Opaque receipt; explicit record access remains sensitive and local."""
    __slots__ = ('__accepted', '__counts', '__version')

    def __init__(self, token, version, accepted, counts):
        if token is not _SEAL:
            raise ReceiptError('receipt_untrusted')
        self.__version = version
        self.__accepted = accepted
        self.__counts = counts

    def __repr__(self):
        return '<ResearchReceipt redacted>'

    __str__ = __repr__

    def accepted_records(self, table):
        if table not in TABLES:
            raise ReceiptError('invalid_table')
        return deepcopy(self.__accepted.get(table, []))

    def aggregate(self):
        return dict(self.__counts)

    def version(self):
        """Validated version label; no source identifiers or content."""
        return self.__version

    def provenance(self):
        """Version metadata only; never include baseline hashes or IDs."""
        # A matching externally supplied anchor does not itself establish that
        # the caller's baseline ID map was derived from those exact bytes.
        return {'version': self.__version, 'baseline_anchor_matched': True,
                'baseline_ids_binding_verified': False}


def _fail():
    raise ReceiptError('archive_invalid') from None


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _object_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail()
        result[key] = value
    return result


def _json(data):
    return json.loads(data.decode('utf-8'), object_pairs_hook=_object_pairs,
                      parse_constant=lambda _: _fail())


def _text_field(value, limit):
    return (isinstance(value, str) and bool(value.strip()) and len(value) <= limit
            and not any(ord(ch) < 32 for ch in value))


def _schema_valid(table, row):
    """Strict minimum for this proposed v1 format, not the uninspected D13."""
    if not isinstance(row, dict) or not _text_field(row.get('id'), 512):
        return False
    if table == 'sources' and not _text_field(row.get('title'), 4096):
        return False
    if table == 'passages' and not (isinstance(row.get('corpus'), str) and row['corpus'] in ('Bible', 'Quran')
                                     and _text_field(row.get('scheme'), 256)
                                     and _text_field(row.get('reference'), 512)):
        return False
    if table == 'rights' and not (isinstance(row.get('action'), str) and row['action'] in _RIGHT_ACTIONS
                                   and isinstance(row.get('decision'), str) and row['decision'] in _RIGHT_DECISIONS):
        return False
    if table == 'relationships' and (not isinstance(row.get('relation_type'), str) or row['relation_type'] not in _RELATIONS):
        return False
    if table == 'communities' and not _text_field(row.get('canonical_name'), 1024):
        return False
    if table == 'agents' and not _text_field(row.get('name'), 1024):
        return False
    return True


def receive(blob, *, trusted_manifest_sha256, trusted_baseline_sha256, baseline_ids, trusted_baseline_version=None):
    """Validate an archive using separately provisioned, exact trust anchors.

    ``trusted_manifest_sha256`` must come from an independently authenticated
    channel. This function does not create or load a trust store, nor can a
    ZIP authorize itself. ``trusted_baseline_sha256`` and ``baseline_ids``
    describe the caller's already verified baseline. Archived data is read
    entirely in memory; invalid individual rows are quarantined. A bad ZIP,
    manifest, hash or unauthenticated baseline rejects the whole increment.
    """
    try:
        return _receive(blob, trusted_manifest_sha256, trusted_baseline_sha256, baseline_ids, trusted_baseline_version)
    except ReceiptError:
        raise
    except Exception:
        _fail()


def _receive(blob, trusted_manifest_sha256, trusted_baseline_sha256, baseline_ids, trusted_baseline_version):
    if (type(blob) is not bytes or len(blob) > MAX_ARCHIVE
            or not isinstance(trusted_manifest_sha256, str) or not _SHA.fullmatch(trusted_manifest_sha256)
            or not isinstance(trusted_baseline_sha256, str) or not _SHA.fullmatch(trusted_baseline_sha256)
            or not isinstance(baseline_ids, dict)):
        _fail()
    if any(not isinstance(k, str) or not k or v not in TABLES for k, v in baseline_ids.items()):
        _fail()
    try:
        archive = ZipFile(io.BytesIO(blob))
    except (BadZipFile, ValueError):
        _fail()
    with archive:
        infos = archive.infolist()
        names = [i.filename for i in infos]
        if (not infos or len(infos) > MAX_FILES or len(set(names)) != len(names)
                or sum(i.file_size for i in infos) > MAX_UNPACKED
                or 'manifest.json' not in names):
            _fail()
        for item in infos:
            mode = item.external_attr >> 16
            if (item.is_dir() or stat.S_ISLNK(mode) or item.file_size > MAX_FILE
                    or item.flag_bits & 1 or '\\' in item.filename
                    or item.filename.startswith('/') or '..' in item.filename.split('/')
                    or (item.file_size > 1024 * 1024 and item.file_size > 200 * max(item.compress_size, 1))):
                _fail()
        raw_manifest = archive.read('manifest.json')
        if _sha(raw_manifest) != trusted_manifest_sha256:
            _fail()
        manifest = _json(raw_manifest)
        if not isinstance(manifest, dict) or set(manifest) != {'schema', 'version', 'baseline_sha256', 'files'}:
            _fail()
        version, files = manifest['version'], manifest['files']
        if (manifest['schema'] != 'scriptura.research-archive.v1'
                or not isinstance(version, str) or not _VERSION.fullmatch(version)
                or manifest['baseline_sha256'] != trusted_baseline_sha256
                or not isinstance(files, list) or not files):
            _fail()
        if trusted_baseline_version is not None and (
                not isinstance(trusted_baseline_version, str)
                or not _VERSION.fullmatch(trusted_baseline_version)
                or int(version[1:]) <= int(trusted_baseline_version[1:])):
            _fail()
        declared, tables, parsed = set(), set(), []
        for entry in files:
            if not isinstance(entry, dict) or set(entry) != {'path', 'table', 'sha256', 'count'}:
                _fail()
            name, table, digest, count = (entry[k] for k in ('path', 'table', 'sha256', 'count'))
            match = _PATH.fullmatch(name) if isinstance(name, str) else None
            if (not match or table not in TABLES or match.group(1) != table or name in declared
                    or table in tables or not isinstance(digest, str) or not _SHA.fullmatch(digest)
                    or type(count) is not int or count < 0 or count > MAX_ROWS or name not in names):
                _fail()
            declared.add(name); tables.add(table)
            raw = archive.read(name)
            if _sha(raw) != digest:
                _fail()
            lines = raw.splitlines()
            if len(lines) != count or len(parsed) + len(lines) > MAX_ROWS:
                _fail()
            for line in lines:
                if not line.strip() or len(line) > MAX_LINE:
                    parsed.append((table, None)); continue
                try:
                    row = _json(line)
                except (UnicodeError, ValueError, TypeError, RecursionError):
                    row = None
                parsed.append((table, row))
        if set(names) != declared | {'manifest.json'}:
            _fail()
    counts = Counter()
    counts['input_rows'] = len(parsed)
    counts['version_order_unverified'] = int(trusted_baseline_version is None)
    candidates = []
    by_id = defaultdict(list)
    for table, row in parsed:
        if not _schema_valid(table, row):
            counts['quarantined_schema'] += 1
            continue
        idx = len(candidates)
        candidates.append((table, row))
        by_id[row['id']].append(idx)
    invalid = {}
    for ident, indexes in by_id.items():
        if ident in baseline_ids or len(indexes) != 1:
            for idx in indexes:
                invalid[idx] = 'quarantined_id_collision'
    # Index the reverse dependency graph once. A queue then propagates every
    # quarantined row to its dependants in O(rows + reference edges), without
    # repeatedly traversing an adversarially ordered increment. Baseline rows
    # remain immutable. Passage mappings always use exact IDs, never inferred
    # equivalence between different canons or reference schemes.
    dependants = defaultdict(list)
    for idx, (table, row) in enumerate(candidates):
        if idx in invalid:
            continue
        refs = [(row.get(key), target) for key, target in _REQUIRED.get(table, {}).items()]
        refs += [(row[key], target) for key, target in _OPTIONAL.get(table, {}).items() if row.get(key) is not None]
        if table == 'relationships':
            old_pair = ('from_claim_id' in row, 'to_claim_id' in row)
            new_pair = ('subject_id' in row, 'object_id' in row)
            if old_pair == (True, True) and new_pair == (False, False):
                refs.extend(((row['from_claim_id'], 'claims'), (row['to_claim_id'], 'claims')))
            elif new_pair == (True, True) and old_pair == (False, False):
                refs.extend(((row['subject_id'], 'claims'), (row['object_id'], 'claims')))
            else:
                invalid[idx] = 'quarantined_reference'; continue
        if table == 'claims':
            values = row.get('passage_ids')
            if not isinstance(values, list) or not values or any(not isinstance(x, str) or not x for x in values):
                invalid[idx] = 'quarantined_reference'; continue
            refs.extend((value, 'passages') for value in values)
        if table == 'rights' and not any(row.get(k) for k in ('source_id', 'edition_id', 'locator_id')):
            invalid[idx] = 'quarantined_reference'; continue
        for value, target in refs:
            if not isinstance(value, str) or not value:
                invalid[idx] = 'quarantined_reference'; break
            if value in baseline_ids:
                valid = baseline_ids[value] == target
            else:
                matches = by_id.get(value, [])
                valid = len(matches) == 1 and candidates[matches[0]][0] == target
                if valid:
                    dependants[matches[0]].append(idx)
            if not valid:
                invalid[idx] = 'quarantined_reference'; break
        if idx in invalid:
            continue
        # Baseline endpoints have type checks; their richer cross-row
        # semantics require separately supplied trusted baseline evidence.
        if table == 'locators' and row['edition_id'] not in baseline_ids:
            edition = candidates[by_id[row['edition_id']][0]][1]
            if edition.get('source_id') != row['source_id']:
                invalid[idx] = 'quarantined_reference'
    queue = deque(invalid)
    while queue:
        for idx in dependants.get(queue.popleft(), ()):
            if idx not in invalid:
                invalid[idx] = 'quarantined_reference'
                queue.append(idx)
    accepted = defaultdict(list)
    for idx, (table, row) in enumerate(candidates):
        if idx in invalid:
            counts[invalid[idx]] += 1
        else:
            accepted[table].append(deepcopy(row)); counts['accepted_rows'] += 1
            if table == 'locators' and row.get('edition_id') in baseline_ids:
                counts['baseline_semantics_unverified'] += 1
    for key in ('accepted_rows', 'quarantined_schema', 'quarantined_id_collision', 'quarantined_reference'):
        counts.setdefault(key, 0)
    counts.setdefault('baseline_semantics_unverified', 0)
    # A normalized value match is only a duplicate candidate, not proof of
    # work/edition identity. No fields or identifiers enter aggregate output.
    # This independent increment does not inspect baseline bibliography.
    for field in ('title', 'doi'):
        frequencies = Counter()
        for row in accepted.get('sources', []):
            value = row.get(field)
            if isinstance(value, str) and value.strip():
                frequencies[' '.join(unicodedata.normalize('NFKC', value).split()).casefold()] += 1
        counts['duplicate_' + field + '_candidates_within'] = sum(n - 1 for n in frequencies.values() if n > 1)
    return ResearchReceipt(_SEAL, version, dict(accepted), counts)
