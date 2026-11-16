"""Synthetic-only tests for format routing and separate trust lanes."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from c01_receipt import ResearchCatalog, snapshot_digest, ReceiptError
from c01_receipt_adapter import receive_increment
from test_k3_receipt import archive

class ReceiptAdapterTests(unittest.TestCase):
    def test_generic_receipt_requires_catalog_and_no_legacy_preview(self):
        anchor = snapshot_digest('D12', {})
        catalog = ResearchCatalog(version='D12', tables={}, trusted_snapshot_sha256=anchor)
        blob, manifest = archive(baseline=anchor)
        result = receive_increment('jsonl_v1', catalog=catalog, blob=blob,
                                   trusted_manifest_sha256=manifest, expected_anchor=anchor)
        self.assertEqual(result.aggregate()['counts']['accepted_rows'], 6)
        with self.assertRaisesRegex(ReceiptError, 'preview_not_available'):
            result.local_preview()
        self.assertNotIn('synthetic:source', repr(result))

    def test_legacy_only_delegates_to_existing_filtered_preview(self):
        receipt = {k: 0 for k in ('d13_sources', 'd13_claims', 'd14_sources', 'd14_claims',
                                   'd14_passages', 'comparison_sets', 'd13_quarantined', 'd14_quarantined')}
        preview = {'d16_receipt': receipt, 'private': 'SYNTHETIC_SECRET'}
        with patch('k37_bridge.real_receipt.load_d16_archive', return_value=preview) as load:
            result = receive_increment('legacy_work_d13_d16', base_path='synthetic-a', delta_path='synthetic-b')
        load.assert_called_once_with('synthetic-a', 'synthetic-b')
        self.assertEqual(result.local_preview(), preview)
        self.assertNotIn('private', result.aggregate())
        self.assertNotIn('SYNTHETIC_SECRET', repr(result))

    def test_legacy_failure_is_fixed_code_and_no_fallback(self):
        with patch('k37_bridge.real_receipt.load_d16_archive', side_effect=ValueError('SYNTHETIC_SECRET')):
            with self.assertRaisesRegex(ReceiptError, '^legacy_receipt_invalid$'):
                receive_increment('legacy_work_d13_d16', base_path='synthetic-a', delta_path='synthetic-b')
        with self.assertRaisesRegex(ReceiptError, '^adapter_format_unsupported$'):
            receive_increment('unrecognized')

    def test_modes_cannot_be_combined(self):
        with self.assertRaisesRegex(ReceiptError, '^adapter_invalid$'):
            receive_increment('legacy_work_d13_d16', blob=b'x', base_path='a', delta_path='b')
        with self.assertRaisesRegex(ReceiptError, '^adapter_invalid$'):
            receive_increment('jsonl_v1', base_path='a')

if __name__ == '__main__': unittest.main()
