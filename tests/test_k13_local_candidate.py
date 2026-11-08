"""Synthetic-only tests for the recorded local candidate policy."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from k13_bridge.local_candidate import (
    LocalCandidateIndex, candidate_metadata_for_record,
    candidate_restriction_summary, prepare_local_candidate_index,
)


def sample():
    source = {'id': 'synthetic:source', 'title': 'SYNTHETIC-TITLE',
              'creator': 'SYNTHETIC-CREATOR', 'publisher': 'SYNTHETIC-PUBLISHER',
              'publication_year': 2099}
    edition = {'id': 'synthetic:edition', 'source_id': 'synthetic:source'}
    claim = {'id': 'synthetic:claim', 'attribution_kind': 'external_critique'}
    layers = {'d9': {'sources': [{'line': 1, 'value': source}],
                     'editions': [{'line': 1, 'value': edition}],
                     'claims': [{'line': 1, 'value': claim}], 'rights': []}}
    dataset = {'dataset': 'D10', 'records': [
        {'key': 'd9:sources:1', 'record_kind': 'source'},
        {'key': 'd9:claims:1', 'record_kind': 'claim', 'source_key': 'd9:sources:1',
         'edition_key': 'd9:editions:1'}]}
    return dataset, layers


def make(dataset, layers, key='d9:sources:1'):
    index = prepare_local_candidate_index(dataset, layers)
    return candidate_metadata_for_record(index, dataset['dataset'], key)


class LocalCandidateTests(unittest.TestCase):
    def test_unverified_is_independent_of_claim_status(self):
        dataset, layers = sample()
        layers['d9']['claims'][0]['value'].update({'verification_status': 'unverified',
                                                  'authority_status': 'pending',
                                                  'independent_human_review': False})
        row = make(dataset, layers, 'd9:claims:1')
        self.assertEqual(row['source_title'], {'value': 'SYNTHETIC-TITLE',
                                               'status': 'recorded_unverified', 'reason': None})
        self.assertEqual(row['source_creator']['value'], 'SYNTHETIC-CREATOR')
        self.assertEqual(row['source_year']['value'], '2099')
        self.assertEqual(row['community_name']['status'], 'missing_or_unmapped')

    def test_unknown_is_neither_denial_nor_confirmation(self):
        dataset, layers = sample()
        layers['d9']['rights'] = [{'value': {'edition_id': 'synthetic:edition',
                                             'action': 'browse', 'decision': 'unknown'}}]
        self.assertEqual(make(dataset, layers)['source_title']['status'], 'recorded_unverified')

    def test_conditional_and_permission_alias_restrict_only_display_actions(self):
        for alias in ('decision', 'new_decision', 'permission'):
            for decision in ('conditional', 'denied', 'prohibited', 'restricted'):
                with self.subTest(alias=alias, decision=decision):
                    dataset, layers = sample()
                    layers['d9']['rights'] = [{'value': {'edition_id': 'synthetic:edition',
                                                         'action': 'browse', 'decision': 'unknown',
                                                         alias: decision}}]
                    self.assertEqual(make(dataset, layers)['source_title']['status'], 'restricted')
        dataset, layers = sample()
        layers['d9']['rights'] = [{'value': {'edition_id': 'synthetic:edition',
                                             'action': 'index_fulltext', 'decision': 'denied'}},
                                  {'value': {'edition_id': 'synthetic:edition',
                                             'action': 'collect_metadata', 'decision': 'conditional'}}]
        self.assertEqual(make(dataset, layers)['source_title']['status'], 'recorded_unverified')

    def test_override_conflict_and_source_rights_fail_closed(self):
        dataset, layers = sample()
        layers['d9']['rights_overrides'] = [{'value': {'baseline_edition_id': 'synthetic:edition',
                                                       'action': 'browse', 'new_decision': 'denied'}}]
        self.assertEqual(make(dataset, layers)['source_title']['reason'], 'explicit_restriction')
        layers['d9']['rights_overrides'] = []
        layers['d9']['rights'] = [{'value': {'source_id': 'synthetic:source', 'action': 'browse',
                                             'decision': 'allowed', 'permission': 'conditional'}}]
        self.assertEqual(make(dataset, layers)['source_title']['reason'], 'conditional_use')

    def test_whitespace_actions_and_malformed_decisions_fail_closed(self):
        dataset, layers = sample()
        layers['d9']['rights'] = [{'value': {'edition_id': 'synthetic:edition',
                                             'action': '  BrOwSe  ', 'permission': 'Not Allowed'}}]
        self.assertEqual(make(dataset, layers)['source_title']['reason'], 'explicit_restriction')
        layers['d9']['rights'][0]['value']['permission'] = {'bad': 'shape'}
        self.assertEqual(make(dataset, layers)['source_title']['reason'], 'explicit_restriction')

    def test_multiedition_source_is_recorded_but_claim_chain_checked(self):
        dataset, layers = sample()
        layers['d9']['editions'].append({'line': 2, 'value': {'id': 'synthetic:edition2',
                                                               'source_id': 'synthetic:source'}})
        self.assertEqual(make(dataset, layers)['source_title']['value'], 'SYNTHETIC-TITLE')
        dataset['records'][1]['edition_key'] = 'd9:editions:3'
        self.assertEqual(make(dataset, layers, 'd9:claims:1')['source_title']['reason'], 'ambiguous_edition')

    def test_field_level_restriction_does_not_hide_other_fields(self):
        dataset, layers = sample()
        layers['d9']['sources'][0]['value']['restricted_fields'] = ['creator']
        row = make(dataset, layers)
        self.assertEqual(row['source_creator']['reason'], 'explicit_restriction')
        self.assertEqual(row['source_title']['value'], 'SYNTHETIC-TITLE')

    def test_sensitive_agent_and_private_source_fields_are_hidden(self):
        dataset, layers = sample()
        layers['d9']['agents'] = [{'value': {'id': 'synthetic:agent', 'name': 'SYNTHETIC-CREATOR',
                                            'is_private': True}}]
        self.assertEqual(make(dataset, layers)['source_creator']['reason'], 'sensitive_or_personal')
        self.assertEqual(make(dataset, layers)['source_title']['status'], 'recorded_unverified')
        layers['d9']['sources'][0]['value']['confidential'] = True
        self.assertEqual(make(dataset, layers)['source_title']['reason'], 'sensitive_or_personal')

    def test_private_creator_in_author_list_or_explicit_id_is_hidden(self):
        dataset, layers = sample()
        layers['d9']['agents'] = [{'value': {'id': 'synthetic:agent', 'name': 'SYNTHETIC-PRIVATE',
                                            'privacy_status': 'private'}}]
        source = layers['d9']['sources'][0]['value']
        source['creator'] = 'SYNTHETIC-OTHER; SYNTHETIC-PRIVATE'
        self.assertEqual(make(dataset, layers)['source_creator']['reason'], 'sensitive_or_personal')
        source['creator'] = 'SYNTHETIC-OTHER'
        source['creator_ids'] = ['synthetic:agent']
        self.assertEqual(make(dataset, layers)['source_creator']['reason'], 'sensitive_or_personal')

    def test_private_name_in_title_or_publisher_is_hidden(self):
        dataset, layers = sample()
        layers['d9']['agents'] = [{'value': {'id': 'synthetic:agent', 'name': 'SYNTHETIC-PRIVATE',
                                            'privacy_status': 'private'}}]
        source = layers['d9']['sources'][0]['value']
        source['title'] = 'SYNTHETIC-TITLE mentioning SYNTHETIC-PRIVATE'
        source['publisher'] = 'SYNTHETIC-PUBLISHER (SYNTHETIC-PRIVATE)'
        row = make(dataset, layers)
        self.assertEqual(row['source_title']['reason'], 'sensitive_or_personal')
        self.assertEqual(row['source_publisher']['reason'], 'sensitive_or_personal')
        self.assertEqual(row['source_creator']['status'], 'recorded_unverified')
        source['title'] = 'SYNTHETIC-PRIVATELESS'
        self.assertEqual(make(dataset, layers)['source_title']['status'], 'recorded_unverified')

    def test_values_with_contact_data_markup_or_controls_are_hidden(self):
        for value in ('SYNTHETIC-EXAMPLE@example.invalid', 'https://example.invalid/',
                      '<script>bad</script>', 'a\nb', '010-1234-5678', '000101-1234567'):
            with self.subTest(kind=value.split(':')[0]):
                dataset, layers = sample()
                layers['d9']['sources'][0]['value']['title'] = value
                self.assertEqual(make(dataset, layers)['source_title']['status'], 'restricted')

    def test_long_title_and_placeholder(self):
        dataset, layers = sample()
        layers['d9']['sources'][0]['value']['title'] = 'S' * 300
        self.assertEqual(make(dataset, layers)['source_title']['status'], 'recorded_unverified')
        layers['d9']['sources'][0]['value']['title'] = 'unknown'
        self.assertEqual(make(dataset, layers)['source_title']['status'], 'missing_or_unmapped')

    def test_posted_date_is_not_publication_year(self):
        dataset, layers = sample()
        source = layers['d9']['sources'][0]['value']
        del source['publication_year']
        source['published_at'] = '2099-01-01'
        self.assertEqual(make(dataset, layers)['source_year']['status'], 'missing_or_unmapped')
        source['publication_date'] = '2098-01-01'
        self.assertEqual(make(dataset, layers)['source_year']['value'], '2098')
        source['publication_date'] = '2098'
        self.assertEqual(make(dataset, layers)['source_year']['value'], '2098')
        source['publication_date'] = '2098-12'
        self.assertEqual(make(dataset, layers)['source_year']['value'], '2098')
        source['publication_date'] = '2098-99'
        self.assertEqual(make(dataset, layers)['source_year']['status'], 'missing_or_unmapped')

    def test_community_requires_exact_target_role_and_unique_join(self):
        dataset, layers = sample()
        claim = layers['d9']['claims'][0]['value']
        claim['community_id'] = 'synthetic:community'
        layers['d9']['communities'] = [{'value': {'id': 'synthetic:community',
                                                 'canonical_name': 'SYNTHETIC-COMMUNITY'}}]
        self.assertEqual(make(dataset, layers, 'd9:claims:1')['community_name']['reason'], 'community_role_unconfirmed')
        claim['community_id_role'] = 'target'
        community = make(dataset, layers, 'd9:claims:1')['community_name']
        self.assertEqual(community['value'], 'SYNTHETIC-COMMUNITY')
        self.assertEqual(community['relationship_role'], 'target')
        claim['attribution_kind'] = 'self_explanation'
        self.assertEqual(make(dataset, layers, 'd9:claims:1')['community_name']['reason'], 'community_role_unconfirmed')
        claim['community_id_role'] = 'self'
        community = make(dataset, layers, 'd9:claims:1')['community_name']
        self.assertEqual(community['value'], 'SYNTHETIC-COMMUNITY')
        self.assertEqual(community['relationship_role'], 'self')
        layers['d9']['communities'] = []
        self.assertEqual(make(dataset, layers, 'd9:claims:1')['community_name']['reason'], 'community_unlinked')

    def test_sealed_index_and_aggregate_contains_no_values(self):
        dataset, layers = sample()
        index = prepare_local_candidate_index(dataset, layers)
        self.assertNotIn('SYNTHETIC-TITLE', repr(index))
        self.assertNotIn('SYNTHETIC-TITLE', repr(candidate_restriction_summary(index, 'D10')))
        self.assertEqual(candidate_restriction_summary(index, 'D10')['sources']['source_title']['recorded_unverified'], 1)
        self.assertEqual(candidate_metadata_for_record({}, 'D10', 'd9:sources:1'), {})
        self.assertEqual(candidate_metadata_for_record(index, 'D9', 'd9:sources:1'), {})
        with self.assertRaises(ValueError):
            LocalCandidateIndex(None, 'D10', {}, {})


if __name__ == '__main__':
    unittest.main()
