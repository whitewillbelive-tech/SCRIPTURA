"""Synthetic-only J3 field eligibility, version selection, and overlays."""
import copy
import sys
import unittest
from unittest.mock import patch
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'));sys.path.insert(0,str(ROOT/'tests'))
from j2_bridge.candidate_readonly import CandidateError
from j3_bridge import candidate_archive as m
from j3_bridge.eligibility import synthetic_field_is_eligible


def approval():
 return {'entity_id':'synthetic:source','field_group':'bibliography','display_field':'source_title','transformation':'identity',
  'edition_id':'synthetic:edition','locator_id':'synthetic:locator','direct_evidence_url':'https://example.invalid/synthetic-evidence',
  'rights_basis':'synthetic:permission','action':'browse','purpose':'private_local_candidate_review_only',
  'jurisdiction':'synthetic:scope','reviewed_at':'2025-01-01','reviewer':'synthetic:reviewer',
  'limitations':'synthetic:local-only','source_verification_method':'direct_checked','decision':'candidate_visible_local',
  'valid_from':'2024-01-01','valid_until':'2026-12-31','rights_decision':'allowed'}

def request(a):return {k:a[k] for k in ('entity_id','field_group','display_field','transformation','edition_id','locator_id','action','purpose','jurisdiction')}
def entry(n,x):return {'line':n,'value':x,'sha256':'a'*64}

class SyntheticEligibilityTests(unittest.TestCase):
 def test_complete_approval_is_only_synthetic(self):
  a=approval();self.assertTrue(synthetic_field_is_eligible(a,request(a),today='2025-05-01'))
  for field in ('source_title','source_creator','researcher','speaker','community_name'):
   b=approval();b['display_field']=field;self.assertTrue(synthetic_field_is_eligible(b,request(b),today='2025-05-01'))
 def test_each_required_value_is_necessary(self):
  a=approval()
  for k in a:
   with self.subTest(field=k):
    b=approval();b.pop(k);self.assertFalse(synthetic_field_is_eligible(b,request(a),today='2025-05-01'))
 def test_scope_and_exact_field_must_match(self):
  for k in request(approval()):
   with self.subTest(field=k):
    a=approval();q=request(a);q[k]='synthetic:other';self.assertFalse(synthetic_field_is_eligible(a,q,today='2025-05-01'))
 def test_different_content_and_permissions_are_denied(self):
  for changes in ({'decision':'metadata_candidate'},{'rights_decision':'unknown'},{'rights_decision':'conditional'}, {'field_group':'short_quote'}, {'display_field':'full_text'}, {'action':'embed'}, {'transformation':'summarize'}, {'source_verification_method':'search_only'}):
   a=approval();a.update(changes);self.assertFalse(synthetic_field_is_eligible(a,request(a),today='2025-05-01'))
 def test_dates_and_scope_must_be_current(self):
  for today in ('2023-01-01','2027-01-01','2025-02-30','2024-06-01'):
   a=approval();self.assertFalse(synthetic_field_is_eligible(a,request(a),today=today))
  a=approval();a['jurisdiction']='unverified';self.assertFalse(synthetic_field_is_eligible(a,request(a),today='2025-05-01'))
 def test_no_arbitrary_asserted_real_approval(self):
  for field, val in [('entity_id','some-real-id'),('reviewer','unverified-person'),('direct_evidence_url','https://real.example/evidence')]:
   a=approval();a[field]=val;self.assertFalse(synthetic_field_is_eligible(a,request(a),today='2025-05-01'))
 def test_bad_urls_and_dates_rejected(self):
  for v in ('http://example.invalid/evidence','https://a@example.invalid/evidence','https://example.invalid/','https://example.invalid:9999/evidence'):
   a=approval();a['direct_evidence_url']=v;self.assertFalse(synthetic_field_is_eligible(a,request(a),today='2025-05-01'))

class SyntheticVersionTests(unittest.TestCase):
 def test_changed_d8_path_rejected_before_return(self):
  data=b'synthetic-fixed'
  import hashlib
  with patch.object(m.base,'D8_SHA',hashlib.sha256(data).hexdigest()),patch.object(m.prior,'_bounded_read',side_effect=[data,b'changed']),patch.object(m.base,'load_candidate_archive',return_value={'dataset':'D8'}):
   with self.assertRaises(CandidateError):m.load_versioned_archive('/synthetic/test.zip')
 def test_empty_and_unknown_input_fail_closed(self):
  for data in (b'',b'synthetic-unknown'):
   with self.subTest(data=len(data)):
    with self.assertRaises(CandidateError):m.load_versioned_archive(data)
 def test_remote_path_is_rejected_without_read(self):
  for path in ('https://example.invalid/x',r'\\\\server\share\x','//server/share/x'):
   with patch.object(m.prior,'_bounded_read') as read:
    with self.assertRaises(CandidateError):m.load_versioned_archive(path)
    read.assert_not_called()
 def test_overlays_leave_old_source_status_and_input_intact(self):
  layers={'base':{},'d5':{},'d6':{},'d7':{'sources':[entry(1,{'id':'synthetic:oldsource'})], 'editions':[entry(1,{'id':'synthetic:oldedition','source_id':'synthetic:oldsource'})], 'claims':[entry(1,{'id':'synthetic:oldclaim'})]},'d8':{},'d9':{'editions':[entry(1,{'id':'synthetic:newedition','source_id':'synthetic:oldsource'})], 'rights':[entry(1,{'id':'synthetic:r','edition_id':'synthetic:newedition','action':'browse','decision':'unknown'})], 'rights_actions':[entry(1,{'id':'synthetic:obs','source_right_id':'synthetic:r','edition_id':'synthetic:newedition','action':'browse','decision':'unknown'})], 'audit_reviews':[entry(1,{'id':'synthetic:a','baseline_record_id':'synthetic:oldclaim','observation_status':'verified_exact'})], 'claims':[entry(1,{'id':'synthetic:newclaim'})], 'relationships':[entry(1,{'id':'synthetic:rel','subject_id':'synthetic:newclaim','object_id':'synthetic:oldclaim','predicate':'same_community_similar_interpretation','status':'source_checked'})]}}
  original=[{'key':'d7:sources:1','record_kind':'source','stage':'d7','verification_status':'source_checked','edition_rights':[{'key':'d7:editions:1','rights':{'browse':'conditional'}}]}, {'key':'d7:claims:1','record_kind':'claim','stage':'d7','verification_status':'source_checked'}]
  before=copy.deepcopy(original);result=m._attach_d9_observations(original,[],layers,[])
  self.assertEqual(original,before);self.assertEqual(result[0]['verification_status'],'source_checked')
  self.assertEqual(len(result[0]['edition_rights']),2);self.assertEqual(result[0]['edition_rights'][0]['rights']['browse'],'conditional')
  self.assertEqual(result[0]['edition_rights'][1]['rights']['browse'],'unknown');self.assertFalse(any(result[0]['edition_rights'][1]['effective_permissions'].values()))
  self.assertEqual(result[0]['d9_rights_observations'][0]['decision'],'unknown')
  self.assertEqual(result[1]['d9_observations'][0]['kind'],'audit_review');self.assertEqual(result[1]['verification_status'],'source_checked')
  relation=next(x for x in result[1]['d9_observations'] if x['kind']=='relationship');self.assertEqual(relation['relation_type'],'same_community_similar_interpretation');self.assertEqual(relation['direction'],'incoming');self.assertEqual(relation['target_key'],'d9:claims:1')
 def test_visibility_matrix_never_grants_actual_fields(self):
  layers={'base':{},'d5':{},'d6':{},'d7':{},'d8':{},'d9':{'sources':[entry(1,{'id':'synthetic:source'})]}}
  v=[entry(i,{'entity_id':'synthetic:source','field_group':g,'decision':d}) for i,(g,d) in enumerate(zip(m._GROUPS,('metadata_candidate','unknown','unknown','unknown','unmapped')),1)]
  old=[{'key':'d9:sources:1','record_kind':'source','stage':'d9','source_title':None}]
  out=m._attach_d9_observations([],old,layers,v)
  self.assertEqual(out[0]['field_eligibility']['source']['bibliography'],'metadata_candidate');self.assertIsNone(out[0]['source_title'])
  self.assertNotIn('candidate_visible_local',repr(out))

if __name__=='__main__':unittest.main()
