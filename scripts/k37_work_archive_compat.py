#!/usr/bin/env python3
"""Read-only compatibility audit for pinned SCRIPTURA D13 + D14-D16 Work ZIPs.

Reports bounded numeric/boolean diagnostics only. No research strings, names,
identifiers, source URLs or private file paths are emitted.
NOT a UI adapter, theological review, nor copyright permission.
"""
import collections
from collections.abc import Mapping, Sequence
import hashlib
import hmac
import io
import json
import os
import re
import stat
import sys
import zipfile

D13_SHA = 'b109240d6e47df1e6a822fb530285bc4f0bfc39594123c72c90eaf7a277e72fe'
DELTA_SHA = 'd78dd6ce2e467db91ba615ed7bf4a1fe962e137ac43ceafd9bc77ab80c95e800'
MAX_BYTES = 16 * 1024 * 1024
MAX_UNCOMPRESSED = 40 * 1024 * 1024
MAX_COMPRESSION_RATIO = 250
TABLES = ('sources', 'editions', 'locators', 'passages', 'claims', 'evidence', 'rights')
COUNTS = dict(sources=96, editions=96, locators=98, passages=45, claims=98, evidence=98, rights=864)
EXPECTED_CHECKSUMS = 45


class AuditError(Exception):
    pass


class PrivateRows(Sequence):
    """Opaque carrier to reduce accidental bulk repr/JSON disclosure.

    Explicit indexing/iteration still exposes private values to trusted local
    code, so this object is not a sandbox or a public API.
    """
    __slots__ = ('__rows',)

    def __init__(self, rows):
        self.__rows = rows

    def __len__(self):
        return len(self.__rows)

    def __getitem__(self, index):
        return self.__rows[index]

    def __repr__(self):
        return '<PrivateRows redacted>'


class PrivatePrior(Mapping):
    """Opaque top-level lineage carrier; explicit values remain private."""
    __slots__ = ('__tables',)

    def __init__(self, tables):
        self.__tables = tables

    def __getitem__(self, key):
        try:
            return self.__tables[key]
        except (KeyError, TypeError):
            raise KeyError('private_key_unavailable') from None

    def __iter__(self):
        return iter(self.__tables)

    def __len__(self):
        return len(self.__tables)

    def __repr__(self):
        return '<PrivatePrior redacted>'


def require(ok):
    if not ok:
        raise AuditError('audit_failed')


def secure_zip(blob):
    z = zipfile.ZipFile(io.BytesIO(blob))
    infos = z.infolist()
    require(0 < len(infos) <= 150 and len({i.filename for i in infos}) == len(infos))
    require(sum(i.file_size for i in infos) <= MAX_UNCOMPRESSED)
    for i in infos:
        # ZipInfo normalizes platform separators on Windows. Validate the raw
        # archive name too, before that normalization can hide a backslash.
        for n in (i.orig_filename, i.filename):
            require(not any(ord(ch) < 32 or ord(ch) == 127 for ch in n)
                    and not n.startswith('/') and '\\' not in n and not re.match(r'^[A-Za-z]:', n)
                    and not any(part in ('.', '..') for part in n.split('/')))
        if i.is_dir():
            continue
        require(not i.flag_bits & 1 and not stat.S_ISLNK(i.external_attr >> 16)
                and i.file_size <= MAX_UNCOMPRESSED
                and (i.file_size == 0 or (i.compress_size > 0
                     and i.file_size <= i.compress_size * MAX_COMPRESSION_RATIO)))
    require(z.testzip() is None)
    return z


def read_local_unchanged(path):
    """Read a bounded local regular file; refuse changed files and UNC/URLs."""
    try:
        require(isinstance(path, str) and path and not path.startswith(('\\\\', '//', '\\/', '/\\'))
                and not re.match(r'^[A-Za-z][A-Za-z0-9+.-]*://', path))
        before = os.stat(path)
        require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= MAX_BYTES)
        fingerprint = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        with open(path, 'rb') as stream:
            require(fingerprint(os.fstat(stream.fileno())) == fingerprint(before))
            data = stream.read(MAX_BYTES + 1)
            require(fingerprint(os.fstat(stream.fileno())) == fingerprint(before))
        require(fingerprint(os.stat(path)) == fingerprint(before) and len(data) == before.st_size and len(data) <= MAX_BYTES)
        return data
    except Exception:
        raise AuditError('audit_failed') from None


def load_rows(z, key):
    lines = z.read(key).splitlines()
    require(len(lines) <= 5000)
    result = []
    for line in lines:
        require(0 < len(line) < 1000000)
        obj = json.loads(line)
        require(isinstance(obj, dict))
        result.append(obj)
    return PrivateRows(result)


def validate_checksums(z, lines, *, expected_count=EXPECTED_CHECKSUMS, required=()):
    """Validate distinct checksum entries without emitting filenames or hashes.

    The externally pinned ZIP digest authenticates this manifest; a checksum
    list by itself never establishes trust. Required data members must occur in
    the list, and duplicate, malformed or unsafe entries fail closed.
    """
    require(isinstance(lines, list))
    seen = set()
    for line in lines:
        require(isinstance(line, str))
        if not line.strip():
            continue
        match = re.fullmatch(r'([0-9a-fA-F]{64})[ \t]+\*?([^\r\n]+)', line)
        require(match is not None)
        digest, name = match.groups()
        require(name and not name.startswith('/') and '\\' not in name
                and not any(part in ('', '.', '..') for part in name.split('/')))
        require(name not in seen)
        seen.add(name)
        try:
            payload = z.read(name)
        except Exception:
            raise AuditError('audit_failed') from None
        require(hashlib.sha256(payload).hexdigest() == digest.lower())
    require(len(seen) == expected_count and set(required).issubset(seen))
    return len(seen)


def reference_assessment(prior, new):
    """Classify invalid increments by fixed labels; never return identifiers.

    This detects graph errors without changing prior rows. It does not certify
    source claims, rights, text, a legal permission, or unseen Work schemas.
    """
    prior_index = {}
    global_prior = set()
    for table, stages in prior.items():
        prior_index[table] = {}
        for rows in stages.values():
            for row in rows:
                ident = row.get('id') if isinstance(row, dict) else None
                if isinstance(ident, str) and ident:
                    require(ident not in global_prior)
                    global_prior.add(ident)
                    prior_index[table][ident] = row
    indexes = {table: dict(prior_index.get(table, {})) for table in TABLES}
    rejected = {table: set() for table in TABLES}
    reasons = collections.Counter()
    global_new = {}
    ambiguous_ids = set()
    for table, rows in new.items():
        require(table in indexes and isinstance(rows, (list, PrivateRows)))
        for pos, row in enumerate(rows):
            ident = row.get('id') if isinstance(row, dict) else None
            if not isinstance(ident, str) or not ident:
                rejected[table].add(pos); reasons['invalid_id'] += 1
            elif ident in global_prior or ident in global_new:
                rejected[table].add(pos); reasons['id_collision'] += 1
                ambiguous_ids.add(ident)
                if ident in global_new:
                    old_table, old_pos, old_row = global_new[ident]
                    if old_pos not in rejected[old_table]:
                        rejected[old_table].add(old_pos); reasons['id_collision'] += 1
                        if indexes[old_table].get(ident) is old_row:
                            del indexes[old_table][ident]
            else:
                global_new[ident] = (table, pos, row)
                indexes[table][ident] = row

    # These record classes form a dependency DAG. Process dependencies before
    # dependants in one pass rather than rescanning hostile input quadratically.
    relations = {
        'editions': (('source_id', 'sources'),),
        'locators': (('source_id', 'sources'), ('edition_id', 'editions')),
        'claims': (('source_id', 'sources'), ('source_locator_id', 'locators')),
        'evidence': (('claim_id', 'claims'),),
        'rights': (('edition_id', 'editions'),),
    }
    def has_ref(value, table):
        return isinstance(value, str) and bool(value) and value not in ambiguous_ids and value in indexes[table]

    for table in ('sources', 'passages', 'editions', 'locators', 'claims', 'evidence', 'rights'):
        rows = new.get(table, [])
        for pos, row in enumerate(rows):
            if pos in rejected[table]:
                continue
            missing = any(not has_ref(row.get(field), target)
                          for field, target in relations.get(table, ()))
            if table == 'evidence':
                missing |= not has_ref(row.get('source_locator_id') or row.get('locator_id'), 'locators')
            if table == 'claims':
                passages = row.get('passage_ids')
                missing |= not isinstance(passages, list) or not passages or any(not has_ref(p, 'passages') for p in passages)
            conflict = False
            if not missing and table == 'locators':
                edition = indexes['editions'][row['edition_id']]
                conflict = edition.get('source_id') != row.get('source_id')
            if not missing and table == 'claims':
                locator = indexes['locators'][row['source_locator_id']]
                conflict = locator.get('source_id') != row.get('source_id')
            if missing or conflict:
                rejected[table].add(pos)
                ident = row.get('id')
                if indexes[table].get(ident) is row:
                    del indexes[table][ident]
                reasons['reference_missing' if missing else 'source_chain_conflict'] += 1
    return {'accepted': sum(len(rows) - len(rejected[t]) for t, rows in new.items()),
            'quarantined': sum(map(len, rejected.values())),
            'id_collision': reasons['id_collision'], 'invalid_id': reasons['invalid_id'],
            'reference_missing': reasons['reference_missing'],
            'source_chain_conflict': reasons['source_chain_conflict']}


def old_layers(baseline):
    all_tables = collections.defaultdict(dict)
    data = baseline
    for depth in range(20):
        with secure_zip(data) as z:
            for name in z.namelist():
                if '/records/' not in name or not name.endswith('.jsonl'):
                    continue
                stage, tablepath = name.split('/records/', 1)
                table = tablepath[:-6]
                if table in TABLES:
                    all_tables[table][str(depth) + ':' + stage] = load_rows(z, name)
            child = [n for n in z.namelist() if n.startswith('baseline/') and n.endswith('.zip')]
            if not child:
                return PrivatePrior(dict(all_tables)), depth + 1
            require(len(child) == 1)
            data = z.read(child[0])
            require(len(data) <= MAX_BYTES)
    raise AuditError('too_many_layers')


def audit(d13_path, delta_path):
    base = read_local_unchanged(d13_path)
    delta = read_local_unchanged(delta_path)
    require(hmac.compare_digest(hashlib.sha256(base).hexdigest(), D13_SHA))
    require(hmac.compare_digest(hashlib.sha256(delta).hexdigest(), DELTA_SHA))
    prior, depth = old_layers(base)
    with secure_zip(delta) as z:
        manifest = json.loads(z.read('MANIFEST.json'))
        require(manifest.get('stage') == 'D14_D15_D16')
        require(manifest.get('baseline', {}).get('sha256') == D13_SHA)
        sums = z.read('SHA256SUMS.txt').decode().splitlines()
        required = [f'd14/records/{table}.jsonl' for table in TABLES]
        required += ['d16/records/comparison_sets.jsonl', 'd15/records/claim_review_events.jsonl']
        # Every stage record in this archive must be covered; this does not
        # claim that unrelated documents or the whole ZIP are in the list.
        required += [name for name in z.namelist()
                     if re.fullmatch(r'd1[456]/records/.+\.jsonl', name)]
        checked = validate_checksums(z, sums, required=required)
        new = {table: load_rows(z, f'd14/records/{table}.jsonl') for table in TABLES}
        require(all(len(new[t]) == count for t, count in COUNTS.items()))
        comparisons = load_rows(z, 'd16/records/comparison_sets.jsonl')
        require(len(comparisons) == 80)
        reviews = load_rows(z, 'd15/records/claim_review_events.jsonl')
        require(len(reviews) == 47)
    assessment = reference_assessment(prior, new)
    d13_count = lambda table: sum(len(rows) for stage, rows in prior.get(table, {}).items()
                                   if stage.rsplit(':', 1)[-1].rstrip('/').split('/')[-1].lower() == 'd13')
    rights = collections.Counter(str(x.get('decision', '')).lower() for x in new['rights'])
    return {
        'd13_anchor_verified': True,
        'd14_d16_anchor_verified': True,
        'lineage_layers_checked': depth,
        'file_hashes_checked': checked,
        'lineage_expected_verified': depth == 14,
        'd13_source_records': d13_count('sources'),
        'd13_claim_records': d13_count('claims'),
        'd13_expected_counts_verified': d13_count('sources') == 47 and d13_count('claims') == 47,
        'reference_failures': assessment['reference_missing'] + assessment['source_chain_conflict'],
        'id_collisions': assessment['id_collision'],
        'invalid_id_records': assessment['invalid_id'],
        'quarantined_records': assessment['quarantined'],
        'accepted_records': assessment['accepted'],
        'checked_reference_integrity': assessment['quarantined'] == 0,
        'd14_source_records': len(new['sources']),
        'd14_claim_records': len(new['claims']),
        'd14_passage_records': len(new['passages']),
        'd16_comparison_sets': len(comparisons),
        'd15_review_events': len(reviews),
        'rights_unknown': rights.get('unknown', 0),
        # The two table schemas are not specified by the recovered audit; a
        # row count alone cannot prove their references or semantics.
        'd15_review_links_verified': False,
        'd16_comparison_links_verified': False,
        'source_and_claim_data_shown': False,
        'actual_ui_import_complete': False,
    }


if __name__ == '__main__':
    try:
        require(len(sys.argv) == 3)
        result = audit(sys.argv[1], sys.argv[2])
        print(json.dumps(result, sort_keys=True))
    except Exception:
        print('{"audit_pass":false,"reason":"invalid_or_incompatible_archives"}')
        raise SystemExit(1)
