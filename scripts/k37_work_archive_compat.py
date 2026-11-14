#!/usr/bin/env python3
"""Read-only compatibility audit for pinned SCRIPTURA D13 + D14-D16 Work ZIPs.

Reports bounded numeric/boolean diagnostics only. No research strings, names,
identifiers, source URLs or private file paths are emitted.
NOT a UI adapter, theological review, nor copyright permission.
"""
import collections
import hashlib
import io
import json
import os
import stat
import sys
import zipfile

D13_SHA = 'b109240d6e47df1e6a822fb530285bc4f0bfc39594123c72c90eaf7a277e72fe'
DELTA_SHA = 'd78dd6ce2e467db91ba615ed7bf4a1fe962e137ac43ceafd9bc77ab80c95e800'
MAX_BYTES = 16 * 1024 * 1024
MAX_UNCOMPRESSED = 40 * 1024 * 1024
TABLES = ('sources', 'editions', 'locators', 'passages', 'claims', 'evidence', 'rights')
COUNTS = dict(sources=96, editions=96, locators=98, passages=45, claims=98, evidence=98, rights=864)


class AuditError(Exception):
    pass


def require(ok):
    if not ok:
        raise AuditError('audit_failed')


def secure_zip(blob):
    z = zipfile.ZipFile(io.BytesIO(blob))
    infos = z.infolist()
    require(0 < len(infos) <= 150 and len({i.filename for i in infos}) == len(infos))
    require(sum(i.file_size for i in infos) <= MAX_UNCOMPRESSED)
    for i in infos:
        n = i.filename
        require(not n.startswith('/') and '\\' not in n and '..' not in n.split('/'))
        if i.is_dir():
            continue
        require(not i.flag_bits & 1 and not stat.S_ISLNK(i.external_attr >> 16)
                and i.file_size <= MAX_UNCOMPRESSED)
    require(z.testzip() is None)
    return z


def load_rows(z, key):
    lines = z.read(key).splitlines()
    require(len(lines) <= 5000)
    result = []
    for line in lines:
        require(0 < len(line) < 1000000)
        obj = json.loads(line)
        require(isinstance(obj, dict))
        result.append(obj)
    return result


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
                return all_tables, depth + 1
            require(len(child) == 1)
            data = z.read(child[0])
            require(len(data) <= MAX_BYTES)
    raise AuditError('too_many_layers')


def audit(d13_path, delta_path):
    sizes = [os.path.getsize(p) for p in (d13_path, delta_path)]
    require(all(0 < n <= MAX_BYTES for n in sizes))
    with open(d13_path, 'rb') as f:
        base = f.read()
    with open(delta_path, 'rb') as f:
        delta = f.read()
    require(hashlib.sha256(base).hexdigest() == D13_SHA)
    require(hashlib.sha256(delta).hexdigest() == DELTA_SHA)
    prior, depth = old_layers(base)
    with secure_zip(delta) as z:
        manifest = json.loads(z.read('MANIFEST.json'))
        require(manifest.get('stage') == 'D14_D15_D16')
        require(manifest.get('baseline', {}).get('sha256') == D13_SHA)
        sums = z.read('SHA256SUMS.txt').decode().splitlines()
        require(len(sums) > 10)
        checked = 0
        for line in sums:
            if not line.strip():
                continue
            digest, name = line.split(maxsplit=1)
            name = name.lstrip(' *')
            require(hashlib.sha256(z.read(name)).hexdigest() == digest)
            checked += 1
        new = {table: load_rows(z, f'd14/records/{table}.jsonl') for table in TABLES}
        require(all(len(new[t]) == count for t, count in COUNTS.items()))
        comparisons = load_rows(z, 'd16/records/comparison_sets.jsonl')
        require(len(comparisons) == 80)
        reviews = load_rows(z, 'd15/records/claim_review_events.jsonl')
        require(len(reviews) == 47)
    allids = collections.defaultdict(set)
    for table, stages in prior.items():
        for rows in stages.values():
            for row in rows:
                if isinstance(row.get('id'), str):
                    allids[table].add(row['id'])
    collisions = sum(row.get('id') in allids[table] for table, rows in new.items() for row in rows)
    require(collisions == 0)
    for table, rows in new.items():
        require(len({row.get('id') for row in rows}) == len(rows))
        for row in rows:
            require(isinstance(row.get('id'), str) and row['id'])
            allids[table].add(row['id'])
    failed = 0
    for table, field, target in (
        ('editions', 'source_id', 'sources'),
        ('locators', 'source_id', 'sources'),
        ('locators', 'edition_id', 'editions'),
        ('claims', 'source_id', 'sources'),
        ('claims', 'source_locator_id', 'locators'),
        ('evidence', 'claim_id', 'claims'),
        ('rights', 'edition_id', 'editions'),
    ):
        failed += sum(row.get(field) not in allids[target] for row in new[table])
    for row in new['evidence']:
        failed += int((row.get('source_locator_id') or row.get('locator_id')) not in allids['locators'])
    for row in new['claims']:
        passages = row.get('passage_ids')
        failed += int(not isinstance(passages, list) or not passages
                      or any(x not in allids['passages'] for x in passages))
    require(failed == 0)
    rights = collections.Counter(str(x.get('decision', '')).lower() for x in new['rights'])
    return {
        'd13_anchor_verified': True,
        'd14_d16_anchor_verified': True,
        'lineage_layers_checked': depth,
        'file_hashes_checked': checked,
        'reference_failures': failed,
        'id_collisions': collisions,
        'd14_source_records': len(new['sources']),
        'd14_claim_records': len(new['claims']),
        'd14_passage_records': len(new['passages']),
        'd16_comparison_sets': len(comparisons),
        'd15_review_events': len(reviews),
        'rights_unknown': rights.get('unknown', 0),
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
