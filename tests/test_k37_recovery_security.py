"""Independent adversarial checks using synthetic inputs only."""
import hashlib
import io
import json
from pathlib import Path
import stat
import sys
import tempfile
import traceback
import unittest
from unittest.mock import patch
import warnings
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import k37_work_archive_compat as compat


def archive(entries, *, compression=zipfile.ZIP_STORED):
    out = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', UserWarning)
        with zipfile.ZipFile(out, 'w', compression=compression) as z:
            for name, data in entries:
                z.writestr(name, data)
    return out.getvalue()


def manifest(entries):
    return [hashlib.sha256(value).hexdigest() + '  ' + name for name, value in entries]


def jsonlines(items):
    return b''.join(json.dumps(item).encode() + b'\n' for item in items)


def synthetic_pair(*, incomplete=False, collision=False, bad_baseline=False, unsigned_extra=False):
    base = archive([('d13/records/sources.jsonl', jsonlines([{'id': 'synthetic-old-source'}])),
                    ('d13/records/claims.jsonl', jsonlines([{'id': 'synthetic-old-claim'}]))])
    base_sha = hashlib.sha256(base).hexdigest()
    source_id = 'synthetic-source'
    rows = {
        'sources': [{'id': source_id}],
        'editions': [{'id': 'synthetic-edition', 'source_id': source_id}],
        'locators': [{'id': 'synthetic-locator', 'source_id': source_id, 'edition_id': 'synthetic-edition'}],
        'passages': [{'id': source_id if collision else 'synthetic-passage'}],
        'claims': [{'id': 'synthetic-claim', 'source_id': source_id,
                    'source_locator_id': 'synthetic-locator', 'passage_ids': ['synthetic-passage']}],
        'evidence': [{'id': 'synthetic-evidence', 'claim_id': 'synthetic-claim', 'source_locator_id': 'synthetic-locator'}],
        'rights': [{'id': 'synthetic-right', 'edition_id': 'synthetic-edition', 'decision': 'unknown'}],
    }
    entries = [(f'd14/records/{table}.jsonl', jsonlines(value)) for table, value in rows.items()]
    entries += [('d16/records/comparison_sets.jsonl', jsonlines([{'id': f'synthetic-comparison-{n}'} for n in range(80)])),
                ('d15/records/claim_review_events.jsonl', jsonlines([{'id': f'synthetic-review-{n}'} for n in range(47)]))]
    entries += [(f'synthetic/filler-{n}.txt', str(n).encode()) for n in range(36)]
    checksums = manifest(entries[:-1] if incomplete else entries)
    if unsigned_extra:
        entries.append(('d16/records/synthetic-unsigned.jsonl', b'{}\n'))
    entries += [('SHA256SUMS.txt', ('\n'.join(checksums) + '\n').encode()),
                ('MANIFEST.json', json.dumps({'stage': 'D14_D15_D16', 'baseline': {'sha256': '0' * 64 if bad_baseline else base_sha}}).encode())]
    return base, archive(entries)


class RecoverySecurityTests(unittest.TestCase):
    def test_private_carriers_do_not_bulk_render_or_json_encode(self):
        sentinel = 'SYNTHETIC_PRIVATE_SENTINEL_92'
        private_rows = compat.PrivateRows([{'text': sentinel}])
        private_prior = compat.PrivatePrior({'sources': {'d13': private_rows}})
        for value in (private_rows, private_prior):
            with self.subTest(carrier=type(value).__name__):
                self.assertNotIn(sentinel, repr(value))
                self.assertNotIn(sentinel, str(value))
                with self.assertRaises(TypeError) as caught:
                    json.dumps(value)
                self.assertNotIn(sentinel, ''.join(traceback.format_exception(caught.exception)))
        # Explicit reads remain possible and are not a sandbox boundary.
        self.assertEqual(private_rows[0]['text'], sentinel)
        with self.assertRaises(KeyError) as caught:
            private_prior[sentinel]
        self.assertNotIn(sentinel, ''.join(traceback.format_exception(caught.exception)))

    def test_loader_returns_opaque_rows_for_synthetic_sentinel(self):
        sentinel = 'SYNTHETIC_PRIVATE_SENTINEL_92'
        blob = archive([('records/synthetic.jsonl', jsonlines([{'text': sentinel}]))])
        with compat.secure_zip(blob) as z:
            rows = compat.load_rows(z, 'records/synthetic.jsonl')
            self.assertIsInstance(rows, compat.PrivateRows)
            self.assertNotIn(sentinel, str(rows))
            self.assertNotIn(sentinel, repr(rows))
            with self.assertRaises(TypeError):
                json.dumps(rows)

    def test_45_unique_digests_and_required_coverage(self):
        rows = [(f'records/synthetic-{n}.jsonl', str(n).encode()) for n in range(45)]
        with compat.secure_zip(archive(rows)) as z:
            self.assertEqual(compat.validate_checksums(z, manifest(rows), required=(rows[0][0],)), 45)
            with self.assertRaises(compat.AuditError):
                compat.validate_checksums(z, manifest(rows[:-1]), required=(rows[0][0],))
            with self.assertRaises(compat.AuditError):
                compat.validate_checksums(z, manifest(rows) + [manifest(rows)[0]])
            with self.assertRaises(compat.AuditError):
                compat.validate_checksums(z, manifest(rows), required=('records/missing.jsonl',))

    def test_checksum_mismatch_and_path_escape_rejected(self):
        rows = [('records/synthetic.jsonl', b'synthetic')]
        with compat.secure_zip(archive(rows)) as z:
            with self.assertRaises(compat.AuditError):
                compat.validate_checksums(z, manifest([('records/synthetic.jsonl', b'different')]), expected_count=1)
            with self.assertRaises(compat.AuditError):
                compat.validate_checksums(z, [hashlib.sha256(b'synthetic').hexdigest() + '  ../synthetic'], expected_count=1)

    def test_zip_slip_and_duplicate_names_rejected(self):
        for rows in ([('../synthetic', b'x')], [('x', b'a'), ('x', b'b')]):
            with self.subTest(kind=len(rows)):
                with self.assertRaises(compat.AuditError):
                    compat.secure_zip(archive(rows))
        # writestr normalizes backslashes on Windows. Construct the malformed
        # local and central directory names at the byte level on every OS.
        blob = archive([('a/b', b'x')])
        self.assertEqual(blob.count(b'a/b'), 2)
        malformed = blob.replace(b'a/b', b'a\\b')
        for separator in ('/', '\\'):
            with self.subTest(separator=separator), patch.object(zipfile.os, 'sep', separator):
                with self.assertRaises(compat.AuditError):
                    compat.secure_zip(malformed)
        # NUL is also normalized by ZipInfo, so validate the raw member name.
        with self.assertRaises(compat.AuditError):
            compat.secure_zip(blob.replace(b'a/b', b'a\x00b'))

    def test_symlink_and_excessive_compression_rejected(self):
        out = io.BytesIO()
        with zipfile.ZipFile(out, 'w') as z:
            item = zipfile.ZipInfo('synthetic-link')
            item.create_system = 3
            item.external_attr = (stat.S_IFLNK | 0o777) << 16
            z.writestr(item, 'synthetic-target')
        with self.assertRaises(compat.AuditError):
            compat.secure_zip(out.getvalue())
        with self.assertRaises(compat.AuditError):
            compat.secure_zip(archive([('synthetic', b'0' * 1000000)], compression=zipfile.ZIP_DEFLATED))

    def test_remote_paths_and_missing_file_are_not_read(self):
        for value in ('https://example.invalid/private', '//synthetic/share', r'\\synthetic\share'):
            with self.subTest(kind=len(value)):
                with self.assertRaises(compat.AuditError):
                    compat.read_local_unchanged(value)
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'sample.zip'
            path.write_bytes(b'synthetic')
            self.assertEqual(compat.read_local_unchanged(str(path)), b'synthetic')

    def test_changed_file_identity_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'sample.zip'
            path.write_bytes(b'synthetic')
            initial = path.stat()
            with patch.object(compat.os, 'stat', side_effect=[initial, object()]):
                with self.assertRaises(compat.AuditError):
                    compat.read_local_unchanged(str(path))

    def test_cross_table_collision_quarantines_both_and_dependants(self):
        new = {'sources': [{'id': 'synthetic-duplicate'}],
               'passages': [{'id': 'synthetic-duplicate'}],
               'editions': [{'id': 'synthetic-edition', 'source_id': 'synthetic-duplicate'}]}
        result = compat.reference_assessment({}, new)
        self.assertEqual(result['accepted'], 0)
        self.assertEqual(result['quarantined'], 3)
        self.assertEqual(result['id_collision'], 2)
        self.assertEqual(result['reference_missing'], 1)

    def test_cross_source_conflict_quarantines_dependants_only(self):
        prior = {'sources': {'old': [{'id': 'synthetic-source-a'}, {'id': 'synthetic-source-b'}]},
                 'editions': {'old': [{'id': 'synthetic-edition', 'source_id': 'synthetic-source-a'}]}}
        new = {'locators': [{'id': 'synthetic-locator', 'source_id': 'synthetic-source-b', 'edition_id': 'synthetic-edition'}],
               'rights': [{'id': 'synthetic-right', 'edition_id': 'synthetic-edition'}]}
        result = compat.reference_assessment(prior, new)
        self.assertEqual(result['accepted'], 1)
        self.assertEqual(result['quarantined'], 1)
        self.assertEqual(result['source_chain_conflict'], 1)
        self.assertEqual(len(prior['sources']['old']), 2)

    def test_conflicting_baseline_id_does_not_silently_select_old_record(self):
        prior = {'sources': {'old': [{'id': 'synthetic-existing'}]}}
        new = {'sources': [{'id': 'synthetic-existing'}, {'id': 'synthetic-unrelated'}],
               'editions': [{'id': 'synthetic-edition', 'source_id': 'synthetic-existing'}]}
        result = compat.reference_assessment(prior, new)
        self.assertEqual(result['accepted'], 1)
        self.assertEqual(result['quarantined'], 2)
        self.assertEqual(prior['sources']['old'][0]['id'], 'synthetic-existing')

    def test_malformed_unhashable_reference_is_quarantined(self):
        result = compat.reference_assessment({}, {'editions': [{'id': 'synthetic-edition', 'source_id': ['synthetic-wrong-type']}]})
        self.assertEqual(result['quarantined'], 1)
        self.assertEqual(result['accepted'], 0)

    def test_audit_entrypoint_uses_manifest_and_quarantine(self):
        for incomplete, collision in ((False, False), (True, False), (False, True)):
            base, delta = synthetic_pair(incomplete=incomplete, collision=collision)
            with self.subTest(incomplete=incomplete, collision=collision), tempfile.TemporaryDirectory() as root:
                base_path, delta_path = Path(root) / 'base.zip', Path(root) / 'delta.zip'
                base_path.write_bytes(base)
                delta_path.write_bytes(delta)
                with patch.object(compat, 'D13_SHA', hashlib.sha256(base).hexdigest()), \
                     patch.object(compat, 'DELTA_SHA', hashlib.sha256(delta).hexdigest()), \
                     patch.object(compat, 'COUNTS', {table: 1 for table in compat.TABLES}):
                    if incomplete:
                        with self.assertRaises(compat.AuditError):
                            compat.audit(str(base_path), str(delta_path))
                    else:
                        result = compat.audit(str(base_path), str(delta_path))
                        self.assertEqual(result['file_hashes_checked'], 45)
                        self.assertFalse(result['actual_ui_import_complete'])
                        self.assertFalse(result['d16_comparison_links_verified'])
                        self.assertEqual(result['quarantined_records'] > 0, collision)

    def test_entrypoint_rejects_wrong_baseline_even_with_correct_zip_anchors(self):
        base, delta = synthetic_pair(bad_baseline=True)
        with tempfile.TemporaryDirectory() as root:
            base_path, delta_path = Path(root) / 'base.zip', Path(root) / 'delta.zip'
            base_path.write_bytes(base)
            delta_path.write_bytes(delta)
            with patch.object(compat, 'D13_SHA', hashlib.sha256(base).hexdigest()), \
                 patch.object(compat, 'DELTA_SHA', hashlib.sha256(delta).hexdigest()), \
                 patch.object(compat, 'COUNTS', {table: 1 for table in compat.TABLES}):
                with self.assertRaises(compat.AuditError):
                    compat.audit(str(base_path), str(delta_path))

    def test_entrypoint_rejects_unchecksummed_extra_record(self):
        base, delta = synthetic_pair(unsigned_extra=True)
        with tempfile.TemporaryDirectory() as root:
            base_path, delta_path = Path(root) / 'base.zip', Path(root) / 'delta.zip'
            base_path.write_bytes(base)
            delta_path.write_bytes(delta)
            with patch.object(compat, 'D13_SHA', hashlib.sha256(base).hexdigest()), \
                 patch.object(compat, 'DELTA_SHA', hashlib.sha256(delta).hexdigest()), \
                 patch.object(compat, 'COUNTS', {table: 1 for table in compat.TABLES}):
                with self.assertRaises(compat.AuditError):
                    compat.audit(str(base_path), str(delta_path))


if __name__ == '__main__':
    unittest.main()
