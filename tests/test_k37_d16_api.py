"""Synthetic D16 API contracts; never open research archives."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import j2_private_preview as api


def _row(key, corpus, scheme, reference):
    return {'key': key, 'record_kind': 'claim', 'passages': [{'corpus': corpus, 'scheme': scheme, 'reference': reference}], 'relationships': []}


class D16ApiTests(unittest.TestCase):
    def setUp(self):
        self.dataset = {'dataset': 'D16', 'records': []}
        self.bible = ('Bible_1', 'd16_scheme_1', 'John 1:1')
        self.quran = ('Quran_1', 'd16_scheme_2', '2:1')
        self.rows = [_row('d13:claims:1', *self.bible), _row('d14:claims:1', *self.bible),
                     _row('d14:claims:2', *self.quran)]
        self.groups = [
            dict(key='d16:comparison_sets:1', corpus=self.bible[0], scheme=self.bible[1], reference=self.bible[2], claim_keys=['d13:claims:1', 'd14:claims:1'], status='recorded_unverified'),
            dict(key='d16:comparison_sets:1', corpus=self.quran[0], scheme=self.quran[1], reference=self.quran[2], claim_keys=['d14:claims:2'], status='pending'),
        ]
        self.projected = {'records': self.rows, 'metadata_projection': 'k1.3-local-candidate'}

    def compare(self, params, groups=None):
        with patch.object(api, 'filter_records', return_value=self.projected), patch.object(api, 'get_d16_sets', return_value=self.groups if groups is None else groups):
            return api.compare_passages(self.dataset, params)

    def test_group_selects_only_exact_corpus_scheme_reference(self):
        p = dict(zip(('corpus', 'scheme', 'reference'), ([x] for x in self.bible)))
        p['comparison_set'] = ['d16:comparison_sets:1']
        result = self.compare(p)
        self.assertEqual([row['key'] for row in result['claims']], ['d13:claims:1', 'd14:claims:1'])
        self.assertEqual(len(result['comparison_sets']), 2)
        self.assertTrue(all('claim_keys' not in x for x in result['comparison_sets']))
        self.assertTrue(all(row['relationships'] == [] for row in result['claims']))

    def test_cross_corpus_group_does_not_merge(self):
        p = dict(zip(('corpus', 'scheme', 'reference'), ([x] for x in self.quran)))
        p['comparison_set'] = ['d16:comparison_sets:1']
        result = self.compare(p)
        self.assertEqual([row['key'] for row in result['claims']], ['d14:claims:2'])

    def test_untrusted_or_malformed_group_is_rejected(self):
        with self.assertRaises(ValueError): self.compare({'comparison_set': ['raw-private-identifier']})
        with self.assertRaises(ValueError): self.compare({'comparison_set': ['d16:comparison_sets:9']})
        malformed = [dict(self.groups[0], claim_keys=['raw-private-identifier'])]
        with self.assertRaises(ValueError): self.compare({'comparison_set': ['d16:comparison_sets:1']}, malformed)

    def test_older_research_mode_rejects_group_filter(self):
        with self.assertRaises(ValueError): api.compare_passages({'dataset':'D12','records':[]}, {'comparison_set':['d16:comparison_sets:1']})

    def test_stage_allowlist_never_treats_unknown_as_synthetic(self):
        self.assertTrue(api._stage_allowed('d14', 'D16'))
        self.assertFalse(api._stage_allowed('d16', 'D12'))
        self.assertFalse(api._stage_allowed('d17', 'D16'))
        self.assertFalse(api._stage_allowed('d14', 'unexpected'))

    def test_recorded_speaker_requires_sealed_projection_and_stays_unverified(self):
        row = {'key': 'd13:claims:1', 'stage': 'd13', 'record_kind': 'claim',
               'reported_speaker': 'INJECTED', 'reported_speaker_status': 'source_confirmed'}
        dataset = {'dataset': 'D16', 'records': [row]}
        untrusted = api.filter_records(dataset, {})
        self.assertIsNone(untrusted['records'][0]['reported_speaker'])
        self.assertEqual(untrusted['records'][0]['reported_speaker_status'], 'pending')
        with patch.object(api, 'content_for_record', return_value={'reported_speaker': 'SYNTHETIC SPEAKER', 'reported_speaker_status': 'recorded_unverified'}):
            trusted = api.filter_records(dataset, {})
        self.assertEqual(trusted['reported_speaker_projection'], 'k37-recorded-speaker')
        self.assertEqual(trusted['records'][0]['reported_speaker'], 'SYNTHETIC SPEAKER')
        self.assertEqual(trusted['records'][0]['reported_speaker_status'], 'recorded_unverified')
        self.assertIsNone(trusted['records'][0]['subject'])

    def test_recorded_speaker_search_uses_only_the_safe_projection(self):
        row = {'key': 'd13:claims:1', 'stage': 'd13', 'record_kind': 'claim',
               'reported_speaker': 'RAW SECRET', 'reported_speaker_status': 'recorded_unverified'}
        dataset = {'dataset': 'D16', 'records': [row]}
        # Archive-supplied fields must never become searchable through either
        # the general query or the researcher filter.
        for parameter in ('q', 'researcher'):
            self.assertEqual(api.filter_records(dataset, {parameter: ['RAW SECRET']})['records'], [])
        projection = {'reported_speaker': 'SYNTHETIC SPEAKER',
                      'reported_speaker_status': 'recorded_unverified'}
        with patch.object(api, 'content_for_record', return_value=projection):
            for parameter in ('q', 'researcher'):
                result = api.filter_records(dataset, {parameter: ['synthetic speaker']})
                self.assertEqual(len(result['records']), 1)
                self.assertEqual(result['records'][0]['reported_speaker_status'], 'recorded_unverified')
                self.assertIsNone(result['records'][0]['subject'])
            self.assertEqual(api.filter_records(dataset, {'q': ['RAW SECRET']})['records'], [])

    def test_recorded_speaker_search_rejects_unsupported_projection_status(self):
        dataset = {'dataset': 'D16', 'records': [
            {'key': 'd13:claims:1', 'stage': 'd13', 'record_kind': 'claim'}]}
        # Only the expected sealed candidate status participates in search;
        # a forged or unsupported status does not promote a speaker.
        with patch.object(api, 'content_for_record', return_value={
                'reported_speaker': 'SYNTHETIC SPEAKER',
                'reported_speaker_status': 'source_confirmed'}):
            for parameter in ('q', 'researcher'):
                self.assertEqual(api.filter_records(dataset, {parameter: ['SYNTHETIC SPEAKER']})['records'], [])

if __name__ == '__main__': unittest.main()
