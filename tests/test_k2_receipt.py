"""Synthetic D12 receipt invariants; never loads research materials."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from k2_bridge.receipt import _validate,load_k2_archive,safe_k2_passage,_summary_index,summary_for_record,_tradition_index,tradition_for_record
from j2_bridge.candidate_readonly import CandidateError


def entry(value): return {'line':1,'value':value}

def fixture():
    passages=[entry({'id':f'synthetic:p:{n}'}) for n in range(26)]
    links=list(range(25))+list(range(16))+[0,1,2]
    sources=[entry({'id':f'synthetic:s:{i}'}) for i in range(41)]
    editions=[entry({'id':f'synthetic:e:{i}','source_id':f'synthetic:s:{i}'}) for i in range(41)]
    locators=[entry({'id':f'synthetic:l:{i}','source_id':f'synthetic:s:{i%41}','edition_id':f'synthetic:e:{i%41}'}) for i in range(42)]
    claims=[entry({'id':f'synthetic:c:{i}','source_locator_id':f'synthetic:l:{i%42}','passage_ids':[f'synthetic:p:{n}']}) for i,n in enumerate(links)]
    evidence=[entry({'id':f'synthetic:v:{i}','claim_id':f'synthetic:c:{i}','locator_id':f'synthetic:l:{i%42}'}) for i in range(44)]
    return {'d11':{'sources':[]},'d12':{'sources':sources,'editions':editions,'locators':locators,'claims':claims,'passages':passages,'evidence':evidence}}

class K2ReceiptTests(unittest.TestCase):
    def test_valid_counts_distinguish_one_unused_address(self):
        r=_validate(fixture());self.assertEqual(r['passages'],26);self.assertEqual(r['claim_passage_links'],44);self.assertEqual(r['multiple_passages'],16)
    def test_duplicate_claim_fails_closed(self):
        x=fixture();x['d12']['claims'][1]['value']['id']=x['d12']['claims'][0]['value']['id']
        with self.assertRaises(CandidateError):_validate(x)
    def test_dangling_passage_fails_closed(self):
        x=fixture();x['d12']['claims'][0]['value']['passage_ids']=['synthetic:missing']
        with self.assertRaises(CandidateError):_validate(x)
    def test_dangling_evidence_fails_closed(self):
        x=fixture();x['d12']['evidence'][0]['value']['claim_id']='synthetic:missing'
        with self.assertRaises(CandidateError):_validate(x)
    def test_bad_edition_fails_closed(self):
        x=fixture();x['d12']['locators'][0]['value']['edition_id']='synthetic:missing'
        with self.assertRaises(CandidateError):_validate(x)
    def test_wrong_source_edition_pair_fails_closed(self):
        x=fixture();x['d12']['locators'][0]['value']['source_id']='synthetic:s:2'
        with self.assertRaises(CandidateError):_validate(x)
    def test_evidence_other_locator_fails_closed(self):
        x=fixture();x['d12']['evidence'][0]['value']['locator_id']='synthetic:l:2'
        with self.assertRaises(CandidateError):_validate(x)
    def test_canonical_addresses_reject_prose_and_preserve_compounds(self):
        p={'corpus':'Bible_1','scheme':'d12_scheme_1','reference':'John 1:1; 2:3'}
        self.assertIsNotNone(safe_k2_passage(p))
        self.assertIsNone(safe_k2_passage(dict(p,reference='John 1:1; untrusted prose')))
        self.assertIsNone(safe_k2_passage(dict(p,corpus='Quran_1')))
    def test_sealed_summary_requires_own_nonquote_and_exact_chain(self):
        class I:
            def for_record(self,d,k): return {'source_title':{'status':'recorded_unverified'}}
        row={'id':'synthetic:c','source_locator_id':'synthetic:l','verification_method':'자체 요약 인용 없이','original_text_stored':False,'statement_ko':'SYNTHETIC candidate'}
        layers={'d12':{'claims':[entry(row)],'sources':[entry({'id':'synthetic:s'})],
                 'editions':[entry({'id':'synthetic:e','source_id':'synthetic:s'})],
                 'locators':[entry({'id':'synthetic:l','source_id':'synthetic:s','edition_id':'synthetic:e'})],
                 'evidence':[entry({'claim_id':'synthetic:c','locator_id':'synthetic:l'})],'rights':[]}}
        records=[{'key':'d12:claims:1'}]
        i=_summary_index(layers,records,I());self.assertEqual(summary_for_record(i,'D12','d12:claims:1'),'SYNTHETIC candidate')
        row['statement_original_quote']='SYNTHETIC quotation'
        self.assertIsNone(summary_for_record(_summary_index(layers,records,I()),'D12','d12:claims:1'))
        row['statement_original_quote']='';row['verification_method']='자체 요약 인용 없이 아님'
        self.assertIsNone(summary_for_record(_summary_index(layers,records,I()),'D12','d12:claims:1'))
        row['verification_method']='자체 요약 인용 없이';layers['d12']['rights']=[entry({'source_id':'synthetic:s','action':'own_summary','decision':'conditional'})]
        self.assertIsNone(summary_for_record(_summary_index(layers,records,I()),'D12','d12:claims:1'))
        layers['d12']['rights']=[entry({'source_id':'synthetic:s','action':' own-summary ','permission':' CONDITIONAL '})]
        self.assertIsNone(summary_for_record(_summary_index(layers,records,I()),'D12','d12:claims:1'))
        layers['d12']['rights']=[entry({'source_id':'synthetic:s','action':'summary','new_decision':'denied'})]
        self.assertIsNone(summary_for_record(_summary_index(layers,records,I()),'D12','d12:claims:1'))
        layers['d12']['rights']=[];row['field_restrictions']={'statement_ko':'restricted'}
        self.assertIsNone(summary_for_record(_summary_index(layers,records,I()),'D12','d12:claims:1'))
    def test_unverified_tradition_sealed_and_private_restriction(self):
        class I:
            def for_record(self,d,k): return {'source_title':{'status':'recorded_unverified'}}
        row={'id':'synthetic:c','tradition':'SYNTHETIC label','source_locator_id':'synthetic:l'}
        source={'id':'synthetic:s'};edition={'id':'synthetic:e','source_id':'synthetic:s'};locator={'id':'synthetic:l','source_id':'synthetic:s','edition_id':'synthetic:e'}
        layers={'d12':{'claims':[entry(row)],'sources':[entry(source)],'editions':[entry(edition)],'locators':[entry(locator)],'rights':[]}}
        records=[{'key':'d12:claims:1'}]
        i=_tradition_index(layers,records,I());self.assertEqual(tradition_for_record(i,'D12','d12:claims:1'),'SYNTHETIC label')
        row['private_fields']=['tradition'];i=_tradition_index(layers,records,I())
        self.assertIsNone(tradition_for_record(i,'D12','d12:claims:1'))
        row.pop('private_fields');row['tradition']='https://example.invalid/private';i=_tradition_index(layers,records,I())
        self.assertIsNone(tradition_for_record(i,'D12','d12:claims:1'))
        self.assertIsNone(tradition_for_record({'fake':'SYNTHETIC'},'D12','d12:claims:1'))
        row['tradition']='SYNTHETIC label';source['private_fields']=['tradition']
        self.assertIsNone(tradition_for_record(_tradition_index(layers,records,I()),'D12','d12:claims:1'))
        source.pop('private_fields');layers['d12']['rights']=[entry({'source_id':'synthetic:s','action':'tradition','permission':'conditional'})]
        self.assertIsNone(tradition_for_record(_tradition_index(layers,records,I()),'D12','d12:claims:1'))
    def test_url_and_unc_rejected_without_path_leak(self):
        for path in ('https://example.invalid/SYNTHETIC_PRIVATE','//SYNTHETIC_PRIVATE/input'):
            with self.assertRaises(CandidateError) as caught: load_k2_archive(path)
            self.assertNotIn('SYNTHETIC_PRIVATE',str(caught.exception))

if __name__=='__main__': unittest.main()
