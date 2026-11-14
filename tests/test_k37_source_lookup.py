"""Synthetic tests for exact, safe source-to-claim navigation."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from j2_private_preview import filter_records


def dataset():
    return {'dataset': 'D12', 'counts': {}, 'warnings': [], 'records': [
        {'key': 'd12:claims:1', 'stage': 'd12', 'record_kind': 'claim', 'source_key': 'd12:sources:1'},
        {'key': 'd12:claims:2', 'stage': 'd12', 'record_kind': 'claim', 'source_key': 'd12:sources:2'},
        {'key': 'd12:claims:3', 'stage': 'd12', 'record_kind': 'claim', 'source_key': 'SYNTHETIC-RAW-PRIVATE-ID'},
        {'key': 'd12:sources:1', 'stage': 'd12', 'record_kind': 'source'},
    ]}


class SourceLookupTests(unittest.TestCase):
    def test_exact_source_lookup_uses_only_safe_projection(self):
        result = filter_records(dataset(), {'source_key': ['d12:sources:1'], 'record_kind': ['claim']})
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['records'][0]['key'], 'd12:claims:1')
        self.assertNotIn('SYNTHETIC-RAW-PRIVATE-ID', repr(result))

    def test_invalid_or_cross_version_coordinates_are_rejected(self):
        for value in ('SYNTHETIC-RAW-PRIVATE-ID', 'https://example.invalid/x',
                      'd12:claims:1', 'd13:sources:1', 'd12:sources:0', '../d12:sources:1'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                filter_records(dataset(), {'source_key': [value]})

    def test_no_prefix_matches(self):
        result = filter_records(dataset(), {'source_key': ['d12:sources:12'], 'record_kind': ['claim']})
        self.assertEqual(result['total'], 0)


if __name__ == '__main__':
    unittest.main()
