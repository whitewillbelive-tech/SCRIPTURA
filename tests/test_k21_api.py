"""Synthetic regression for exposing only K-2's vetted summary index."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from j2_private_preview import compare_passages, filter_records
from k2_bridge.receipt import _SummaryIndex


def data():
    return {
        'dataset': 'D12', 'counts': {}, 'warnings': [],
        'records': [
            {'key': 'd12:claims:1', 'stage': 'd12', 'record_kind': 'claim',
             'summary': 'SYNTHETIC-RAW-DENY',
             'passages': [{'corpus': 'Bible_1', 'scheme': 'd12_scheme_1', 'reference': 'John 1:1'}]},
            {'key': 'd12:claims:2', 'stage': 'd12', 'record_kind': 'claim',
             'summary': 'SYNTHETIC-RAW-DENY',
             'passages': [{'corpus': 'Bible_1', 'scheme': 'd12_scheme_1', 'reference': 'John 1:1'}]},
            {'key': 'd12:sources:1', 'stage': 'd12', 'record_kind': 'source',
             'summary': 'SYNTHETIC-RAW-DENY'},
        ],
    }


class CandidateSummaryTests(unittest.TestCase):
    def test_only_sealed_claim_summary_and_same_comparison_policy(self):
        dataset = data()
        dataset['_k2_summary_index'] = _SummaryIndex({
            'd12:claims:1': 'SYNTHETIC-REVIEWED-SUMMARY',
            'd12:sources:1': 'SYNTHETIC-SOURCE-MUST-NOT-SHOW',
        })
        result = filter_records(dataset, {})
        self.assertEqual(result['summary_projection'], 'k2-reviewed-summary')
        first, second, source = result['records']
        self.assertEqual(first['summary'], 'SYNTHETIC-REVIEWED-SUMMARY')
        self.assertEqual(first['summary_status'], 'recorded_unverified')
        self.assertIsNone(second['summary'])
        self.assertEqual(second['summary_status'], 'pending_review')
        self.assertIsNone(source['summary'])
        comparison = compare_passages(dataset, {'stage': ['d12'], 'corpus': ['Bible_1'],
                                                'scheme': ['d12_scheme_1'], 'reference': ['John 1:1']})
        self.assertEqual(comparison['claims'][0]['summary'], first['summary'])
        self.assertEqual(comparison['claims'][1]['summary_status'], second['summary_status'])

    def test_raw_and_forged_index_cannot_authorize(self):
        dataset = data()
        dataset['_k2_summary_index'] = {'d12:claims:1': 'SYNTHETIC-FORGED'}
        result = filter_records(dataset, {})
        self.assertTrue(all(row['summary'] is None for row in result['records']))
        self.assertNotIn('SYNTHETIC-RAW-DENY', repr(result))
        self.assertNotIn('SYNTHETIC-FORGED', repr(result))

    def test_old_dataset_and_search_do_not_expose_summary(self):
        dataset = data()
        dataset['_k2_summary_index'] = _SummaryIndex({'d12:claims:1': 'SYNTHETIC-REVIEWED-SUMMARY'})
        self.assertEqual(filter_records(dataset, {'q': ['SYNTHETIC-REVIEWED-SUMMARY']})['total'], 0)
        dataset['dataset'] = 'D10'
        result = filter_records(dataset, {})
        self.assertIsNone(result['summary_projection'])
        self.assertNotIn('SYNTHETIC-REVIEWED-SUMMARY', repr(result))


if __name__ == '__main__':
    unittest.main()
