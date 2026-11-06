"""Synthetic I-3 adversarial tests. No external research archive is read."""
import collections
import copy
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from i3_bridge import d6 as m


def row(x,n=1):
 return {'value':x,'line':n,'sha256':'a'*64}

def fixture():
 base={'claims':[row({'id':'synthetic:baseline-claim'})]}
 d5={'authority_registries':[row({'id':'synthetic:registry','tradition_id':'synthetic:tradition'})]}
 d6={t:[] for t in m.TABLES}
 d6['communities']=[row({'id':'synthetic:community','canonical_name':'synthetic','self_designation':'synthetic','aliases':[],'relation_to_bible':'synthetic','authority_structure':'pending','coverage_status':'pending','independent_review_status':'none'})]
 d6['sources']=[row({'id':'synthetic:source','title':'synthetic','creator':'synthetic','url':'https://example.invalid','kind':'synthetic'})]
 d6['editions']=[row({'id':'synthetic:edition','source_id':'synthetic:source','label':'synthetic'})]
 d6['locators']=[row({'id':'synthetic:locator','edition_id':'synthetic:edition','location':'synthetic','verification_status':'pending'}),row({'id':'synthetic:locator2','edition_id':'synthetic:edition','location':'synthetic','verification_status':'pending'},2)]
 d6['passages']=[row({'id':'synthetic:passage','corpus':'synthetic','reference_scheme':'unknown','reference':'synthetic'})]
 d6['claims']=[row({'id':'synthetic:claim','community_id':'synthetic:community','source_locator_id':'synthetic:locator','passage_ids':['synthetic:passage'],'statement_ko':'synthetic','attribution_kind':'community_self_explanation','authority_status':'unknown','verification_status':'pending'})]
 d6['assessments']=[row({'id':'synthetic:assessment','target_community_id':'synthetic:community','assessor':'synthetic','assessment_date':None,'status_as_of':'pending','locator_id':'synthetic:locator'})]
 d6['rights']=[row({'id':f'synthetic:right:{action}','edition_id':'synthetic:edition','action':action,'decision':'unknown','evidence_locator_id':None},i+1) for i,action in enumerate(sorted(m.ACTIONS))]
 d6['relationships']=[row({'id':'synthetic:relation','subject_id':'synthetic:claim','object_id':'synthetic:assessment','predicate':'response_to_specific_assessment_candidate','locator_id':'synthetic:locator','status':'pending'})]
 d6['authority']=[row({'id':'synthetic:authority','community_id':'synthetic:tradition','edition_id':'synthetic:edition'})]
 d6['evidence']=[row({'id':'synthetic:evidence','claim_id':'synthetic:claim','locator_id':'synthetic:locator'})]
 return base,d5,d6

class SyntheticD6Tests(unittest.TestCase):
 def setUp(self):self.base,self.d5,self.d6=fixture()
 def errors(self):return m.validate_records(self.base,self.d5,self.d6)[0]
 def test_valid_synthetic(self):self.assertFalse(self.errors())
 def test_duplicate_id(self):
  self.d6['sources'][0]['value']['id']='synthetic:community';self.assertIn('duplicate_record_id',self.errors())
 def test_null_community_is_not_assigned(self):
  c=self.d6['claims'][0]['value'];c['community_id']=None;c['attribution_kind']='academic_interpretation'
  self.assertFalse(self.errors());self.assertIsNone(c['community_id'])
 def test_known_tradition_alias_is_not_new_community(self):
  self.d6['claims'][0]['value']['community_id']='synthetic:tradition';self.assertFalse(self.errors());self.assertEqual(len(self.d6['communities']),1)
 def test_tradition_alias_maps_to_original_registry_row_without_identifier_hash(self):
  self.d6['claims'][0]['value']['community_id']='synthetic:tradition'
  errors,refs=m.validate_records(self.base,self.d5,self.d6)
  self.assertFalse(errors)
  r=next(r for r in refs if r['table']=='claims' and r['field']=='community_id')
  self.assertEqual((r['target_table'],r['target_field'],r['target_row']),('authority_registries','tradition_id',1))
  self.assertNotIn('target_id_sha256',r)
 def test_claim_wrong_type_community(self):
  self.d6['claims'][0]['value']['community_id']='synthetic:source';self.assertIn('reference_wrong_type',self.errors())
 def test_authority_wrong_type_community(self):
  self.d6['authority'][0]['value']['community_id']='synthetic:source';self.assertIn('reference_wrong_type',self.errors())
 def test_missing_community_id(self):
  del self.d6['claims'][0]['value']['community_id'];self.assertIn('required_field_missing',self.errors())
 def test_required_fk_placeholders_are_not_silently_accepted(self):
  for table,field in [('claims','source_locator_id'),('rights','edition_id'),('relationships','subject_id')]:
   self.setUp();self.d6[table][0]['value'][field]='pending';self.assertIn('required_reference_pending',self.errors())
 def test_unknown_optional_foreign_key(self):
  self.d6['authority'][0]['value']['locator_id']='synthetic:missing';self.assertIn('reference_unresolved',self.errors())
 def test_wrong_kind_locator(self):
  self.d6['claims'][0]['value']['source_locator_id']='synthetic:source';self.assertIn('reference_wrong_type',self.errors())
 def test_evidence_source_mismatch(self):
  self.d6['evidence'][0]['value']['locator_id']='synthetic:locator2';self.assertIn('evidence_claim_locator_mismatch',self.errors())
 def test_missing_passage(self):
  self.d6['claims'][0]['value']['passage_ids']=['synthetic:missing'];self.assertIn('reference_unresolved',self.errors())
 def test_malformed_foreign_key_array(self):
  self.d6['claims'][0]['value']['passage_ids']='synthetic:passage';self.assertIn('reference_array_invalid',self.errors())
 def test_unsupported_official_claim(self):
  self.d6['claims'][0]['value']['attribution_kind']='official_doctrine';self.assertIn('unsupported_official_doctrine',self.errors())
 def test_self_explanation_stays_self_explanation(self):
  c=self.d6['claims'][0]['value'];self.assertFalse(self.errors());self.assertEqual(c['attribution_kind'],'community_self_explanation')
 def test_human_review_requires_independent_validation(self):
  self.d6['claims'][0]['value']['scholarly_reviewed']=True;self.assertIn('unverified_human_review_claim',self.errors())
 def test_nine_rights_each_once(self):
  self.d6['rights'].pop();self.assertIn('rights_matrix_incomplete',self.errors())
 def test_duplicate_action(self):
  self.d6['rights'][0]['value']['action']=self.d6['rights'][1]['value']['action'];self.assertIn('rights_matrix_incomplete',self.errors())
 def test_conditional_is_not_unconditional_permission(self):
  self.d6['rights'][0]['value']['decision']='conditional';self.assertIn('permission_evidence_missing',self.errors())
 def test_unknown_uppercase_is_preserved(self):
  x=self.d6['rights'][0]['value'];x['decision']='UNKNOWN';x['original_decision']='UNKNOWN';self.assertFalse(self.errors());self.assertEqual(x['decision'],'UNKNOWN')
 def test_direct_rebuttal_needs_explicit_proof(self):
  x=self.d6['relationships'][0]['value'];x.update(predicate='directly_rebuts',status='source_checked',object_id='synthetic:claim');self.assertIn('unsupported_direct_rebuttal',self.errors())
 def test_reversed_assessment_relationship(self):
  x=self.d6['relationships'][0]['value'];x['subject_id'],x['object_id']=x['object_id'],x['subject_id'];self.assertIn('relation_direction_or_type_mismatch',self.errors())
 def test_ongoing_not_final(self):
  self.d6['assessments'][0]['value'].update(decision_status='ongoing',final_decision=True);self.assertIn('investigation_misrepresented_final',self.errors())
 def test_final_requires_evidence(self):
  self.d6['assessments'][0]['value']['decision_status']='final';self.assertIn('unsupported_final_decision',self.errors())
 def test_raw_text_field_disallowed(self):
  self.d6['sources'][0]['value']['full_text']='synthetic';self.assertIn('prohibited_content_field',self.errors())
 def test_input_objects_not_mutated(self):
  saved=copy.deepcopy((self.base,self.d5,self.d6));self.errors();self.assertEqual(saved,(self.base,self.d5,self.d6))
 def test_reject_wrong_pinned_zip(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'synthetic.zip';p.write_bytes(b'synthetic');result=m.inspect_archive(p)
   self.assertEqual(result['status'],'fail');self.assertIn('d6_sha_mismatch',result['errors']);self.assertFalse(result['database_write'])
 def test_safe_zip_rejects_traversal(self):
  b=io.BytesIO()
  with zipfile.ZipFile(b,'w') as z:z.writestr('../outside','synthetic')
  e=collections.Counter();self.assertIsNone(m._safe_archive(b.getvalue(),e));self.assertIn('unsafe_or_corrupt_archive',e)
 def test_manifest_missing_extra_or_mutation_fails(self):
  b=io.BytesIO()
  with zipfile.ZipFile(b,'w') as z:z.writestr('x','synthetic');z.writestr('SHA256SUMS.txt','0'*64+'  x\n')
  e=collections.Counter()
  with zipfile.ZipFile(io.BytesIO(b.getvalue())) as z:m._manifest(z,'SHA256SUMS.txt',e)
  self.assertIn('manifest_hash_mismatch',e)
 def test_nested_json_manifest_checks_content_and_complete_list(self):
  b=io.BytesIO();data=b'synthetic'; good={'path':'file','bytes':len(data),'sha256':m._sha(data)}
  for entry in (dict(good,bytes=1),dict(good,sha256='0'*64)):
   b=io.BytesIO()
   with zipfile.ZipFile(b,'w') as z:z.writestr('file',data);z.writestr('RUN_MANIFEST.json',json.dumps({'file_hashes':[entry]}))
   e=collections.Counter()
   with zipfile.ZipFile(io.BytesIO(b.getvalue())) as z:m._json_manifest(z,e)
   self.assertIn('json_manifest_hash_or_size_mismatch',e)
  b=io.BytesIO()
  with zipfile.ZipFile(b,'w') as z:z.writestr('file',data);z.writestr('RUN_MANIFEST.json',json.dumps({'file_hashes':[]}))
  e=collections.Counter()
  with zipfile.ZipFile(io.BytesIO(b.getvalue())) as z:m._json_manifest(z,e)
  self.assertIn('json_manifest_coverage_mismatch',e)
 def test_nested_baseline_tampering_detected(self):
  a=io.BytesIO();b=io.BytesIO()
  with zipfile.ZipFile(a,'w') as z:z.writestr('records.jsonl','synthetic one')
  with zipfile.ZipFile(b,'w') as z:z.writestr('records.jsonl','synthetic two')
  e=collections.Counter()
  with zipfile.ZipFile(io.BytesIO(a.getvalue())) as left,zipfile.ZipFile(io.BytesIO(b.getvalue())) as right:
   m._same_member(left,'records.jsonl',right,'records.jsonl',e,'baseline_changed')
  self.assertIn('baseline_changed',e)
 def test_oversized_archive_is_bounded(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'large';p.touch()
   with p.open('r+b') as f:f.truncate(64*1024*1024+1)
   self.assertEqual(m.inspect_archive(p)['status'],'fail')
 def test_duplicate_json_keys_are_rejected(self):
  with self.assertRaises(ValueError):m._strict_json('{"id":1,"id":2}')
 def test_cli_never_overwrites_output(self):
  with tempfile.TemporaryDirectory() as t:
   path=Path(t)/'input';path.write_bytes(b'synthetic');out=Path(t)/'report';out.write_text('preserve')
   p=subprocess.run([sys.executable,str(ROOT/'scripts/i3_d6_dryrun.py'),'validate',str(path),'--output',str(out)],capture_output=True,text=True)
   self.assertEqual(p.returncode,2);self.assertEqual(out.read_text(),'preserve');self.assertEqual(path.read_bytes(),b'synthetic')

if __name__=='__main__':unittest.main()
