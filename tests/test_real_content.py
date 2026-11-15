"""Synthetic field-level safety tests; no research archive is used."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from k13_bridge.local_candidate import prepare_local_candidate_index
from k37_bridge.real_content import RealContentIndex, build_content_index, content_for_record
from j3_bridge.private_io import PrivateMapping


def fixture():
    def e(value):return {'line':1,'value':value}
    source={'id':'synthetic-src','title':'SYNTHETIC TITLE','creator':'SYNTHETIC CREATOR'}
    edition={'id':'synthetic-ed','source_id':'synthetic-src'}
    locator={'id':'synthetic-loc','source_id':'synthetic-src','edition_id':'synthetic-ed'}
    claim={'id':'synthetic-claim','source_id':'synthetic-src','edition_id':'synthetic-ed',
           'source_locator_id':'synthetic-loc','statement_ko':'SYNTHETIC STATEMENT',
           'reasoning_ko':'SYNTHETIC REASONING','tradition':'SYNTHETIC LABEL','speaker':'SYNTHETIC SPEAKER',
           'verification_method':'자체 요약; 인용 없이','original_text_stored':False}
    evidence={'id':'synthetic-evidence','claim_id':'synthetic-claim','locator_id':'synthetic-loc'}
    layers={'d13':{'sources':[e(source)],'editions':[e(edition)],'locators':[e(locator)],'claims':[e(claim)],'evidence':[e(evidence)],'rights':[]}}
    records=[{'key':'d13:claims:1','stage':'d13','record_kind':'claim','source_key':'d13:sources:1','edition_key':'d13:editions:1'}]
    dataset={'dataset':'D16','records':records}
    return layers,records,dataset


def build(layers,records,dataset):
    candidate=prepare_local_candidate_index(dataset,layers)
    return build_content_index(layers,records,candidate)


class PrivateContentTests(unittest.TestCase):
    def test_opaque_baseline_mapping_is_supported(self):
        layers,records,dataset=fixture()
        candidate=prepare_local_candidate_index(dataset,layers)
        index=build_content_index(PrivateMapping(layers),records,candidate)
        self.assertEqual(content_for_record(index,'D16','d13:claims:1')['summary_status'],'recorded_unverified')

    def test_statement_and_tradition_are_separate_from_reasoning_and_subject(self):
        layers,records,dataset=fixture(); index=build(layers,records,dataset)
        result=content_for_record(index,'D16','d13:claims:1')
        self.assertEqual(result['summary'],'SYNTHETIC STATEMENT')
        self.assertEqual(result['summary_status'],'recorded_unverified')
        self.assertEqual(result['tradition_status'],'recorded_unverified')
        self.assertEqual(result['reported_speaker'],'SYNTHETIC SPEAKER')
        self.assertEqual(result['reported_speaker_status'],'recorded_unverified')
        self.assertEqual(result['reasoning'],'SYNTHETIC REASONING');self.assertEqual(result['reasoning_status'],'local_input_candidate')
        self.assertIsNone(result['subject']);self.assertEqual(result['subject_status'],'pending')
        self.assertNotIn('SYNTHETIC',repr(index))

    def test_reasoning_requires_own_independent_attestation(self):
        layers,records,dataset=fixture(); row=layers['d13']['claims'][0]['value']
        row['reasoning_verification_method']='자체 요약; 인용 없이'; row['reasoning_original_text_stored']=False
        result=content_for_record(build(layers,records,dataset),'D16','d13:claims:1')
        self.assertEqual(result['reasoning'],'SYNTHETIC REASONING')
        row['reasoning_original_quote']='SYNTHETIC QUOTE'
        self.assertIsNone(content_for_record(build(layers,records,dataset),'D16','d13:claims:1')['reasoning'])

    def test_missing_method_or_original_storage_is_a_separate_unreviewed_local_candidate(self):
        layers,records,dataset=fixture()
        for field in ('verification_method','original_text_stored'):
            candidate=copy.deepcopy(layers);candidate['d13']['claims'][0]['value'].pop(field)
            got=content_for_record(build(candidate,records,dataset),'D16','d13:claims:1')
            self.assertEqual(got['summary'],'SYNTHETIC STATEMENT')
            self.assertEqual(got['summary_status'],'local_input_candidate')
            self.assertEqual(got['reasoning'],'SYNTHETIC REASONING')
            self.assertEqual(got['reasoning_status'],'local_input_candidate')

    def test_d12_unattested_notes_are_visible_only_as_private_input_candidates(self):
        layers,records,dataset=fixture()
        layers['d12'] = layers.pop('d13')
        records[0]['key'] = 'd12:claims:1'
        records[0]['stage'] = 'd12'
        records[0]['source_key'] = 'd12:sources:1'
        records[0]['edition_key'] = 'd12:editions:1'
        row = layers['d12']['claims'][0]['value']
        row.pop('verification_method');row.pop('original_text_stored')
        candidate=prepare_local_candidate_index(dataset,layers)
        result=content_for_record(build_content_index(layers,records,candidate),'D16','d12:claims:1')
        self.assertEqual(result['summary_status'],'local_input_candidate')
        self.assertEqual(result['reasoning_status'],'local_input_candidate')
        row['statement_original_quote'] = 'SYNTHETIC QUOTATION'
        result=content_for_record(build_content_index(layers,records,candidate),'D16','d12:claims:1')
        self.assertIsNone(result['summary'])

    def test_unattested_research_reasoning_remains_unreviewed(self):
        layers,records,dataset=fixture()
        row=layers['d13']['claims'][0]['value']
        row.pop('verification_method');row.pop('original_text_stored')
        result=content_for_record(build(layers,records,dataset),'D16','d13:claims:1')
        self.assertEqual(result['summary_status'],'local_input_candidate')
        self.assertEqual(result['reasoning'],'SYNTHETIC REASONING')
        self.assertEqual(result['reasoning_status'],'local_input_candidate')
        self.assertIsNone(result['subject'])  # no official/speaker promotion

    def test_explicit_original_text_storage_and_quote_still_block(self):
        layers,records,dataset=fixture(); row=layers['d13']['claims'][0]['value']
        row['original_text_stored']=True
        result=content_for_record(build(layers,records,dataset),'D16','d13:claims:1')
        self.assertIsNone(result['summary']);self.assertIsNone(result['reasoning'])
        row['original_text_stored']=False;row.pop('verification_method')
        row['statement_original_quote']='SYNTHETIC DIRECT QUOTE'
        result=content_for_record(build(layers,records,dataset),'D16','d13:claims:1')
        self.assertIsNone(result['summary']);self.assertEqual(result['reasoning_status'],'local_input_candidate')
        row.pop('statement_original_quote');row['restricted_fields']=['reasoning_ko']
        result=content_for_record(build(layers,records,dataset),'D16','d13:claims:1')
        self.assertIsNone(result['reasoning'])

    def test_field_privacy_and_conditional_rights_are_not_overridden(self):
        layers,records,dataset=fixture(); row=layers['d13']['claims'][0]['value']
        row['restricted_fields']=['statement_ko']
        result=content_for_record(build(layers,records,dataset),'D16','d13:claims:1')
        self.assertIsNone(result['summary']);self.assertEqual(result['tradition_status'],'recorded_unverified')
        layers['d13']['rights']=[{'line':1,'value':{'edition_id':'synthetic-ed','action':'tradition','permission':'conditional'}}]
        result=content_for_record(build(layers,records,dataset),'D16','d13:claims:1')
        self.assertIsNone(result['tradition'])

    def test_exact_source_chain_and_sealed_index_are_required(self):
        layers,records,dataset=fixture(); layers['d13']['locators'][0]['value']['source_id']='synthetic-other'
        self.assertEqual(content_for_record(build(layers,records,dataset),'D16','d13:claims:1'),{})
        self.assertEqual(content_for_record({'d13:claims:1':{'summary':'SYNTHETIC FORGED'}},'D16','d13:claims:1'),{})
        with self.assertRaises(ValueError):RealContentIndex(None,{})

    def test_missing_evidence_does_not_hide_unverified_tradition(self):
        layers,records,dataset=fixture();layers['d13']['evidence']=[]
        result=content_for_record(build(layers,records,dataset),'D16','d13:claims:1')
        self.assertIsNone(result['summary']);self.assertEqual(result['tradition_status'],'recorded_unverified')

    def test_recorded_speaker_does_not_become_verified_subject_and_can_be_restricted(self):
        layers,records,dataset=fixture()
        result=content_for_record(build(layers,records,dataset),'D16','d13:claims:1')
        self.assertEqual(result['reported_speaker_status'],'recorded_unverified')
        self.assertIsNone(result['subject']);self.assertEqual(result['subject_status'],'pending')
        layers['d13']['sources'][0]['value']['private_fields']=['speaker']
        result=content_for_record(build(layers,records,dataset),'D16','d13:claims:1')
        self.assertIsNone(result['reported_speaker'])
        layers['d13']['sources'][0]['value'].pop('private_fields')
        layers['d13']['claims'][0]['value']['speaker']='private@example.invalid'
        result=content_for_record(build(layers,records,dataset),'D16','d13:claims:1')
        self.assertIsNone(result['reported_speaker'])

    def test_known_private_agent_never_appears_as_recorded_speaker(self):
        layers,records,dataset=fixture()
        layers['d13']['agents']=[{'line':1,'value':{'id':'synthetic-agent','name':'SYNTHETIC SPEAKER','is_private':True}}]
        result=content_for_record(build(layers,records,dataset),'D16','d13:claims:1')
        self.assertIsNone(result['reported_speaker'])
        self.assertEqual(result['reported_speaker_status'],'pending')

    def test_locator_specific_rights_cannot_be_skipped(self):
        layers,records,dataset=fixture()
        layers['d13']['rights']=[{'line':1,'value':{'source_locator_id':'synthetic-loc','action':'speaker','permission':'denied'}}]
        result=content_for_record(build(layers,records,dataset),'D16','d13:claims:1')
        self.assertIsNone(result['reported_speaker'])
        self.assertEqual(result['reported_speaker_status'],'pending')
        self.assertEqual(result['tradition_status'],'recorded_unverified')
        layers['d13']['rights'][0]['value']['action']='display speaker'
        layers['d13']['rights'][0]['value']['permission']='not permitted'
        result=content_for_record(build(layers,records,dataset),'D16','d13:claims:1')
        self.assertIsNone(result['reported_speaker'])
        layers['d13']['rights'][0]['value']['action']='local display'
        result=content_for_record(build(layers,records,dataset),'D16','d13:claims:1')
        self.assertIsNone(result['reported_speaker'])
        self.assertIsNone(result['tradition'])

if __name__=='__main__':unittest.main()
