"""Synthetic-only K-1 API fail-closed and version isolation tests."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from j2_private_preview import PrivatePreviewServer, filter_records
from j2_preview_test_server import sample_data


def data(mode='D10'):
    dataset = sample_data()
    dataset['dataset'] = mode
    dataset['records'] = [copy.deepcopy(dataset['records'][0])]
    dataset['records'][0].update(
        stage='d10', key='d10:sources:1', record_kind='source',
        source_key='d10:sources:1', edition_key='d10:editions:1', locator_key='d10:locators:1',
        source_title='SYNTHETIC_PRIVATE_TITLE', source_creator='SYNTHETIC_PRIVATE_PERSON',
        researcher='SYNTHETIC_PRIVATE_PERSON', speaker='SYNTHETIC_PRIVATE_PERSON',
        tradition='SYNTHETIC_PRIVATE_GROUP', community_reference='SYNTHETIC_PRIVATE_GROUP',
        evaluated_subject='SYNTHETIC_PRIVATE_GROUP', source_doi='10.1234/SYNTHETIC',
        source_year=2020, locator='page 22', summary='SYNTHETIC_PRIVATE_TEXT',
        field_policy={'source_metadata':'candidate_visible_local'},
        field_eligibility={'source':{'bibliography':'candidate_visible_local'}},
        display_status='candidate_visible_local', display_grant={'approved': True},
        rights={'browse':'allowed'},
    )
    dataset['visibility_summary'] = {'total':1270, 'candidate_visible_local':1, 'metadata_candidate':8, 'unknown':751, 'unmapped':510}
    dataset['counts'] = {'display_records': 1, 'd10': {'sources': 1}, 'by_stage': {'d10': {'sources': 1}}}
    dataset['unmapped_summary'] = {'d10': {'sources': {'input_count': 1, 'mapping': 'partial'}}}
    return dataset


def fetch(dataset, **kwargs):
    return filter_records(dataset, {key:[value] for key, value in kwargs.items()})


class K1ApiTests(unittest.TestCase):
    def test_d10_is_research_mode_and_all_private_fields_remain_hidden(self):
        candidate = data()
        result = fetch(candidate)
        self.assertEqual(result['total'], 1)
        row = result['records'][0]
        self.assertEqual(row['key'], 'd10:sources:1')
        for field in ('source_title','source_creator','researcher','speaker','tradition', 'community_reference','evaluated_subject','source_doi','source_year','locator','summary'):
            self.assertIsNone(row.get(field), field)
        encoded = json.dumps(result)
        self.assertNotIn('SYNTHETIC_PRIVATE_', encoded)
        self.assertEqual(row['field_eligibility']['source']['bibliography'], 'unmapped')
        self.assertTrue(all(value is False for value in row['effective_permissions'].values()))
        for marker in ('SYNTHETIC_PRIVATE_TITLE', 'SYNTHETIC_PRIVATE_PERSON', 'SYNTHETIC_PRIVATE_GROUP', 'SYNTHETIC_PRIVATE_TEXT'):
            self.assertEqual(fetch(candidate, q=marker)['total'], 0)
        self.assertEqual(fetch(candidate, researcher='SYNTHETIC_PRIVATE_PERSON')['total'], 0)

    def test_candidate_count_is_not_an_approval(self):
        result = fetch(data())['visibility_summary']
        self.assertEqual(result['conditional_candidate'], 1)
        self.assertEqual(result['candidate_visible_local'], 0)
        self.assertEqual(result['total'], 1270)

    def test_visibility_counter_tampering_fails_closed(self):
        for forged in (0, 2, -1, True, '1'):
            candidate=data()
            candidate['visibility_summary']['candidate_visible_local']=forged
            self.assertEqual(fetch(candidate)['visibility_summary'], {'status':'pending_inconsistent'})

    def test_unknown_dataset_never_uses_synthetic_bypass(self):
        for mode in ('D11', '', 'D10 ', None):
            candidate=data(mode)
            with self.assertRaises(ValueError):
                fetch(candidate)
            with self.assertRaises(ValueError):
                PrivatePreviewServer(candidate, 'synthetic-secret-for-local-tests')

    def test_d8_d9_modes_do_not_return_d10_or_counts(self):
        for mode, existing_stage in (('D8', 'd8'), ('D9', 'd9')):
            candidate=data(mode)
            existing=copy.deepcopy(candidate['records'][0])
            existing.update(stage=existing_stage, key=existing_stage+':sources:1')
            candidate['records'].append(existing)
            result=fetch(candidate)
            self.assertEqual(result['total'], 1)
            self.assertEqual(result['counts']['display_records'], 1)
            self.assertNotIn('d10', result['counts'])
            self.assertNotIn('d10', result['counts']['by_stage'])
            self.assertNotIn('d10', result['unmapped_summary'])
            self.assertEqual(fetch(candidate, stage='d10')['total'], 0)

    def test_d10_safe_coordinates_and_observations(self):
        candidate=data()
        row=candidate['records'][0]
        row.update(d9_observations=[{'kind':'relationship','status':'pending', 'direction':'incoming', 'relation_type':'support', 'target_key':'d9:claims:1'}],
                   d9_rights_observations=[{'action':'browse','decision':'conditional','edition_key':'d10:editions:1'}])
        out=fetch(candidate)['records'][0]
        self.assertEqual(out['source_key'], 'd10:sources:1')
        self.assertEqual(out['edition_key'], 'd10:editions:1')
        self.assertEqual(out['locator_key'], 'd10:locators:1')
        self.assertEqual(out['d9_observations'][0]['target_key'], 'd9:claims:1')
        self.assertEqual(out['d9_rights_observations'][0]['edition_key'], 'd10:editions:1')

    def test_claim_never_inherits_source_bibliographic_permission(self):
        candidate=data()
        candidate['records'][0].update(stage='d9', key='d9:claims:1', record_kind='claim')
        candidate['display_grant']={'version':'k1-local-v1','key':'d9:claims:1','fields':['source_title','source_creator']}
        row=fetch(candidate)['records'][0]
        self.assertIsNone(row['source_title'])
        self.assertIsNone(row['source_creator'])

    def test_d10_receipt_is_bounded_aggregate_not_grant(self):
        candidate=data()
        candidate['d10_receipt']={
            'source_count':16, 'quarantined_source_count':16, 'conditional_candidate_count':1,
            'effective_visible_fields':0, 'SYNTHETIC_PRIVATE_KEY':'SYNTHETIC_PRIVATE_VALUE',
            'duplicate_counts':{'cross_id':0, 'SYNTHETIC_PRIVATE_KEY':'SYNTHETIC_PRIVATE_VALUE'},
            'linkage_counts':{'editions_source_id_present':5, 'SYNTHETIC_PRIVATE_KEY':2}}
        result=fetch(candidate)
        self.assertNotIn('SYNTHETIC_PRIVATE_', json.dumps(result))
        self.assertEqual(result['d10_receipt']['quarantined_source_count'],16)
        candidate['d10_receipt']['effective_visible_fields']=1
        self.assertEqual(fetch(candidate)['d10_receipt'], {'status':'pending_inconsistent'})


if __name__ == '__main__':
    unittest.main()
