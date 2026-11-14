"""Synthetic regression for comparison scan cost and projection boundaries."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import j2_private_preview as preview


def dataset(size):
    return {
        'dataset': 'D12',
        'records': [
            {'key': f'd12:claims:{n}', 'stage': 'd12', 'record_kind': 'claim',
             'passages': [{'corpus': 'Bible_1', 'scheme': 'd12_scheme_1',
                           'reference': 'John 1:1'}],
             'summary': 'SYNTHETIC-NOT-APPROVED',
             'attribution': 'individual_opinion'}
            for n in range(1, size + 1)
        ],
        'counts': {}, 'warnings': [],
    }


class ComparisonScalingTests(unittest.TestCase):
    def test_comparison_projects_each_record_only_once(self):
        records = dataset(251)
        with patch.object(preview, '_safe_record', wraps=preview._safe_record) as safe:
            result = preview.compare_passages(records, {
                'stage': ['d12'], 'corpus': ['Bible_1'],
                'scheme': ['d12_scheme_1'], 'reference': ['John 1:1'],
            })
        self.assertEqual(safe.call_count, 251)
        self.assertEqual(len(result['claims']), 251)
        self.assertTrue(all(c['summary'] is None for c in result['claims']))
        self.assertTrue(all(c['relationships'] == [] for c in result['claims']))

    def test_public_candidate_pagination_remains_bounded(self):
        records = dataset(251)
        page = preview.filter_records(records, {'offset': ['100']})
        self.assertEqual(page['total'], 251)
        self.assertEqual(len(page['records']), preview.PAGE_SIZE)
        self.assertEqual(page['records'][0]['key'], 'd12:claims:101')
        last = preview.filter_records(records, {'offset': ['200']})
        self.assertEqual(len(last['records']), 51)
        self.assertTrue(all(c['summary'] is None for c in page['records']))


if __name__ == '__main__':
    unittest.main()
