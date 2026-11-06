"""Synthetic-only D9 structural and private-output protections."""
import collections
import contextlib
import copy
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from j3_bridge import d9_validation as m
from j3_bridge.private_io import PrivateLayers,read_checked_d8_layers,safe_error_count

def e(n,x):return {'line':n,'value':x}
def fixture():
 prior={'base':{},'d5':{},'d6':{},'d7':{'claims':[e(1,{'id':'synthetic:oldclaim','verification_status':'source_checked'})]},'d8':{}}
 d={t:[] for t in m.TABLE_COUNTS}
 d['sources']=[e(1,{'id':'synthetic:source','title':'fake','creator':'fake','url':'https://example.invalid','kind':'article'})]
 d['editions']=[e(1,{'id':'synthetic:edition','source_id':'synthetic:source','label':'fake'})]
 d['locators']=[e(1,{'id':'synthetic:locator','edition_id':'synthetic:edition','location':'p. 1','verification_status':'pending'})]
 d['passages']=[e(1,{'id':'synthetic:passage','corpus':'Bible','reference_scheme':'synthetic','reference':'John 1:1'})]
 d['claims']=[e(1,{'id':'synthetic:claim','community_id':None,'source_locator_id':'synthetic:locator','passage_ids':['synthetic:passage'],'attribution_kind':'individual_opinion','verification_status':'source_checked'})]
 d['evidence']=[e(1,{'id':'synthetic:evidence','claim_id':'synthetic:claim','locator_id':'synthetic:locator','status':'pending'})]
 d['audit_reviews']=[e(1,{'id':'synthetic:audit','baseline_record_id':'synthetic:oldclaim','previous_verification_status':'source_checked','observation_status':'pending'})]
 d['review_queue']=[e(1,{'id':'synthetic:queue','baseline_target_id':'synthetic:oldclaim','target_kind':'claim','result_status':'pending','prior_status':'source_checked'})]
 d['rights']=[e(i,{'id':'synthetic:right:'+a,'edition_id':'synthetic:edition','action':a,'decision':'unknown','evidence_locator_id':None}) for i,a in enumerate(sorted(m.p.ACTIONS),1)]
 d['rights_actions']=[e(i,{'id':'synthetic:obs:'+a,'edition_id':'synthetic:edition','source_right_id':'synthetic:right:'+a,'action':a,'decision':'unknown','source_origin':'D9_new_right'}) for i,a in enumerate(sorted(m.p.ACTIONS),1)]
 v=[e(i,{'id':'synthetic:elig:'+g,'entity_id':'synthetic:source','entity_kind':'source','field_group':g,'decision':'metadata_candidate' if g=='bibliography' else 'unknown'}) for i,g in enumerate(sorted(m.GROUPS),1)]
 return prior,d,v
class D9ValidationTests(unittest.TestCase):
 def setUp(self):self.prior,self.d,self.v=fixture()
 def errors(self):return m.validate_d9(self.d,self.prior,self.v,expected_counts=False)[0]
 def test_valid_candidate_and_no_automatic_approval(self):
  before=copy.deepcopy((self.prior,self.d,self.v));self.assertFalse(self.errors());self.assertEqual(before,(self.prior,self.d,self.v))
 def test_missing_and_wrong_reference(self):
  self.d['claims'][0]['value']['source_locator_id']='synthetic:missing';self.assertIn('unresolved_reference',self.errors())
  self.d['claims'][0]['value']['source_locator_id']='synthetic:source';self.assertIn('reference_wrong_type',self.errors())
 def test_missing_required_field_and_id_collision(self):
  del self.d['claims'][0]['value']['source_locator_id'];self.assertIn('required_field_missing',self.errors())
  self.d['claims'][0]['value']['id']='synthetic:source';self.assertIn('duplicate_id',self.errors())
 def test_unverified_official_and_human_review_denied(self):
  row=self.d['claims'][0]['value'];row['attribution_kind']='official_doctrine';row['scholarly_reviewed']=True
  errors=self.errors();self.assertIn('official_claim_requires_manual_review',errors);self.assertIn('unsupported_human_review',errors)
 def test_rights_incomplete_and_unknown_not_granted(self):
  self.d['rights'].pop();self.assertIn('rights_matrix_incomplete',self.errors())
 def test_rights_observation_cannot_change_original(self):
  self.d['rights_actions'][0]['value']['decision']='allowed';self.assertIn('rights_observation_mismatch',self.errors())
 def test_queue_and_evidence_cannot_change_source(self):
  self.d['review_queue'][0]['value']['prior_status']='scholarly_reviewed';self.assertIn('queue_previous_status_changed',self.errors())
  self.d['evidence'][0]['value']['locator_id']='synthetic:source';self.assertIn('reference_wrong_type',self.errors())
 def test_audit_cannot_rewrite_past(self):
  self.d['audit_reviews'][0]['value']['previous_verification_status']='verified';self.assertIn('audit_previous_status_changed',self.errors())
 def test_visibility_candidate_never_promoted(self):
  self.assertEqual(self.v[0]['value']['decision'],'metadata_candidate');self.assertFalse(self.errors())
  self.v[0]['value']['decision']='candidate_visible_local';self.assertIn('unexpected_actual_visibility_approval',self.errors())
 def test_eligibility_bad_entity_and_duplicate_id(self):
  self.v[0]['value']['entity_id']='synthetic:claim';self.v[0]['value']['entity_kind']='source';self.assertIn('eligibility_entity_invalid',self.errors())
  self.v[1]['value']['id']=self.v[0]['value']['id'];self.assertIn('eligibility_id_invalid',self.errors())
 def test_wrong_queue_target_coverage(self):
  targets=[e(1,{'baseline_target_id':'synthetic:missing'})]
  self.assertIn('queue_target_coverage_mismatch',m.validate_d9(self.d,self.prior,self.v,baseline_targets=targets,expected_counts=False)[0])
 def test_unapproved_raw_text_rejected(self):
  self.d['sources'][0]['value']['full_text']='SYNTHETIC_PRIVATE_SENTINEL';self.assertIn('prohibited_content_field',self.errors())
 def test_scope_reports_cannot_hide_duplicates(self):
  aux={'SOURCE_ACCESS_INDEX':[e(1,{'source_id':'synthetic:source','edition_ids':['synthetic:edition'],'locator_ids':['synthetic:locator'],'access_event_ids':[]})], 'SOURCE_DUPLICATE_REVIEW':[e(1,{'source_id':'synthetic:source'})]}
  self.assertFalse(m.validate_d9(self.d,self.prior,self.v,auxiliary=aux,expected_counts=False)[0])
  aux['SOURCE_ACCESS_INDEX'].append(e(2,aux['SOURCE_ACCESS_INDEX'][0]['value']))
  self.assertIn('source_report_coverage_mismatch',m.validate_d9(self.d,self.prior,self.v,auxiliary=aux,expected_counts=False)[0])
class PrivateOutputTests(unittest.TestCase):
 def test_carrier_repr_hides_values(self):
  sentinel='SYNTHETIC_PRIVATE_SENTINEL'
  c=PrivateLayers({'k':sentinel},{'k':sentinel},0)
  self.assertNotIn(sentinel,repr(c));self.assertNotIn(sentinel,str(c))
 def test_aux_dict_cannot_be_confused_with_counter(self):
  with self.assertRaisesRegex(ValueError,'invalid_error_counter'):safe_error_count({'SYNTHETIC_PRIVATE_SENTINEL':[]})
  with self.assertRaisesRegex(ValueError,'invalid_error_counter'):safe_error_count(collections.Counter({'SYNTHETIC_PRIVATE_SENTINEL':2}))
  self.assertEqual(safe_error_count(collections.Counter({'invalid_jsonl':2})),2)
 def test_no_sensitive_exception_or_logging(self):
  sentinel='SYNTHETIC_PRIVATE_SENTINEL';stdout=io.StringIO();stderr=io.StringIO()
  with patch('j3_bridge.private_io.base._read_layers',side_effect=RuntimeError(sentinel)),contextlib.redirect_stdout(stdout),contextlib.redirect_stderr(stderr):
   with self.assertRaises(ValueError) as cm:read_checked_d8_layers(None)
  self.assertNotIn(sentinel,str(cm.exception));self.assertNotIn(sentinel,stdout.getvalue());self.assertNotIn(sentinel,stderr.getvalue())

if __name__=='__main__':unittest.main()
