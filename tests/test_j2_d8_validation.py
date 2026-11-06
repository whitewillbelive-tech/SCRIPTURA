"""Synthetic-only structural tests: never open research archives."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from j2_bridge.d8_validation import validate_d8, ACTIONS

def item(x):return {'value':x,'line':1}
def fixture():
 prior={'base':{},'d5':{'authority_registries':[item({'id':'syn:reg','tradition_id':'syn:trad'})]},'d6':{},
        'd7':{'claims':[item({'id':'syn:old','verification_status':'source_checked','source_locator_id':'syn:oldloc'})],
              'locators':[item({'id':'syn:oldloc'})],
              'editions':[item({'id':'syn:oldedition'})],
              'rights':[item({'id':'syn:oldright','edition_id':'syn:oldedition','action':'browse','decision':'unknown'})]}}
 d8={'sources':[item({'id':'syn:source'})],
     'editions':[item({'id':'syn:edition','source_id':'syn:source'})],
     'locators':[item({'id':'syn:locator','edition_id':'syn:edition'})],
     'passages':[item({'id':'syn:passage'})],
     'claims':[item({'id':'syn:claim','community_id':'syn:trad','source_locator_id':'syn:locator','passage_ids':['syn:passage'],'attribution_kind':'individual_opinion'})],
     'evidence':[item({'id':'syn:evidence','claim_id':'syn:claim','locator_id':'syn:locator'})],
     'rights':[item({'id':'syn:right:'+a,'edition_id':'syn:edition','action':a,'decision':'unknown','evidence_locator_id':None}) for a in ACTIONS],
     'rights_overrides':[item({'id':'syn:override','baseline_right_id':'syn:oldright','baseline_edition_id':'syn:oldedition','action':'browse','previous_decision':'unknown','new_decision':'unknown','evidence_locator_id':'syn:oldloc','additional_evidence_locator_ids':[],'original_baseline_mutated':False})],
     'audit_reviews':[item({'id':'syn:audit','baseline_record_id':'syn:old','previous_verification_status':'source_checked','locator_id':'syn:oldloc','observation_status':'direct_recheck'})]}
 return d8,prior

class Validation(unittest.TestCase):
 def setUp(self):self.d,self.p=fixture()
 def errors(self):return validate_d8(self.d,self.p,expected_counts=False)[0]
 def test_valid(self):self.assertFalse(self.errors())
 def test_not_mutated(self):
  before=copy.deepcopy((self.d,self.p));self.errors();self.assertEqual(before,(self.d,self.p))
 def test_duplicate_id(self):
  self.d['sources'][0]['value']['id']='syn:edition';self.assertIn('duplicate_id',self.errors())
 def test_broken_edition(self):
  self.d['editions'][0]['value']['source_id']='syn:missing';self.assertIn('unresolved_reference',self.errors())
 def test_wrong_locator_type(self):
  self.d['claims'][0]['value']['source_locator_id']='syn:source';self.assertIn('reference_wrong_type',self.errors())
 def test_wrong_community_type(self):
  self.d['claims'][0]['value']['community_id']='syn:source';self.assertIn('reference_wrong_type',self.errors())
 def test_missing_community_is_not_invented(self):
  self.d['claims'][0]['value']['community_id']=None;self.assertFalse(self.errors())
 def test_claim_can_lack_passage_when_unmapped(self):
  self.d['claims'][0]['value']['passage_ids']=[];e,m=validate_d8(self.d,self.p,expected_counts=False);self.assertFalse(e);self.assertEqual(m['claims_without_passage'],1)
 def test_evidence_mismatch(self):
  self.d['evidence'][0]['value']['locator_id']='syn:oldloc';self.assertIn('evidence_claim_locator_mismatch',self.errors())
 def test_missing_rights_action(self):
  self.d['rights'].pop();self.assertIn('rights_matrix_incomplete',self.errors())
 def test_conditional_evidence_required(self):
  self.d['rights'][0]['value']['decision']='conditional';self.assertIn('rights_evidence_missing',self.errors())
 def test_unknown_decision_is_not_upgraded(self):
  self.errors();self.assertEqual(self.d['rights'][0]['value']['decision'],'unknown')
 def test_override_cannot_change_baseline_action(self):
  self.d['rights_overrides'][0]['value']['action']='embed';self.assertIn('rights_override_baseline_mismatch',self.errors())
 def test_override_cannot_mark_baseline_mutated(self):
  self.d['rights_overrides'][0]['value']['original_baseline_mutated']=True;self.assertIn('baseline_mutation_flag',self.errors())
 def test_override_conditional_without_scope_is_pending(self):
  self.d['rights_overrides'][0]['value']['new_decision']='conditional'
  e,m=validate_d8(self.d,self.p,expected_counts=False);self.assertFalse(e);self.assertEqual(m['rights_overrides_pending_scope'],1)
 def test_override_decision_must_be_known(self):
  self.d['rights_overrides'][0]['value']['new_decision']='invented';self.assertIn('invalid_rights_decision',self.errors())
 def test_audit_previous_must_match(self):
  self.d['audit_reviews'][0]['value']['previous_verification_status']='scholarly_reviewed';self.assertIn('audit_previous_status_changed',self.errors())
 def test_crosswalk_complete_events(self):
  aux={'D7_D8_REVIEW_CROSSWALK':[item({'baseline_id':'syn:old','d8_review_event_ids':[],'d8_observation_statuses':[],'d8_review_state':'not_reviewed_this_gate'})],
       'SOURCE_ACCESS_INDEX':[item({'source_id':'syn:source'})], 'SOURCE_DUPLICATE_REVIEW':[item({'source_id':'syn:source'})]}
  e,_=validate_d8(self.d,self.p,aux,expected_counts=False);self.assertIn('crosswalk_events_mismatch',e)
 def test_source_index_cannot_replace_source_with_duplicate(self):
  self.d['sources'].append(item({'id':'syn:source2'}))
  aux={'D7_D8_REVIEW_CROSSWALK':[item({'baseline_id':'syn:old','baseline_table':'claims','baseline_locator_id':'syn:oldloc','d8_review_event_ids':['syn:audit'],'d8_observation_statuses':['direct_recheck'],'d8_review_state':'reviewed_this_gate'})],
       'SOURCE_ACCESS_INDEX':[item({'source_id':'syn:source','edition_ids':[],'locator_ids':[],'access_event_ids':[]}),item({'source_id':'syn:source','edition_ids':[],'locator_ids':[],'access_event_ids':[]})],
       'SOURCE_DUPLICATE_REVIEW':[item({'source_id':'syn:source'}),item({'source_id':'syn:source2'})]}
  e,_=validate_d8(self.d,self.p,aux,expected_counts=False);self.assertIn('source_report_coverage_mismatch',e)
 def test_source_index_chain_does_not_cross_sources(self):
  self.d['sources'].append(item({'id':'syn:source2'}))
  aux={'D7_D8_REVIEW_CROSSWALK':[item({'baseline_id':'syn:old','baseline_table':'claims','baseline_locator_id':'syn:oldloc','d8_review_event_ids':['syn:audit'],'d8_observation_statuses':['direct_recheck'],'d8_review_state':'reviewed_this_gate'})],
       'SOURCE_ACCESS_INDEX':[item({'source_id':'syn:source','edition_ids':[],'locator_ids':[],'access_event_ids':[]}),item({'source_id':'syn:source2','edition_ids':['syn:edition'],'locator_ids':[],'access_event_ids':[]})],
       'SOURCE_DUPLICATE_REVIEW':[item({'source_id':'syn:source'}),item({'source_id':'syn:source2'})]}
  e,_=validate_d8(self.d,self.p,aux,expected_counts=False);self.assertIn('source_report_source_mismatch',e)
 def test_official_not_automatically_accepted(self):
  self.d['claims'][0]['value']['attribution_kind']='official_doctrine';self.assertIn('official_claim_requires_manual_review',self.errors())
 def test_independent_review_not_inferred(self):
  self.d['claims'][0]['value']['scholarly_reviewed']=True;self.assertIn('unsupported_human_review',self.errors())
 def test_raw_content_field_rejected(self):
  self.d['sources'][0]['value']['full_text']='synthetic';self.assertIn('prohibited_content_field',self.errors())
 def test_unverified_direct_rebuttal_rejected(self):
  self.d['relationships']=[item({'id':'syn:relation','subject_id':'syn:claim','object_id':'syn:old','locator_id':'syn:locator','predicate':'directly_rebuts','status':'source_checked'})];self.assertIn('direct_rebuttal_evidence_missing',self.errors())
 def test_reversed_relationship_type_rejected(self):
  self.d['relationships']=[item({'id':'syn:relation','subject_id':'syn:source','object_id':'syn:claim','locator_id':'syn:locator','predicate':'contrasting_interpretation_on_shared_text','status':'pending'})];self.assertIn('relation_direction_or_type_mismatch',self.errors())
 def test_unknown_relation_is_pending(self):
  self.d['relationships']=[item({'id':'syn:relation','subject_id':'syn:claim','object_id':'syn:old','locator_id':'syn:locator','predicate':'novel_relation','status':'pending'})];e,m=validate_d8(self.d,self.p,expected_counts=False);self.assertFalse(e);self.assertEqual(m['unmapped_relation_predicates'],1)

if __name__=='__main__':unittest.main()
