"""Synthetic incremental receipt regression, independent of private ZIPs."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import k37_work_archive_compat as audit
from k37_bridge.real_receipt import _extend_prior, _quarantine_increment, _receipt_counts


def empty_increment():
    return {table: [] for table in audit.TABLES}


def entry(line, **value):
    return {'line': line, 'value': value}


class IncrementQuarantineTests(unittest.TestCase):
    def test_invalid_earlier_increment_does_not_validate_later_dependant(self):
        baseline = {'sources': {'baseline': [{'id': 'baseline-source'}]}}
        earlier = empty_increment()
        earlier['sources'] = [entry(1, id='valid-source')]
        earlier['editions'] = [entry(1, id='valid-edition', source_id='valid-source'),
                               entry(2, id='invalid-edition', source_id='missing-source')]
        accepted, counts = _quarantine_increment(baseline, earlier)
        self.assertEqual(counts['quarantined'], 1)
        self.assertEqual(len(earlier['editions']), 2)
        self.assertEqual(len(accepted['editions']), 1)
        later = empty_increment()
        later['locators'] = [entry(1, id='valid-locator', source_id='valid-source', edition_id='valid-edition'),
                             entry(2, id='invalid-locator', source_id='valid-source', edition_id='invalid-edition')]
        later_accepted, later_counts = _quarantine_increment(_extend_prior(baseline, accepted), later)
        self.assertEqual(later_counts['quarantined'], 1)
        self.assertEqual(len(later_accepted['locators']), 1)
        self.assertEqual(baseline['sources']['baseline'], [{'id': 'baseline-source'}])

    def test_receipt_distinguishes_input_and_accepted_counts(self):
        d13 = empty_increment()
        d14 = empty_increment()
        d13['sources'] = [entry(1, id='accepted')]
        original_counts = {'d13': {'sources': 2}, 'd14': {'sources': 0}}
        result = _receipt_counts(original_counts, d13, d14)
        self.assertEqual(result['input_counts']['d13']['sources'], 2)
        self.assertEqual(result['d13_sources'], 1)


if __name__ == '__main__':
    unittest.main()
