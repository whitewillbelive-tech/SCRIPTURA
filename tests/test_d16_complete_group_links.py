"""Synthetic coverage for every address in a comparison group."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from k37_bridge.d16_groups import build_d16_index, d16_summary, get_d16_sets
from test_d16_groups import fixture


class CompleteGroupLinksTest(unittest.TestCase):
    def test_unlinked_resolved_address_only_quarantines_its_group(self):
        layers, records, groups = fixture()
        # The second address exists, but neither member of the first group
        # points to it. The second comparison remains independently valid.
        groups[0]['value'].pop('passage_id')
        groups[0]['value']['passage_ids'] = ['private-p1', 'private-p2']
        index = build_d16_index(layers, records, groups)
        self.assertEqual(d16_summary({'_d16_group_index': index})['pending_groups'], 1)
        self.assertEqual(d16_summary({'_d16_group_index': index})['validated_groups'], 1)
        self.assertEqual(len(get_d16_sets({'_d16_group_index': index})), 2)


if __name__ == '__main__':
    unittest.main()
