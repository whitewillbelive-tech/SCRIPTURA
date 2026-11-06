"""Synthetic-only J-3 API privacy, version isolation and observation tests."""
import copy
import http.client
import json
import sys
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from j2_private_preview import PrivatePreviewServer, filter_records
from j2_preview_test_server import sample_data

SECRET = 'SYNTHETIC-J3-SESSION-SECRET-123'


def dataset(mode='D9'):
    data = sample_data()
    data['dataset'] = mode
    data['records'] = [copy.deepcopy(data['records'][0])]
    row = data['records'][0]
    row.update(stage='d9' if mode == 'D9' else 'd8',
               key='d9:claims:1' if mode == 'D9' else 'd8:claims:1',
               record_kind='claim', source_key='d9:sources:2' if mode == 'D9' else 'd8:sources:2',
               edition_key='d9:editions:3' if mode == 'D9' else 'd8:editions:3',
               locator_key='d9:locators:4' if mode == 'D9' else 'd8:locators:4')
    if mode == 'D9':
        data['visibility_summary'] = {'total':1270, 'metadata_candidate':9, 'candidate_visible_local':0, 'unknown':1261}
    return data


def fetch(data, **args):
    return filter_records(data, {key:[value] for key, value in args.items()})


class J3SearchTests(unittest.TestCase):
    def test_d9_safe_coordinate_and_future_eligibility_are_not_grants(self):
        data = dataset(); row = data['records'][0]
        row.update(source_title='HIDDEN_PRIVATE_TITLE', source_creator='HIDDEN_PRIVATE_PERSON',
                   researcher='HIDDEN_PRIVATE_PERSON', speaker='HIDDEN_PRIVATE_PERSON',
                   tradition='HIDDEN_PRIVATE_GROUP', community_reference='HIDDEN_PRIVATE_GROUP',
                   evaluated_subject='HIDDEN_PRIVATE_GROUP', summary='HIDDEN_PRIVATE_QUOTE',
                   attribution='official_doctrine', authority_status='adoption_documented',
                   independent_review_status='human_review_documented', display_status='candidate_visible_local',
                   field_policy={'source_metadata':'candidate_visible_local'},
                   field_eligibility={'source':{'bibliography':'candidate_visible_local', 'own_summary':'metadata_candidate'}})
        result = fetch(data); out = result['records'][0]; encoded = json.dumps(result)
        for marker in ('HIDDEN_PRIVATE_TITLE','HIDDEN_PRIVATE_PERSON','HIDDEN_PRIVATE_GROUP','HIDDEN_PRIVATE_QUOTE'):
            self.assertNotIn(marker, encoded)
            self.assertEqual(fetch(data, q=marker)['total'], 0)
        self.assertEqual((out['key'], out['source_key'], out['edition_key'], out['locator_key']),
                         ('d9:claims:1','d9:sources:2','d9:editions:3','d9:locators:4'))
        self.assertEqual(out['attribution'],'unconfirmed_authority')
        self.assertEqual(out['authority_status'],'pending_authority')
        self.assertEqual(out['independent_review_status'],'pending')
        self.assertEqual(out['display_status'],'redacted_rights_unresolved')
        self.assertEqual(out['field_policy']['source_metadata'],'redacted_rights_unresolved')
        self.assertEqual(out['field_eligibility']['source']['bibliography'],'unmapped')
        self.assertEqual(out['field_eligibility']['source']['own_summary'],'metadata_candidate')
        self.assertTrue(all(value is False for value in out['effective_permissions'].values()))

    def test_ascii_identifier_cannot_hide_in_codes_fields_or_keys(self):
        data = dataset(); row = data['records'][0]
        row.update(key='d9:claims:1', source_kind='PRIVATE_IDENTIFIER_711',
                   verification_status='PRIVATE_IDENTIFIER_712', access_path='PRIVATE_IDENTIFIER_713',
                   locator='PRIVATE_IDENTIFIER_714', source_doi='PRIVATE_IDENTIFIER_715',
                   unmapped=['PRIVATE_IDENTIFIER_716','source_title'], audit_observation_key='PRIVATE_IDENTIFIER_717',
                   evidence=[{'kind':'PRIVATE_IDENTIFIER_718','status':'PRIVATE_IDENTIFIER_719'}],
                   relationships=[{'kind':'PRIVATE_IDENTIFIER_720','status':'PRIVATE_IDENTIFIER_721',
                                   'target_key':'PRIVATE_IDENTIFIER_722','direction':'PRIVATE_IDENTIFIER_723'}],
                   access_events=[{'method':'PRIVATE_IDENTIFIER_724','result':'PRIVATE_IDENTIFIER_725','checked_at':'PRIVATE_IDENTIFIER_726'}])
        result = fetch(data); encoded=json.dumps(result)
        self.assertNotIn('PRIVATE_IDENTIFIER_',encoded)
        for n in range(711,727):
            self.assertEqual(fetch(data,q=f'PRIVATE_IDENTIFIER_{n}')['total'],0)
        self.assertEqual(result['records'][0]['unmapped'], ['source_title','unrecognized_field'])

    def test_d8_mode_neither_returns_nor_counts_d9_rows_or_observations(self):
        data=dataset('D8'); row=data['records'][0]
        row.update(source_key='d9:sources:2', edition_key='d9:editions:3', locator_key='d9:locators:4',
                   field_eligibility={'source':{'bibliography':'metadata_candidate'}},
                   d9_observations=[{'kind':'evidence','status':'source_checked'}],
                   d9_rights_observations=[{'edition_key':'d9:editions:3','action':'browse','decision':'allowed'}])
        extra = copy.deepcopy(row); extra.update(stage='d9',key='d9:claims:1')
        data['records'].append(extra)
        data['counts']={'display_records':2,'d9':{'claims':1},'by_stage':{'d8':{'claims':1},'d9':{'claims':1}}}
        data['unmapped_summary']={'d8':{'claims':{'input_count':1,'mapping':'partial'}},'d9':{'claims':{'input_count':1,'mapping':'partial'}}}
        data['facets']={'d9':'PRIVATE_METADATA'}; data['warnings']=['PRIVATE_METADATA']
        data['visibility_summary']={'metadata_candidate':9,'candidate_visible_local':0,'total':1270}
        result=fetch(data); out=result['records'][0]
        self.assertEqual(result['total'],1)
        self.assertEqual([out[k] for k in ('source_key','edition_key','locator_key')],[None,None,None])
        self.assertEqual(out['d9_observations'],[]);self.assertEqual(out['d9_rights_observations'],[])
        self.assertEqual(out['field_eligibility'],{});self.assertEqual(result['visibility_summary'],{})
        self.assertEqual(result['counts']['display_records'],1)
        self.assertNotIn('d9', result['counts']);self.assertNotIn('d9',result['counts']['by_stage'])
        self.assertNotIn('d9',result['unmapped_summary'])
        self.assertNotIn('PRIVATE_METADATA',json.dumps(result))
        self.assertEqual(fetch(data,stage='d9')['total'],0)

    def test_visibility_summary_spoof_fails_closed(self):
        data=dataset(); data['visibility_summary']['candidate_visible_local']=1
        self.assertEqual(fetch(data)['visibility_summary'],{'status':'pending_inconsistent'})
        data['visibility_summary']['candidate_visible_local']=0
        data['visibility_summary']['metadata_candidate']=10
        self.assertEqual(fetch(data)['visibility_summary'],{'status':'pending_inconsistent'})
        data['visibility_summary'].update(metadata_candidate=9,other='PRIVATE_METADATA')
        result=fetch(data)
        self.assertEqual(result['visibility_summary']['metadata_candidate'],9)
        self.assertNotIn('PRIVATE_METADATA',json.dumps(result))

    def test_formatted_bibliographic_identifiers_are_not_display_grants(self):
        for mode in ('D8','D9'):
            data=dataset(mode)
            data['records'][0].update(source_doi='10.1234/SYNTHETICUNAPPROVED',source_year=1843,locator='page 834')
            result=fetch(data)
            self.assertIsNone(result['records'][0]['source_doi'])
            self.assertIsNone(result['records'][0]['source_year'])
            self.assertIsNone(result['records'][0]['locator'])
            self.assertNotIn('SYNTHETICUNAPPROVED',json.dumps(result))
            self.assertEqual(fetch(data,q='SYNTHETICUNAPPROVED')['total'],0)
            self.assertEqual(fetch(data,q='1843')['total'],0)
            self.assertEqual(fetch(data,q='page 834')['total'],0)

    def test_observed_criticism_does_not_become_direct_rebuttal(self):
        data=dataset(); row=data['records'][0]
        row['d9_observations']=[{'kind':'relationship','status':'source_checked','method':'unknown',
             'direction':'outgoing','target_key':'d8:sources:5',
             'relation_type':'published_review_criticizes_book_treatment'}]
        self.assertEqual(fetch(data, relation_kind='published_review_criticizes_book_treatment',relation_direction='outgoing')['total'],1)
        self.assertEqual(fetch(data, relation_kind='directly_rebuts')['total'],0)
        observed=fetch(data)['records'][0]['d9_observations'][0]
        self.assertEqual(observed['target_key'],'d8:sources:5')
        self.assertEqual(observed['relation_type'],'published_review_criticizes_book_treatment')
        row['d9_observations'][0].update(target_key='PRIVATE_ID_891',relation_type='PRIVATE_ID_892')
        self.assertNotIn('PRIVATE_ID_',json.dumps(fetch(data)))

    def test_d9_rights_observations_keep_edition_action_and_deny_permissions(self):
        data=dataset(); row=data['records'][0]
        row['d9_rights_observations']=[{'edition_key':'d9:editions:3','action':'browse','decision':'conditional'},
                                       {'edition_key':'d9:editions:8','action':'store_raw','decision':'allowed'}]
        result=fetch(data, rights_action='browse',rights_decision='conditional')
        self.assertEqual(result['total'],1)
        self.assertFalse(result['records'][0]['effective_permissions']['browse'])
        self.assertEqual(fetch(data,rights_action='store_raw',rights_decision='allowed')['total'],0)
        self.assertEqual(fetch(data,rights_action='browse',rights_decision='allowed')['total'],0)

    def test_actual_passages_cannot_inject_hidden_text_or_mix_corpora(self):
        data=dataset(); row=data['records'][0]
        row['passages']=[{'corpus':'Bible','scheme':'chapter_verse_edition_unverified','reference':'John 3:16'},
                         {'corpus':'Quran','scheme':'quran_numbering_edition_unresolved','reference':'3:45'},
                         {'corpus':'Quran','scheme':'quran_numbering_edition_unresolved','reference':'John 3:16'},
                         {'corpus':'PRIVATE_CORPUS','scheme':'PRIVATE_SCHEME','reference':'PRIVATE_REFERENCE'}]
        result=fetch(data); encoded=json.dumps(result)
        self.assertNotIn('PRIVATE_',encoded)
        self.assertEqual(fetch(data,corpus='Quran', reference='John')['total'],0)
        self.assertEqual(fetch(data,corpus='Quran', reference='3:45')['total'],1)
        self.assertEqual(fetch(data,corpus='Bible', reference='John 3:16')['total'],1)

    def test_eligibility_never_accepts_untrusted_values(self):
        data=dataset(); data['records'][0]['field_eligibility']={'source':{'bibliography':'candidate_visible_local',
            'full_text':'candidate_visible_local','private_link':'candidate_visible_local','own_summary':'metadata_candidate',
            'PRIVATE_KEY':'candidate_visible_local'},'PRIVATE_PERSON':{'full_text':'candidate_visible_local'}}
        field=fetch(data)['records'][0]['field_eligibility']
        self.assertEqual(field,{'source':{'bibliography':'unmapped','own_summary':'metadata_candidate','full_text':'unmapped','private_link':'unmapped'}})


class J3HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=PrivatePreviewServer(dataset(),SECRET)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join()
    def request(self, headers):
        client=http.client.HTTPConnection('127.0.0.1',self.server.server_address[1],timeout=3)
        try:
            client.request('GET','/api/candidates',headers={'Host':self.server.expected_host,**headers})
            response=client.getresponse();return response.status,dict(response.getheaders()),response.read()
        finally:client.close()
    def test_real_mode_requires_session_and_correct_origin(self):
        status,_,_=self.request({});self.assertEqual(status,401)
        status,_,_=self.request({'Authorization':'Bearer '+SECRET,'Origin':'http://evil.invalid'});self.assertEqual(status,403)
        status,headers,body=self.request({'Authorization':'Bearer '+SECRET,'Origin':self.server.expected_origin})
        self.assertEqual(status,200);self.assertEqual(json.loads(body)['dataset'],'D9')
        self.assertIn('no-store',headers.get('Cache-Control',''))
        self.assertNotIn('Access-Control-Allow-Origin',headers)

if __name__=='__main__':unittest.main()
