"""Synthetic test of Work rights-evidence linkage and safe projection."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from k37_bridge.review_checks import verified_rights_actions
from k13_bridge.local_candidate import candidate_metadata_for_record, prepare_local_candidate_index
from test_real_content import fixture


def entry(line, **value):
    return {'line': line, 'value': value}


class RightsEvidenceProjectionTests(unittest.TestCase):
    def test_only_matched_restrictions_propagate(self):
        layers = {'d13': {'sources': [entry(1, id='source')],
                          'editions': [entry(1, id='edition', source_id='source'),
                                       entry(2, id='other-edition', source_id='other')]}}
        rows = [entry(1, source_id='source', edition_id='edition', action='display', decision='denied', free_text='secret'),
                entry(2, source_id='source', edition_id='edition', action='display', decision='allowed'),
                entry(3, source_id='source', edition_id='other-edition', action='display', decision='denied'),
                entry(4, source_id='missing', edition_id='edition', action='display', decision='denied'),
                entry(5, source_id='source', edition_id='edition', restricted_fields=['title', 'unsupported'],
                      field_restrictions={'author': 'conditional', 'unused': 'denied'})]
        projected, counts = verified_rights_actions(layers, rows)
        self.assertEqual(counts, {'rows': 5, 'pending': 3, 'restricted': 2, 'unapplied': 1, 'no_applicable_signal': 1})
        self.assertEqual(projected[0]['value']['decision'], 'denied')
        self.assertNotIn('free_text', projected[0]['value'])
        self.assertEqual(projected[1]['value']['restricted_fields'], ['title'])
        self.assertEqual(projected[1]['value']['field_restrictions'], {'author': 'conditional'})

    def test_conflicting_identity_does_not_propagate(self):
        layers = {'d13': {'sources': [entry(1, id='source'), entry(2, id='source', title='different')],
                          'editions': [entry(1, id='edition', source_id='source')]}}
        projected, counts = verified_rights_actions(layers, [entry(1, source_id='source', edition_id='edition', action='display', decision='denied')])
        self.assertEqual(projected, [])
        self.assertEqual(counts['pending'], 1)

    def test_unmapped_or_malformed_restrictions_remain_pending(self):
        layers = {'d13': {'sources': [entry(1, id='source')],
                          'editions': [entry(1, id='edition', source_id='source')]}}
        rows = [entry(1, source_id='source', edition_id='edition', decision='denied'),
                entry(2, source_id='source', edition_id='edition', action='unsupported', decision='denied', restricted_fields=['title']),
                entry(3, source_id='source', edition_id='edition', action='display', decision=['denied']),
                entry(4, source_id='source', edition_id='edition', restricted_fields='title'),
                entry(5, source_id='source', edition_id='edition', field_restrictions={'unmapped': True}),
                entry(6, source_id='source', edition_id='edition', action='Local Display', decision='denied')]
        projected, counts = verified_rights_actions(layers, rows)
        self.assertEqual(counts['pending'], 5)
        self.assertEqual(counts['unapplied'], 5)
        self.assertEqual(counts['restricted'], 2)
        self.assertEqual(projected[0]['value']['restricted_fields'], ['title'])
        self.assertEqual(projected[1]['value']['action'], 'local_display')

    def test_bibliographic_action_projection_controls_candidate_display(self):
        layers, records, dataset = fixture()
        rows = [entry(1, source_id='synthetic-src', edition_id='synthetic-ed',
                      action='display source creator', decision='denied')]
        projected, counts = verified_rights_actions(layers, rows)
        self.assertEqual(counts['restricted'], 1)
        self.assertEqual(counts['pending'], 0)
        layers['d16'] = {'rights_actions': projected}
        index = prepare_local_candidate_index(dataset, layers)
        fields = candidate_metadata_for_record(index, 'D16', 'd13:claims:1')
        self.assertEqual(fields['source_creator']['status'], 'restricted')
        self.assertEqual(fields['source_title']['status'], 'recorded_unverified')


if __name__ == '__main__':
    unittest.main()
