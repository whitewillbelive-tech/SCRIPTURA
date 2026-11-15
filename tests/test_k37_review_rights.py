"""Synthetic field-specific restrictions do not become blanket permissions."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from k13_bridge.local_candidate import candidate_metadata_for_record, prepare_local_candidate_index
from k37_bridge.real_content import apply_k2_review_restrictions, content_for_record
from k2_bridge.receipt import _SummaryIndex, _TraditionIndex, summary_for_record, tradition_for_record
from j2_private_preview import compare_passages, filter_records
from test_real_content import fixture, build


class LinkedRightsFields(unittest.TestCase):
    def metadata(self, dataset, layers):
        return candidate_metadata_for_record(prepare_local_candidate_index(dataset, layers), 'D16', 'd13:claims:1')

    def set_right(self, layers, **kwargs):
        layers['d16'] = {'rights_actions': [{'line': 1, 'value': {
            'source_id': 'synthetic-src', 'edition_id': 'synthetic-ed', **kwargs}}]}

    def test_bibliography_field_restrictions_are_independent(self):
        layers, records, dataset = fixture()
        self.set_right(layers, restricted_fields=['creator'])
        fields = self.metadata(dataset, layers)
        self.assertEqual(fields['source_creator']['status'], 'restricted')
        self.assertEqual(fields['source_title']['status'], 'recorded_unverified')
        layers['d16']['rights_actions'][0]['value']['restricted_fields'] = []
        layers['d16']['rights_actions'][0]['value']['field_restrictions'] = {'title': 'conditional'}
        fields = self.metadata(dataset, layers)
        self.assertEqual(fields['source_title']['reason'], 'conditional_use')
        self.assertEqual(fields['source_creator']['status'], 'recorded_unverified')

    def test_field_action_denial_is_scoped_and_allowed_never_confirms(self):
        layers, records, dataset = fixture()
        self.set_right(layers, action='display creator', decision='denied')
        fields = self.metadata(dataset, layers)
        self.assertEqual(fields['source_creator']['status'], 'restricted')
        self.assertEqual(fields['source_title']['status'], 'recorded_unverified')
        layers['d16']['rights_actions'][0]['value']['decision'] = 'allowed'
        self.assertEqual(self.metadata(dataset, layers)['source_creator']['status'], 'recorded_unverified')
        layers['d16']['rights_actions'][0]['value'].update(action='store_fulltext', decision='denied')
        self.assertEqual(self.metadata(dataset, layers)['source_creator']['status'], 'recorded_unverified')

    def test_claim_content_restrictions_do_not_cross_fields(self):
        layers, records, dataset = fixture()
        row = layers['d13']['claims'][0]['value']
        row['reasoning_verification_method'] = '자체 요약; 인용 없이'
        row['reasoning_original_text_stored'] = False
        self.set_right(layers, restricted_fields=['speaker', 'reasoning_ko'])
        result = content_for_record(build(layers, records, dataset), 'D16', 'd13:claims:1')
        self.assertIsNone(result['reported_speaker'])
        self.assertIsNone(result['reasoning'])
        self.assertEqual(result['summary_status'], 'recorded_unverified')
        self.assertEqual(result['tradition_status'], 'recorded_unverified')
        layers['d16']['rights_actions'][0]['value']['restricted_fields'] = []
        layers['d16']['rights_actions'][0]['value']['field_restrictions'] = {'statement_ko': 'restricted'}
        result = content_for_record(build(layers, records, dataset), 'D16', 'd13:claims:1')
        self.assertIsNone(result['summary'])
        self.assertEqual(result['reasoning_status'], 'recorded_unverified')

    def test_other_edition_restriction_does_not_apply_to_claim(self):
        layers, records, dataset = fixture()
        layers['d13']['editions'].append({'line': 2, 'value': {'id': 'synthetic-other-ed', 'source_id': 'synthetic-src'}})
        self.set_right(layers, action='browse', decision='denied')
        layers['d16']['rights_actions'][0]['value']['edition_id'] = 'synthetic-other-ed'
        self.assertEqual(self.metadata(dataset, layers)['source_title']['status'], 'recorded_unverified')
        result = content_for_record(build(layers, records, dataset), 'D16', 'd13:claims:1')
        self.assertEqual(result['reported_speaker_status'], 'recorded_unverified')
        self.assertEqual(result['summary_status'], 'recorded_unverified')
        # A source card represents all its editions and therefore remains conservative.
        dataset = copy.deepcopy(dataset)
        dataset['records'].append({'key': 'd13:sources:1', 'record_kind': 'source'})
        index = prepare_local_candidate_index(dataset, layers)
        self.assertEqual(candidate_metadata_for_record(index, 'D16', 'd13:sources:1')['source_title']['status'], 'restricted')

    def test_general_restriction_overrides_field_allow(self):
        layers, records, dataset = fixture()
        self.set_right(layers, action='browse', decision='denied', field_restrictions={'creator': 'allowed'})
        fields = self.metadata(dataset, layers)
        self.assertEqual(fields['source_title']['status'], 'restricted')
        self.assertEqual(fields['source_creator']['status'], 'restricted')
        layers['d16']['rights_actions'][0]['value'].update(action='local display', decision='not permitted')
        self.assertEqual(self.metadata(dataset, layers)['source_title']['status'], 'restricted')

    def test_community_field_rule_is_independent_of_bibliography(self):
        layers, records, dataset = fixture()
        layers['d13']['claims'][0]['value'].update(
            community_id='synthetic-community', community_id_role='self',
            attribution_kind='self_explanation')
        layers['d13']['communities'] = [{'line': 1, 'value': {
            'id': 'synthetic-community', 'canonical_name': 'SYNTHETIC COMMUNITY'}}]
        self.set_right(layers, field_restrictions={'community_name': 'not permitted'})
        fields = self.metadata(dataset, layers)
        self.assertEqual(fields['community_name']['status'], 'restricted')
        self.assertEqual(fields['source_title']['status'], 'recorded_unverified')

    def test_allow_does_not_approve_unattested_claim(self):
        layers, records, dataset = fixture()
        row = layers['d13']['claims'][0]['value']
        row.pop('verification_method')
        self.set_right(layers, action='display_summary', decision='allowed')
        result = content_for_record(build(layers, records, dataset), 'D16', 'd13:claims:1')
        self.assertIsNone(result['summary'])
        self.assertEqual(result['summary_status'], 'pending_review')

    def test_recorded_speaker_denial_aliases_are_honored(self):
        for decision in ('deny', 'not granted', 'disallow', 'rejected'):
            with self.subTest(decision=decision):
                layers, records, dataset = fixture()
                self.set_right(layers, action='speaker', decision=decision)
                result = content_for_record(build(layers, records, dataset), 'D16', 'd13:claims:1')
                self.assertIsNone(result['reported_speaker'])
                self.assertEqual(result['summary_status'], 'recorded_unverified')

    def test_d12_sealed_indices_remove_only_restricted_edition_fields(self):
        layers, records, dataset = fixture()
        layers['d12'] = layers.pop('d13')
        claim = layers['d12']['claims'][0]['value']
        claim2 = dict(claim, id='synthetic-claim-2', edition_id='synthetic-other-ed', source_locator_id='synthetic-other-loc')
        layers['d12']['claims'].append({'line': 2, 'value': claim2})
        layers['d12']['editions'].append({'line': 2, 'value': {'id': 'synthetic-other-ed', 'source_id': 'synthetic-src'}})
        layers['d12']['locators'].append({'line': 2, 'value': {'id': 'synthetic-other-loc', 'source_id': 'synthetic-src', 'edition_id': 'synthetic-other-ed'}})
        layers['d16'] = {'rights_actions': [{'line': 1, 'value': {
            'source_id': 'synthetic-src', 'edition_id': 'synthetic-ed',
            'restricted_fields': ['summary', 'tradition']}}]}
        records = [dict(key=f'd12:claims:{n}', stage='d12', record_kind='claim',
                        passages=[{'corpus': 'Bible_1', 'scheme': 'd12_scheme_1', 'reference': 'John 1:1'}])
                   for n in (1, 2)]
        original_summary = _SummaryIndex({'d12:claims:1': 'SYNTHETIC SUMMARY 1', 'd12:claims:2': 'SYNTHETIC SUMMARY 2'})
        original_tradition = _TraditionIndex({'d12:claims:1': 'SYNTHETIC TRADITION 1', 'd12:claims:2': 'SYNTHETIC TRADITION 2'})
        summaries, traditions = apply_k2_review_restrictions(layers, records, original_summary, original_tradition)
        self.assertIsNone(summary_for_record(summaries, 'D12', 'd12:claims:1'))
        self.assertIsNone(tradition_for_record(traditions, 'D12', 'd12:claims:1'))
        self.assertEqual(summary_for_record(summaries, 'D12', 'd12:claims:2'), 'SYNTHETIC SUMMARY 2')
        self.assertEqual(tradition_for_record(traditions, 'D12', 'd12:claims:2'), 'SYNTHETIC TRADITION 2')
        self.assertEqual(summary_for_record(original_summary, 'D12', 'd12:claims:1'), 'SYNTHETIC SUMMARY 1')
        data = {'dataset': 'D16', 'records': records, '_k2_summary_index': summaries,
                '_k2_tradition_index': traditions}
        rows = filter_records(data, {})['records']
        self.assertIsNone(rows[0]['summary'])
        self.assertIsNone(rows[0]['tradition_candidate']['value'])
        self.assertEqual(rows[1]['summary'], 'SYNTHETIC SUMMARY 2')
        detail = filter_records(data, {'key': ['d12:claims:1']})['records']
        self.assertEqual(len(detail), 1)
        self.assertIsNone(detail[0]['summary'])
        self.assertIsNone(detail[0]['tradition_candidate']['value'])
        query = {'corpus': ['Bible_1'], 'scheme': ['d12_scheme_1'], 'reference': ['John 1:1']}
        compared = compare_passages(data, query)['claims']
        self.assertIsNone(compared[0]['summary'])
        self.assertIsNone(compared[0]['tradition_candidate']['value'])
        self.assertEqual(compared[1]['summary'], 'SYNTHETIC SUMMARY 2')

    def test_d12_gate_never_grants_missing_old_content(self):
        layers, records, dataset = fixture()
        layers['d12'] = layers.pop('d13')
        records = [{'key': 'd12:claims:1', 'stage': 'd12', 'record_kind': 'claim'}]
        summaries, traditions = apply_k2_review_restrictions(
            layers, records, _SummaryIndex({}), _TraditionIndex({}))
        self.assertIsNone(summary_for_record(summaries, 'D12', 'd12:claims:1'))
        self.assertIsNone(tradition_for_record(traditions, 'D12', 'd12:claims:1'))


if __name__ == '__main__':
    unittest.main()
