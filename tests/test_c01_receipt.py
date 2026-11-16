"""Synthetic tests for the process-local atomic research catalog."""
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from c01_receipt import ResearchCatalog, snapshot_digest, ReceiptError
from test_k3_receipt import archive, sample

class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.base = {}
        self.anchor = snapshot_digest('D12', self.base)
        self.manager = ResearchCatalog(version='D12', tables=self.base, trusted_snapshot_sha256=self.anchor)

    def test_untrusted_baseline_is_rejected(self):
        with self.assertRaisesRegex(ReceiptError, 'baseline_untrusted'):
            ResearchCatalog(version='D12', tables=self.base, trusted_snapshot_sha256='a' * 64)

    def test_integrates_verified_increment_and_defensively_copies(self):
        blob, digest = archive(baseline=self.anchor)
        event = self.manager.integrate(blob, trusted_manifest_sha256=digest, expected_anchor=self.anchor)
        self.assertEqual(event['counts']['accepted_rows'], 6)
        self.assertEqual(self.manager.snapshot()['version'], 'D13')
        copy = self.manager.snapshot()
        copy['tables']['sources'].clear()
        self.assertEqual(len(self.manager.snapshot()['tables']['sources']), 1)
        self.assertNotIn('synthetic:source', repr(self.manager))

    def test_invalid_input_never_changes_baseline(self):
        blob, digest = archive(baseline=self.anchor)
        before = self.manager.snapshot()
        with self.assertRaises(ReceiptError):
            self.manager.integrate(blob, trusted_manifest_sha256='a' * 64, expected_anchor=self.anchor)
        self.assertEqual(self.manager.snapshot(), before)
        self.assertEqual(self.manager.history(), [])

    def test_quarantined_row_and_dependants_do_not_remove_siblings(self):
        tables = sample()
        tables['sources'].append({'id':'synthetic:other', 'title':'Other'})
        tables['editions'][0]['source_id'] = 'synthetic:missing'
        blob, digest = archive(tables, baseline=self.anchor)
        result = self.manager.integrate(blob, trusted_manifest_sha256=digest, expected_anchor=self.anchor)
        self.assertGreater(result['counts']['quarantined_reference'], 0)
        self.assertEqual(len(self.manager.snapshot()['tables']['sources']), 2)
        self.assertNotIn('claims', self.manager.snapshot()['tables'])

    def test_stale_generation_is_rejected(self):
        blob, digest = archive(baseline=self.anchor)
        self.manager.integrate(blob, trusted_manifest_sha256=digest, expected_anchor=self.anchor)
        before = self.manager.snapshot()
        with self.assertRaisesRegex(ReceiptError, 'baseline_changed'):
            self.manager.integrate(blob, trusted_manifest_sha256=digest, expected_anchor=self.anchor)
        self.assertEqual(before, self.manager.snapshot())

    def test_entirely_quarantined_increment_does_not_advance_version(self):
        blob, digest = archive({'sources': [{'id': 'synthetic:invalid'}]}, baseline=self.anchor)
        with self.assertRaisesRegex(ReceiptError, 'increment_fully_quarantined'):
            self.manager.integrate(blob, trusted_manifest_sha256=digest, expected_anchor=self.anchor)
        self.assertEqual(self.manager.snapshot()['version'], 'D12')
        self.assertEqual(self.manager.history(), [])

    def test_parallel_writers_have_only_one_winner(self):
        import c01_receipt
        original, barrier = c01_receipt.receive, threading.Barrier(2)
        blob, digest = archive(baseline=self.anchor)
        outcomes = []
        def blocked(*args, **kwargs):
            result = original(*args, **kwargs)
            barrier.wait(timeout=5)
            return result
        def run():
            try:
                self.manager.integrate(blob, trusted_manifest_sha256=digest, expected_anchor=self.anchor)
                outcomes.append('ok')
            except ReceiptError as exc:
                outcomes.append(str(exc))
        with patch.object(c01_receipt, 'receive', side_effect=blocked):
            threads = [threading.Thread(target=run) for _ in range(2)]
            for thread in threads: thread.start()
            for thread in threads: thread.join(10)
        self.assertCountEqual(outcomes, ['ok', 'baseline_changed'])
        self.assertEqual(len(self.manager.history()), 1)

if __name__ == '__main__': unittest.main()
