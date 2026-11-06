"""Synthetic security tests for J-2 in-memory projections."""
import io
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from j2_bridge import candidate_readonly as m
from j1_bridge import d7 as j1


def entry(row,value):return {'line':row,'value':value,'sha256':'a'*64}

def layers_fixture():
 layers={k:{} for k in ('base','d5','d6','d7','d8')}
 layers['d6']['communities']=[entry(1,{'id':'synthetic:community','canonical_name':'Community X'})]
 layers['d7']['sources']=[entry(1,{'id':'synthetic:oldsource','title':'old unreviewed title','creator':'old unreviewed creator','kind':'article'})]
 layers['d7']['editions']=[entry(1,{'id':'synthetic:oldedition','source_id':'synthetic:oldsource'})]
 layers['d7']['locators']=[entry(1,{'id':'synthetic:oldlocator','edition_id':'synthetic:oldedition','location':'quoted secret fragment'})]
 layers['d7']['claims']=[entry(1,{'id':'synthetic:oldclaim','source_locator_id':'synthetic:oldlocator','community_id':'synthetic:community','attribution_kind':'external_critique','statement_ko':'SECRET_FORBIDDEN_CONTENT','passage_ids':[]})]
 layers['d8']['sources']=[entry(1,{'id':'synthetic:source','title':'Bibliography title','creator':'Researcher A','kind':'article'})]
 layers['d8']['editions']=[entry(1,{'id':'synthetic:edition','source_id':'synthetic:source'})]
 layers['d8']['locators']=[entry(1,{'id':'synthetic:locator','edition_id':'synthetic:edition','location':'p. 12','verification_status':'source_checked'})]
 layers['d8']['passages']=[entry(1,{'id':'synthetic:passage','corpus':'Bible','reference_scheme':'generic chapter and verse; edition alignment not verified','reference':'John 1:1'})]
 layers['d8']['claims']=[entry(1,{'id':'synthetic:claim','source_locator_id':'synthetic:locator','community_id':'synthetic:community','attribution_kind':'external_critique','verification_status':'source_checked','passage_ids':['synthetic:passage'],'statement_ko':'SECRET_FORBIDDEN_CONTENT'})]
 layers['d8']['rights']=[entry(1,{'id':'synthetic:right','edition_id':'synthetic:edition','action':'browse','decision':'unknown'})]
 return layers

class CandidateProjectionTests(unittest.TestCase):
 def test_source_aliases_obey_same_field_gate(self):
  records=m._build_projection(layers_fixture()); old=next(r for r in records if r['key']=='d7:claims:1'); source=next(r for r in records if r['key']=='d7:sources:1')
  for r in (old,source):
   self.assertIsNone(r['source_creator']);self.assertIsNone(r['researcher']);self.assertIsNone(r['source_title'])
  self.assertNotIn('old unreviewed creator',str(records))
 def test_no_claim_body_or_locator_excerpt(self):
  records=m._build_projection(layers_fixture())
  self.assertNotIn('SECRET_FORBIDDEN_CONTENT',str(records));self.assertNotIn('quoted secret fragment',str(records))
  self.assertIn('statement_ko',next(r for r in records if r['key']=='d8:claims:1')['unmapped'])
 def test_claim_source_chain_uses_coordinates_only(self):
  records=m._build_projection(layers_fixture());r=next(r for r in records if r['key']=='d8:claims:1')
  self.assertEqual(r['source_key'],'d8:sources:1');self.assertEqual(r['edition_key'],'d8:editions:1');self.assertEqual(r['locator_key'],'d8:locators:1')
  self.assertIn(r['source_key'],[x['key'] for x in records if x['record_kind']=='source'])
  self.assertNotIn('synthetic:source',str(records));self.assertNotIn('synthetic:edition',str(records));self.assertNotIn('synthetic:locator',str(records))
 def test_unresolvable_source_chain_never_exposes_ids(self):
  layers=layers_fixture();layers['d8']['claims'][0]['value']['source_locator_id']='synthetic:missing'
  r=next(r for r in m._build_projection(layers) if r['key']=='d8:claims:1')
  self.assertIsNone(r['source_key']);self.assertIsNone(r['edition_key']);self.assertIsNone(r['locator_key'])
  self.assertIn('source_chain',r['unmapped']);self.assertNotIn('synthetic:missing',str(r))
 def test_d8_metadata_coordinate_and_format_gate(self):
  layers=layers_fixture();source=layers['d8']['sources'][0];source['line']=16
  self.assertIsNone(next(r for r in m._build_projection(layers) if r['key']=='d8:claims:1')['source_title'])
  source['line']=17
  r=next(r for r in m._build_projection(layers) if r['key']=='d8:claims:1')
  self.assertIsNone(r['source_creator']);self.assertIsNone(r['researcher'])
  source['line']=1;source['value']['title']='"UNREVIEWED QUOTATION"'
  self.assertIsNone(next(r for r in m._build_projection(layers) if r['key']=='d8:claims:1')['source_title'])
  source['value']['creator']='person@example.invalid'
  self.assertIsNone(next(r for r in m._build_projection(layers) if r['key']=='d8:claims:1')['researcher'])
 def test_all_name_fields_redacted_and_recorded_as_unmapped(self):
  layers=layers_fixture();claim=layers['d8']['claims'][0]['value'];claim['speaker']='SPEAKER_SECRET_NAME'
  layers['d8']['sources'][0]['value'].update(title='TITLE_SECRET_NAME',creator='CREATOR_SECRET_NAME')
  layers['d6']['communities'][0]['value']['canonical_name']='COMMUNITY_SECRET_NAME'
  records=m._build_projection(layers);record=next(r for r in records if r['key']=='d8:claims:1')
  for key in ('source_title','source_creator','researcher','speaker','tradition','community_reference','evaluated_subject'):
   self.assertIsNone(record[key],key)
  self.assertTrue({'speaker','community_id','source_title','source_creator'} <= set(record['unmapped']))
  for secret in ('SPEAKER_SECRET_NAME','TITLE_SECRET_NAME','CREATOR_SECRET_NAME','COMMUNITY_SECRET_NAME'):
   self.assertNotIn(secret,str(records))
  source=next(r for r in records if r['key']=='d8:sources:1')
  self.assertTrue({'title','creator'} <= set(source['unmapped']))
  self.assertEqual(source['field_policy']['source_metadata'],'redacted_rights_unresolved')
 def test_community_role_is_never_guessed_from_critique(self):
  layers=layers_fixture();r=next(r for r in m._build_projection(layers) if r['key']=='d8:claims:1')
  self.assertEqual(r['community_role'],'unspecified');self.assertIsNone(r['tradition']);self.assertIsNone(r['evaluated_subject'])
  layers['d8']['claims'][0]['value']['community_id_role']='비평 대상; 주장 발화 공동체가 아님'
  r=next(r for r in m._build_projection(layers) if r['key']=='d8:claims:1')
  self.assertEqual(r['community_role'],'target');self.assertIsNone(r['evaluated_subject']);self.assertIn('community_id',r['unmapped'])
 def test_reference_requires_safe_address_and_corpus_scheme(self):
  s='generic chapter and verse; edition alignment not verified'
  q='Quran surah:ayah, version and text edition unresolved'
  self.assertEqual(m._reference('John 1:1','Bible',s),'John 1:1')
  self.assertIsNone(m._reference('저작권이 확인되지 않은 원문입니다','Bible',s))
  self.assertIsNone(m._reference('John 1:1','Quran',q))
  self.assertIsNone(m._reference('Quran 3:45','Bible',s))
  self.assertEqual(m._reference('3:45','Quran',q),'3:45')
  self.assertIsNone(m._reference('John 1:1','Bible','unverified_unknown'))
 def test_status_axes_do_not_auto_promote(self):
  layers=layers_fixture();layers['d8']['claims'][0]['value']['attribution_kind']='official_doctrine'
  r=next(r for r in m._build_projection(layers) if r['key']=='d8:claims:1')
  self.assertEqual(r['attribution'],'unconfirmed_authority');self.assertEqual(r['authority_status'],'pending_authority')
  self.assertEqual(r['verification_status'],'source_checked');self.assertEqual(r['independent_review_status'],'pending')
  self.assertTrue(all(v is False for v in r['effective_permissions'].values()))
 def test_rights_override_keeps_base_and_new_as_independent_observations(self):
  layers=layers_fixture();layers['d8']['rights_overrides']=[entry(1,{'id':'synthetic:override','baseline_right_id':'synthetic:right','baseline_edition_id':'synthetic:edition','action':'browse','previous_decision':'unknown','new_decision':'conditional','evidence_locator_id':'synthetic:locator'})]
  r=next(r for r in m._build_projection(layers) if r['key']=='d8:claims:1')
  self.assertEqual(r['rights']['browse'],'unknown');self.assertEqual(r['rights']['store_raw'],'not_recorded')
  self.assertEqual(r['rights_overrides'][0]['new_decision'],'conditional');self.assertFalse(r['effective_permissions']['browse'])
 def test_source_rights_preserve_each_edition_without_merging(self):
  layers=layers_fixture()
  r=next(r for r in m._build_projection(layers) if r['key']=='d8:sources:1')
  self.assertEqual(r['rights']['browse'],'unknown');self.assertEqual(len(r['edition_rights']),1)
  layers['d8']['editions'].append(entry(2,{'id':'synthetic:edition2','source_id':'synthetic:source'}))
  layers['d8']['rights'].append(entry(2,{'id':'synthetic:right2','edition_id':'synthetic:edition2','action':'browse','decision':'conditional'}))
  r=next(r for r in m._build_projection(layers) if r['key']=='d8:sources:1')
  self.assertEqual(r['rights_status'],'multiple_editions');self.assertEqual(r['rights']['browse'],'unmapped')
  self.assertEqual([v['rights']['browse'] for v in r['edition_rights']],['unknown','conditional'])
  self.assertTrue(all(not any(v['effective_permissions'].values()) for v in r['edition_rights']))
 def test_access_event_requires_matching_source_and_edition(self):
  layers=layers_fixture();layers['d8']['source_access_events']=[entry(1,{'id':'synthetic:event','source_locator_id':'synthetic:locator','source_id':'synthetic:source','edition_id':'synthetic:edition','method':'web_open','result':'SECRET_FORBIDDEN_CONTENT','checked_at':'2025-01-01'})]
  r=next(r for r in m._build_projection(layers) if r['key']=='d8:claims:1')
  self.assertEqual(r['access_path'],'web_open');self.assertEqual(len(r['access_events']),1)
  self.assertNotIn('SECRET_FORBIDDEN_CONTENT',str(r['access_events']))
  layers['d8']['source_access_events'][0]['value']['source_id']='synthetic:oldsource'
  r=next(r for r in m._build_projection(layers) if r['key']=='d8:claims:1')
  self.assertEqual(r['access_events'],[]);self.assertEqual(r['access_path'],'unknown')
 def test_locator_rules_disallow_quote_and_urls(self):
  self.assertEqual(m._locator('pp. 4–6'),'pp. 4–6')
  self.assertIsNone(m._locator('p. 4 text that is an excerpt'));self.assertIsNone(m._locator('https://example.invalid/p/4'))
 def test_invalid_calendar_dates_are_not_displayed(self):
  self.assertIsNone(m._date('2024-99-99'));self.assertIsNone(m._date('2023-02-29'))
  self.assertEqual(m._date('2024-02-29T00:00:00Z'),'2024-02-29')
 def test_missing_or_wrong_archive_fails_closed_without_path(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'private-DO-NOT-LOG.zip';path.write_bytes(b'not an archive')
   with self.assertRaises(m.CandidateError) as e:m.load_candidate_archive(path)
   self.assertNotIn(str(path),str(e.exception))
  with self.assertRaises(m.CandidateError):m.load_candidate_archive(b'not an archive')
 def test_network_paths_rejected_before_any_read(self):
  for path in (r'\\\\server\share\file.zip','//server/share/file.zip','https://example.invalid/file.zip','file:///some/file.zip'):
   with patch.object(m.prior,'_bounded_read') as read:
    with self.assertRaises(m.CandidateError) as e:m.load_candidate_archive(path)
    self.assertEqual(str(e.exception),'archive_not_local');read.assert_not_called()
 def test_baseline_j1_bytes_support_preserves_existing_validation(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'input';payload=b'synthetic wrong pin';path.write_bytes(payload)
   self.assertEqual(j1.inspect_archive(path)['errors'],j1.inspect_archive(payload)['errors'])

if __name__=='__main__':unittest.main()
