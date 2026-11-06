"""Synthetic J-1 mutation tests. No external research archive is opened."""
import copy
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from j1_bridge import d7 as m

def row(value,n=1):return {'value':value,'line':n,'sha256':'f'*64}
def synthetic():
 base={};d5={'authority_registries':[row({'id':'syn:registry','tradition_id':'syn:tradition'})]}
 d6={'claims':[row({'id':'syn:d6claim','verification_status':'source_checked','source_locator_id':'syn:d6loc'})], 'assessments':[row({'id':'syn:d6assessment','source_verification':'published_source_checked','locator_id':'syn:d6loc'})], 'locators':[row({'id':'syn:d6loc'})]}
 d7={t:[] for t in m.TABLES}
 d7['sources']=[row({'id':'syn:source','title':'synthetic source','creator':'synthetic','url':'https://example.invalid/source','kind':'synthetic'})]
 d7['editions']=[row({'id':'syn:edition','source_id':'syn:source','label':'synthetic'})]
 d7['locators']=[row({'id':'syn:locator','edition_id':'syn:edition','location':'synthetic','verification_status':'pending'})]
 d7['passages']=[row({'id':'syn:passage','corpus':'Bible','reference_scheme':'pending','reference':'synthetic'})]
 d7['claims']=[row({'id':'syn:claim','community_id':'syn:tradition','source_locator_id':'syn:locator','passage_ids':['syn:passage'],'statement_ko':'synthetic','attribution_kind':'community_self_explanation','authority_status':'unknown','verification_status':'pending'})]
 d7['evidence']=[row({'id':'syn:evidence','claim_id':'syn:claim','locator_id':'syn:locator'})]
 d7['rights']=[row({'id':'syn:right:'+a,'edition_id':'syn:edition','action':a,'decision':'unknown','evidence_locator_id':None},i+1) for i,a in enumerate(sorted(m.prior.ACTIONS))]
 def audit(i,target,old,status):return row({'id':'syn:audit'+str(i),'baseline_record_id':target,'previous_verification_status':old,'observation_status':status,'access_method':'synthetic','checked_at':'2025-01-01','locator_id':'syn:d6loc','note':'synthetic'},i)
 d7['audit_reviews']=[audit(1,'syn:d6claim','source_checked','checked'),audit(2,'syn:d6claim','source_checked','blocked'),audit(3,'syn:d6assessment','published_source_checked','checked')]
 cross=[row({'baseline_id':'syn:d6claim','baseline_type':'claim','baseline_locator_id':'syn:d6loc','prior_verification_status':'source_checked','d7_audit_ids':['syn:audit1','syn:audit2'],'d7_observation_statuses':['checked','blocked']}),row({'baseline_id':'syn:d6assessment','baseline_type':'assessment','baseline_locator_id':'syn:d6loc','prior_verification_status':'published_source_checked','d7_audit_ids':['syn:audit3'],'d7_observation_statuses':['checked']},2)]
 return base,d5,d6,d7,cross

class D7Tests(unittest.TestCase):
 def setUp(self):self.base,self.d5,self.d6,self.d7,self.cross=synthetic()
 def check(self):return m.validate_records(self.base,self.d5,self.d6,self.d7,self.cross)[0]
 def test_valid_and_multiple_audit_observations(self):
  self.assertFalse(self.check());self.assertEqual(len(self.d7['audit_reviews']),3)
 def test_frozen_null_previous_status_preserved(self):
  obj=self.d6['assessments'][0]['value'];obj.pop('source_verification');self.d7['audit_reviews'][2]['value']['previous_verification_status']=None;self.cross[1]['value']['prior_verification_status']=None;self.assertFalse(self.check())
 def test_assessment_verification_status_fallback(self):
  obj=self.d6['assessments'][0]['value'];obj['verification_status']=obj.pop('source_verification');self.assertFalse(self.check())
 def test_conflicting_baseline_status_fields(self):
  self.d6['assessments'][0]['value']['verification_status']='different';self.assertIn('baseline_status_fields_conflict',self.check())
 def test_previous_status_not_changed(self):
  self.d7['audit_reviews'][0]['value']['previous_verification_status']='invented';self.assertIn('audit_previous_status_changed',self.check())
 def test_audit_target_must_be_d6(self):
  self.d7['audit_reviews'][0]['value']['baseline_record_id']='syn:claim';self.assertIn('audit_target_not_d6',self.check())
 def test_audit_coverage_missing(self):
  self.d7['audit_reviews']=self.d7['audit_reviews'][:2];self.assertIn('audit_coverage_incomplete',self.check())
 def test_audit_wrong_target_type(self):
  self.d7['audit_reviews'][0]['value']['baseline_record_id']='syn:d6loc';self.assertIn('reference_wrong_type',self.check())
 def test_crosswalk_events_must_be_complete(self):
  self.cross[0]['value']['d7_audit_ids']=['syn:audit1'];self.assertIn('crosswalk_event_mismatch',self.check())
 def test_crosswalk_status_correct(self):
  self.cross[0]['value']['prior_verification_status']='other';self.assertIn('crosswalk_previous_status_changed',self.check())
 def test_crosswalk_observations_correct(self):
  self.cross[0]['value']['d7_observation_statuses']=['checked'];self.assertIn('crosswalk_observation_mismatch',self.check())
 def test_crosswalk_locator_correct(self):
  self.cross[0]['value']['baseline_locator_id']='syn:locator';self.assertIn('crosswalk_locator_mismatch',self.check())
 def test_crosswalk_duplicate_target(self):
  self.cross.append(copy.deepcopy(self.cross[0]));self.assertIn('crosswalk_target_invalid',self.check())
 def test_duplicate_id_across_layers(self):
  self.d7['sources'][0]['value']['id']='syn:d6claim';self.assertIn('duplicate_id_across_layers',self.check())
 def test_missing_source(self):
  self.d7['editions'][0]['value']['source_id']='syn:missing';self.assertIn('reference_unresolved',self.check())
 def test_claim_community_wrong_type(self):
  self.d7['claims'][0]['value']['community_id']='syn:source';self.assertIn('reference_wrong_type',self.check())
 def test_null_community_not_fabricated(self):
  c=self.d7['claims'][0]['value'];c['community_id']=None;c['attribution_kind']='academic_interpretation';self.assertFalse(self.check());self.assertIsNone(c['community_id'])
 def test_pending_essential_foreign_key(self):
  self.d7['claims'][0]['value']['source_locator_id']='pending';self.assertIn('required_reference_pending',self.check())
 def test_evidence_claim_locator_mismatch(self):
  self.d7['evidence'][0]['value']['locator_id']='syn:d6loc';self.assertIn('claim_evidence_locator_mismatch',self.check())
 def test_no_official_promotion(self):
  self.d7['claims'][0]['value']['attribution_kind']='official_doctrine';self.assertIn('official_claim_requires_manual_review',self.check())
 def test_no_unaudited_independent_review(self):
  self.d7['claims'][0]['value']['independent_human_review']=True;self.assertIn('unverified_review_or_raw_storage',self.check())
 def test_no_raw_stored(self):
  self.d7['claims'][0]['value']['raw_text_stored']=True;self.assertIn('unverified_review_or_raw_storage',self.check())
 def test_complete_nine_rights(self):
  self.d7['rights'].pop();self.assertIn('rights_matrix_incomplete',self.check())
 def test_conditional_rights_require_evidence(self):
  self.d7['rights'][0]['value']['decision']='conditional';self.assertIn('permission_evidence_missing',self.check())
 def test_unknown_rights_preserved(self):
  d=self.d7['rights'][0]['value'];d['decision']='UNKNOWN';self.assertFalse(self.check());self.assertEqual(d['decision'],'UNKNOWN')
 def test_no_unsubstantiated_direct_rebuttal(self):
  self.d7['relationships']=[row({'id':'syn:r','subject_id':'syn:claim','object_id':'syn:d6claim','predicate':'rebuts','locator_id':'syn:locator','status':'verified'})];self.assertIn('unsupported_direct_rebuttal',self.check())
 def test_title_duplicates_are_pending_coordinates_only(self):
  self.d6['sources']=[row({'id':'syn:older','title':'Same Title'})];self.d7['sources'][0]['value']['title']='  same   title ';counts,candidates=m._duplicates(self.base,self.d5,self.d6,self.d7);self.assertEqual(counts['title_candidates'],1);self.assertNotIn('Same Title',str(candidates));self.assertEqual(candidates[0]['disposition'],'pending_not_merged')
 def test_input_immutable(self):
  initial=copy.deepcopy((self.base,self.d5,self.d6,self.d7,self.cross));self.check();self.assertEqual(initial,(self.base,self.d5,self.d6,self.d7,self.cross))
 def test_aux_source_index_unique_and_complete(self):
  sources={'sources':[row({'id':'syn:one'}),row({'id':'syn:two'},2)],'editions':[],'locators':[],'source_access_events':[]}
  aux={f'd7/reports/{name}.jsonl':[row({'source_id':'syn:one','edition_ids':[],'locator_ids':[],'access_event_ids':[]}),row({'source_id':'syn:two','edition_ids':[],'locator_ids':[],'access_event_ids':[]},2)] for name in ('SOURCE_DUPLICATE_REVIEW','SOURCE_ACCESS_INDEX')}
  self.assertFalse(m.validate_aux_source_coverage(sources,aux))
  aux['d7/reports/SOURCE_DUPLICATE_REVIEW.jsonl'][1]['value']['source_id']='syn:one'
  self.assertIn('auxiliary_source_coverage_mismatch',m.validate_aux_source_coverage(sources,aux))
 def test_aux_source_index_cross_source_links_rejected(self):
  s={'sources':[row({'id':'syn:one'})],'editions':[row({'id':'syn:e','source_id':'syn:other'})],'locators':[row({'id':'syn:l','edition_id':'syn:e'})],'source_access_events':[row({'id':'syn:a','locator_id':'syn:l'})]}
  aux={'d7/reports/SOURCE_DUPLICATE_REVIEW.jsonl':[row({'source_id':'syn:one'})],'d7/reports/SOURCE_ACCESS_INDEX.jsonl':[row({'source_id':'syn:one','edition_ids':['syn:e'],'locator_ids':['syn:l'],'access_event_ids':['syn:a']})]}
  errors=m.validate_aux_source_coverage(s,aux);self.assertEqual(errors['access_index_source_mismatch'],3)
 def test_unknown_relation_is_pending_not_inferred(self):
  rows=[row({'predicate':'unregistered_relation'})];self.assertEqual(m._unknown_relation_count(rows),1)
 def test_wrong_archive_rejected_before_write(self):
  with tempfile.TemporaryDirectory() as d:
   f=Path(d)/'archive.zip';f.write_bytes(b'synthetic');report=m.inspect_archive(f);self.assertIn('d7_sha_mismatch',report['errors']);self.assertFalse(report['database_write']);self.assertFalse(report['canonical_promotion'])
if __name__=='__main__':unittest.main()
