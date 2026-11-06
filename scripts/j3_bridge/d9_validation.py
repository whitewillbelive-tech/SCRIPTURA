"""D9 structure checks in memory. Error codes never include source values."""
from collections import Counter
from j2_bridge import d8_validation as p

TABLE_COUNTS={'assessments':3,'audit_reviews':23,'authority':6,'authority_scope':13,'claims':6,
 'communities':0,'editions':15,'evidence':9,'institutional_assertions':1,'locators':24,
 'passages':9,'relationships':4,'research_gaps':9,'review_queue':30,'rights':135,
 'rights_actions':162,'sample_manifest':1,'source_access_events':26,'sources':14}
TYPED={
 ('assessments','locator_id'):{'locators'},('assessments','target_community_id'):{'communities','authority_registry_traditions'},
 ('audit_reviews','baseline_record_id'):{'claims','assessments','institutional_assertions'},('audit_reviews','locator_id'):{'locators'},
 ('authority','community_id'):{'communities','authority_registry_traditions'},('authority','source_locator_id'):{'locators'},('authority','source_locator_ids'):{'locators'},
 ('authority_scope','community_id'):{'communities','authority_registry_traditions'},('authority_scope','edition_id'):{'editions'},('authority_scope','source_id'):{'sources'},
 ('claims','community_id'):{'communities','authority_registry_traditions'},('claims','passage_ids'):{'passages'},('claims','source_locator_id'):{'locators'},
 ('editions','source_id'):{'sources'},('locators','edition_id'):{'editions'},('evidence','claim_id'):{'claims'},('evidence','locator_id'):{'locators'},
 ('institutional_assertions','community_id'):{'communities','authority_registry_traditions'},('institutional_assertions','locator_id'):{'locators'},
 ('relationships','subject_id'):{'claims','assessments','sources'},('relationships','object_id'):{'claims','assessments','sources','communities','authority_registry_traditions'},
 ('rights','edition_id'):{'editions'},('rights','evidence_locator_id'):{'locators'},('rights_actions','edition_id'):{'editions'},('rights_actions','source_right_id'):{'rights','rights_overrides'},
 ('sample_manifest','source_id'):{'sources'},('sample_manifest','edition_id'):{'editions'},('sample_manifest','locator_id'):{'locators'},
 ('review_queue','baseline_target_id'):{'claims','assessments','unresolved_gaps'},('research_gaps','baseline_target_id'):{'unresolved_gaps'},('research_gaps','source_queue_id'):{'review_queue'},
 ('source_access_events','source_locator_id'):{'locators'},}
MANDATORY={('claims','source_locator_id'),('editions','source_id'),('locators','edition_id'),('evidence','claim_id'),('evidence','locator_id'),('rights','edition_id'),('rights_actions','source_right_id'),('rights_actions','edition_id'),('audit_reviews','baseline_record_id'),('review_queue','baseline_target_id')}
RELATIONS={'same_community_similar_interpretation':({'claims'},{'claims'}),'published_review_criticizes_book_treatment':({'claims'},{'sources'}),'bibliographic_record_describes':({'sources'},{'sources'})}
GROUPS={'bibliography','own_summary','short_quote','full_text','private_link'}
DECISIONS={'unknown','unmapped','metadata_candidate','candidate_visible_local'}
REQUIRED={
 'sources':('id','title','creator','url','kind'), 'editions':('id','source_id','label'),
 'locators':('id','edition_id','location','verification_status'), 'passages':('id','corpus','reference_scheme','reference'),
 'claims':('id','community_id','source_locator_id','passage_ids','attribution_kind','verification_status'),
 'evidence':('id','claim_id','locator_id','status'), 'relationships':('id','subject_id','object_id','predicate','status'),
 'rights':('id','edition_id','action','decision','evidence_locator_id'),
 'rights_actions':('id','edition_id','source_right_id','action','decision','source_origin'),
 'audit_reviews':('id','baseline_record_id','observation_status'),
 'review_queue':('id','baseline_target_id','target_kind','result_status'),
 'research_gaps':('id','baseline_target_id','source_queue_id','status'), 'sample_manifest':('id','source_id','edition_id','locator_id')}

def validate_d9(d9, prior, eligibility, *, auxiliary=None, baseline_targets=None, expected_counts=True):
 """Validate declared cross references, rights observations and visibility matrix.

 No input mutation, canonical promotion, content truth, or legal approval.
 """
 errors=Counter();known={};values={}
 for layer,tables in list(prior.items())+[('d9',d9)]:
  for table,rows in tables.items():
   for item in rows:
    x=item.get('value'); ident=x.get('id') if isinstance(x,dict) else None
    if ident is None and layer=='d5' and table=='audit_conflicts':continue
    if not isinstance(ident,str) or not ident.strip():errors['invalid_id']+=1;continue
    if ident in known:errors['duplicate_id']+=1;continue
    known[ident]=(layer,table);values[ident]=x
 for item in prior.get('d5',{}).get('authority_registries',[]):
  ident=item['value'].get('tradition_id')
  if isinstance(ident,str) and ident:
   if ident in known:errors['duplicate_tradition_alias']+=1
   else:known[ident]=('d5','authority_registry_traditions')
 if expected_counts:
  for t,n in TABLE_COUNTS.items():
   if len(d9.get(t,[]))!=n:errors['d9_record_count_mismatch']+=1
   if t not in d9:errors['d9_record_file_missing']+=1
 def typeref(table,field,ref):
  if ref in p.MISSING:
   if (table,field) in MANDATORY:errors['required_reference_missing']+=1
   return
  if not isinstance(ref,str) or ref not in known:errors['unresolved_reference']+=1;return
  allowed=TYPED.get((table,field))
  if allowed is None and ('locator_id' in field or field.endswith('locator_ids')):allowed={'locators'}
  if allowed and known[ref][1] not in allowed:errors['reference_wrong_type']+=1
 for table,rows in d9.items():
  for item in rows:
   x=item['value']
   for key in REQUIRED.get(table,('id',)):
    if key not in x:errors['required_field_missing']+=1
   if p.FORBIDDEN.intersection(x):errors['prohibited_content_field']+=1
   if x.get('independent_human_review') is True or x.get('scholarly_reviewed') is True:errors['unsupported_human_review']+=1
   if x.get('formal_adoption') is True or x.get('authority_status')=='adoption_documented':errors['unreviewed_formal_adoption']+=1
   for f,v in x.items():
    if f=='id' or not f.endswith(('_id','_ids')):continue
    if f.endswith('_ids') and not isinstance(v,list):errors['invalid_reference_array']+=1;continue
    for ref in v if isinstance(v,list) else [v]:typeref(table,f,ref)
   if table=='claims':
    if x.get('attribution_kind') not in p.ALLOWED_ATTRIBUTIONS:errors['invalid_attribution']+=1
    if x.get('attribution_kind')=='official_doctrine':errors['official_claim_requires_manual_review']+=1
    if not isinstance(x.get('passage_ids'),list):errors['invalid_passage_references']+=1
   if table=='relationships':
    predicate=x.get('predicate');subject=known.get(x.get('subject_id'));obj=known.get(x.get('object_id'))
    if predicate in RELATIONS:
     a,b=RELATIONS[predicate]
     if (subject and subject[1] not in a) or (obj and obj[1] not in b):errors['relation_direction_or_type_mismatch']+=1
    if predicate in ('directly_rebuts','rebuts') and x.get('status') in ('source_checked','verified') and not x.get('direct_relation_evidence'):errors['direct_rebuttal_evidence_missing']+=1
   if table=='evidence':
    claim=values.get(x.get('claim_id'));info=known.get(x.get('claim_id'))
    if claim and info and info[0]=='d9' and claim.get('source_locator_id')!=x.get('locator_id'):errors['evidence_claim_locator_mismatch']+=1
   if table=='review_queue':
    target=values.get(x.get('baseline_target_id'));info=known.get(x.get('baseline_target_id'))
    if target and info:
     previous=target.get('status') if info[1]=='unresolved_gaps' else target.get('verification_status')
     if x.get('prior_status')!=previous:errors['queue_previous_status_changed']+=1
   if table=='rights':
    decision=str(x.get('decision','')).lower()
    if decision not in ('unknown','conditional','allowed','prohibited'):errors['invalid_rights_decision']+=1
    if x.get('action') not in p.ACTIONS:errors['invalid_rights_action']+=1
    if decision in ('conditional','allowed') and (x.get('evidence_locator_id') in p.MISSING or not x.get('action_specific_basis')):errors['rights_evidence_missing']+=1
   if table=='rights_actions':
    source=values.get(x.get('source_right_id'));info=known.get(x.get('source_right_id'))
    if not source or not info: continue
    if info[1]=='rights':
     if x.get('source_origin')!='D9_new_right':errors['rights_observation_origin_mismatch']+=1
     if (x.get('edition_id'),x.get('action'),x.get('decision'))!=(source.get('edition_id'),source.get('action'),source.get('decision')):errors['rights_observation_mismatch']+=1
    elif info[1]=='rights_overrides':
     if x.get('source_origin')!='D8_unchanged_override':errors['rights_observation_origin_mismatch']+=1
     if (x.get('edition_id'),x.get('action'),x.get('decision'))!=(source.get('baseline_edition_id'),source.get('action'),source.get('new_decision')):errors['rights_observation_mismatch']+=1
   if table=='audit_reviews':
    ref=x.get('baseline_record_id');target=values.get(ref);info=known.get(ref)
    if target and info:
     if info[0] not in ('d7','d8'):errors['audit_target_invalid']+=1
     previous=x.get('previous_verification_status');a=target.get('source_verification');b=target.get('verification_status')
     if a is not None and b is not None and a!=b:errors['audit_prior_conflict']+=1
     elif previous!=(a if a is not None else b):errors['audit_previous_status_changed']+=1
 if expected_counts:
  expected_right_ids=Counter(x['value'].get('id') for x in d9.get('rights',[])+prior.get('d8',{}).get('rights_overrides',[]))
  actual_right_ids=Counter(x['value'].get('source_right_id') for x in d9.get('rights_actions',[]))
  if actual_right_ids!=expected_right_ids:errors['rights_observation_coverage_mismatch']+=1
 pairs=Counter((r['value'].get('edition_id'),r['value'].get('action')) for r in d9.get('rights',[]))
 for x in d9.get('editions',[]):
  for a in p.ACTIONS:
   if pairs[(x['value'].get('id'),a)]!=1:errors['rights_matrix_incomplete']+=1
 vis=Counter(); combinations=Counter(); eligibility_ids=set()
 for item in eligibility:
  x=item['value'];entity=x.get('entity_id');kind=x.get('entity_kind');group=x.get('field_group');decision=x.get('decision')
  ident=x.get('id')
  if not isinstance(ident,str) or not ident or ident in eligibility_ids or ident in known:errors['eligibility_id_invalid']+=1
  else:eligibility_ids.add(ident)
  info=known.get(entity)
  if not info or info[1] not in {'sources','editions','locators','claims'} or info[1].rstrip('s')!=kind:errors['eligibility_entity_invalid']+=1
  if group not in GROUPS or decision not in DECISIONS:errors['eligibility_value_invalid']+=1
  if decision=='candidate_visible_local':errors['unexpected_actual_visibility_approval']+=1
  combinations[(entity,group)]+=1
  if decision in DECISIONS:vis[decision]+=1
 if expected_counts:
  if len(eligibility)!=1270 or len({e['value'].get('entity_id') for e in eligibility})!=254:errors['eligibility_count_mismatch']+=1
  for entity,_ in list(combinations):
   if any(combinations[(entity,g)]!=1 for g in GROUPS):errors['eligibility_matrix_incomplete']+=1
 if auxiliary is not None:
  expected=Counter(x['value'].get('id') for x in d9.get('sources',[]))
  for table in ('SOURCE_ACCESS_INDEX','SOURCE_DUPLICATE_REVIEW'):
   actual=Counter(x['value'].get('source_id') for x in auxiliary.get(table,[]))
   if actual!=expected:errors['source_report_coverage_mismatch']+=1
  for item in auxiliary.get('SOURCE_ACCESS_INDEX',[]):
   x=item['value'];source=x.get('source_id')
   for field,kind in (('edition_ids','editions'),('locator_ids','locators'),('access_event_ids','source_access_events')):
    seq=x.get(field)
    if not isinstance(seq,list):errors['source_report_reference_array_invalid']+=1;continue
    for ident in seq:
     info=known.get(ident); obj=values.get(ident)
     if not info or not obj or info[1]!=kind:errors['source_report_reference_invalid']+=1;continue
     if kind=='editions':edition=obj
     elif kind=='locators':edition=values.get(obj.get('edition_id'))
     else:
      locator=values.get(obj.get('source_locator_id'));edition=values.get(locator.get('edition_id')) if locator else None
     if not edition or edition.get('source_id')!=source:errors['source_report_source_mismatch']+=1
 if baseline_targets is not None:
  actual=Counter(x['value'].get('baseline_target_id') for x in d9.get('review_queue',[]))
  expected=Counter(x['value'].get('baseline_target_id') for x in baseline_targets)
  if actual!=expected:errors['queue_target_coverage_mismatch']+=1
  if expected_counts and (len(baseline_targets)!=30 or any(v!=1 for v in expected.values())):errors['baseline_target_count_mismatch']+=1
 return errors,{'visibility':dict(sorted(vis.items())), 'eligibility_total':len(eligibility),
  'counts':{k:len(v) for k,v in d9.items()},'unmapped_relation_predicates':sum(x['value'].get('predicate') not in RELATIONS for x in d9.get('relationships',[]))}
