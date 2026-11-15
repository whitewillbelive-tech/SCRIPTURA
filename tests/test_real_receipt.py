"""Synthetic regressions for the Work baseline duplicate contract."""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import k37_work_archive_compat as audit
from j2_bridge.candidate_readonly import CandidateError
from k37_bridge.real_receipt import load_d16_archive


class RealReceiptBaselineTests(unittest.TestCase):
    def test_pathlike_inputs_are_passed_as_strings_and_fail_closed(self):
        with patch('k37_bridge.real_receipt.audit.audit', return_value={}) as mock_audit:
            with self.assertRaises(CandidateError):
                load_d16_archive(Path('synthetic-base.zip'), Path('synthetic-delta.zip'))
        self.assertTrue(all(isinstance(value, str) for value in mock_audit.call_args.args))

    def test_identical_baseline_records_are_deduplicated_without_mutation(self):
        row = {'id': 'synthetic-source', 'title': 'SYNTHETIC'}
        prior = {'sources': {'older': [dict(row)], 'newer': [dict(row)]}}
        new = {'sources': [{'id': 'synthetic-new', 'title': 'SYNTHETIC-NEW'}]}
        result = audit.reference_assessment(prior, new)
        self.assertEqual(result['accepted'], 1)
        self.assertEqual(result['quarantined'], 0)
        self.assertEqual(len(prior['sources']['older']), 1)
        self.assertEqual(len(prior['sources']['newer']), 1)

    def test_same_id_different_content_remains_a_conflict(self):
        prior = {'sources': {'older': [{'id': 'synthetic-id', 'title': 'A'}],
                             'newer': [{'id': 'synthetic-id', 'title': 'B'}]}}
        with self.assertRaises(audit.AuditError):
            audit.reference_assessment(prior, {})

    def test_same_id_in_different_tables_remains_a_conflict(self):
        prior = {'sources': {'old': [{'id': 'synthetic-id'}]},
                 'claims': {'old': [{'id': 'synthetic-id'}]}}
        with self.assertRaises(audit.AuditError):
            audit.reference_assessment(prior, {})

    def test_quarantines_bad_increment_and_dependants_only(self):
        baseline = {'sources': {'prior': [{'id': 'prior-source'}]}}
        increment = {
            'sources': [{'id': 'good-source'}, {'id': 'prior-source'}],
            'editions': [{'id': 'good-edition', 'source_id': 'good-source'},
                         {'id': 'bad-edition', 'source_id': 'missing-source'}],
            'locators': [{'id': 'good-locator', 'source_id': 'good-source', 'edition_id': 'good-edition'},
                         {'id': 'bad-locator', 'source_id': 'missing-source', 'edition_id': 'bad-edition'}],
            'passages': [{'id': 'good-passage'}],
            'claims': [{'id': 'good-claim', 'source_id': 'good-source', 'source_locator_id': 'good-locator', 'passage_ids': ['good-passage']},
                       {'id': 'bad-claim', 'source_id': 'missing-source', 'source_locator_id': 'bad-locator', 'passage_ids': ['good-passage']}],
        }
        masks = {}
        result = audit.reference_assessment(baseline, increment, quarantine_positions=masks)
        self.assertEqual(result['quarantined'], 4)
        self.assertEqual(masks['sources'], frozenset({1}))
        self.assertEqual(masks['editions'], frozenset({1}))
        self.assertEqual(masks['locators'], frozenset({1}))
        self.assertEqual(masks['claims'], frozenset({1}))
        self.assertEqual(baseline['sources']['prior'], [{'id': 'prior-source'}])


if __name__ == '__main__':
    unittest.main()
