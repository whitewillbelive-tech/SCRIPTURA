"""Pinned D7 structural receipt: memory-only validation; never an importer.

Coordinates and raw-line hashes are references to sensitive source material,
not anonymisation. No text or record IDs are emitted in public reports.
"""
from __future__ import annotations
import collections
import io
import re
import unicodedata
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from i3_bridge import d6 as prior

D7_SHA='8a8fb8d4efde68f639b99ab8edb9eab14c320b4bc9e64e0aab882af7ee0a4820'
TABLES=('communities','sources','editions','locators','passages','claims','assessments','rights','relationships','authority','evidence','source_access_events','audit_reviews','correction_candidates','research_gaps')
EXPECTED=dict(zip(TABLES,(0,37,37,51,60,42,5,333,8,34,42,39,79,1,2)))
REQUIRED={
 'sources':('id','title','creator','url','kind'), 'editions':('id','source_id','label'),
 'locators':('id','edition_id','location','verification_status'), 'passages':('id','corpus','reference_scheme','reference'),
 'claims':('id','community_id','source_locator_id','passage_ids','statement_ko','attribution_kind','authority_status','verification_status'),
 'assessments':('id','target_community_id','assessor','assessment_date','status_as_of','locator_id'),
 'rights':('id','edition_id','action','decision','evidence_locator_id'),
 'relationships':('id','subject_id','predicate','object_id','locator_id','status'),
 'authority':('id','formal_adoption','source_locator_ids'), 'evidence':('id','claim_id','locator_id'),
 'source_access_events':('id',), 'audit_reviews':('id','baseline_record_id','previous_verification_status','observation_status','access_method','checked_at','locator_id','note'),
 'correction_candidates':('id','baseline_record_id','status'), 'research_gaps':('id','status'),
}
TYPED={
 ('editions','source_id'):{'sources'}, ('locators','edition_id'):{'editions'},
 ('claims','community_id'):{'communities','authority_registry_traditions'},('claims','source_locator_id'):{'locators'},('claims','passage_ids'):{'passages'},
 ('assessments','target_community_id'):{'communities','authority_registry_traditions'},('assessments','locator_id'):{'locators'},
 ('rights','edition_id'):{'editions'},('rights','evidence_locator_id'):{'locators'},
 ('relationships','subject_id'):{'claims','assessments'},('relationships','object_id'):{'claims','assessments','communities','authority_registry_traditions','authority_documents','editions'},('relationships','locator_id'):{'locators'},
 ('authority','community_id'):{'communities','authority_registry_traditions'},('authority','source_locator_ids'):{'locators'},
 ('evidence','claim_id'):{'claims'},('evidence','locator_id'):{'locators'},('source_access_events','source_id'):{'sources'},
 ('source_access_events','locator_id'):{'locators'},('source_access_events','source_locator_id'):{'locators'},
 ('audit_reviews','baseline_record_id'):{'claims','assessments'},('audit_reviews','locator_id'):{'locators'},
 ('correction_candidates','baseline_record_id'):{'communities','claims','assessments'},('research_gaps','source_locator_ids'):{'locators'},
}
REQUIRED_FKS={('editions','source_id'),('locators','edition_id'),('claims','source_locator_id'),('assessments','target_community_id'),('assessments','locator_id'),('rights','edition_id'),('relationships','subject_id'),('relationships','object_id'),('evidence','claim_id'),('evidence','locator_id'),('audit_reviews','baseline_record_id'),('audit_reviews','locator_id'),('correction_candidates','baseline_record_id')}
RELATIONS={
 'later_institutional_report_relevant_to':({'assessments'},{'assessments'}),
 'related_topic':({'claims'},{'claims'}),
 'criticizes_community_position':({'claims','assessments'},{'authority_registry_traditions','communities'}),
 'contrasting_interpretation_on_shared_text':({'claims'},{'claims'}),
 'same_passage_other_research':({'claims'},{'claims'}),
 'interpretive_contrast_candidate':({'claims'},{'claims'}),
}

def _norm_url(value):
 if not isinstance(value,str) or not value.strip():return ''
 try:
  p=urlsplit(value.strip()); host=p.hostname.lower() if p.hostname else ''
  if not host or p.scheme.lower() not in ('http','https'):return ''
  host=host.removeprefix('www.');port=p.port
  net=host+(f':{port}' if port and not ((p.scheme.lower()=='https' and port==443) or (p.scheme.lower()=='http' and port==80)) else '')
  query=urlencode(sorted((k,v) for k,v in parse_qsl(p.query,keep_blank_values=True) if not k.lower().startswith('utm_')))
  return urlunsplit((p.scheme.lower(),net,p.path.rstrip('/') or '/',query,''))
 except ValueError:return ''

def _norm_doi(v):
 if not isinstance(v,str):return ''
 v=v.strip().lower()
 for p in ('https://doi.org/','http://doi.org/','doi:'):
  if v.startswith(p):v=v[len(p):]
 return v.strip()

def validate_records(base,d5,d6,d7,crosswalk):
 """Validate only references/constraints; preserve all source objects unchanged."""
 errors=collections.Counter(); refs=[]; known={}; objects={}
 for layer,tables in [('base',base),('d5',d5),('d6',d6),('d7',d7)]:
  for table,entries in tables.items():
   for item in entries:
    value=item['value']; ident=value.get('id')
    if ident is None and layer=='d5' and table=='audit_conflicts':continue
    if not isinstance(ident,str) or not ident.strip():errors['invalid_id']+=1;continue
    if ident in known:errors['duplicate_id_across_layers']+=1
    else:known[ident]=(layer,table,item['line']);objects[ident]=value
    if layer=='d7':
     for field in REQUIRED.get(table,('id',)):
      if field not in value:errors['required_field_missing']+=1
      elif value[field] in (None,'') and (table,field) not in {('claims','community_id'),('assessments','assessment_date'),('rights','evidence_locator_id'),('audit_reviews','previous_verification_status')}:errors['required_field_empty']+=1
     if prior.FORBIDDEN.intersection(value):errors['prohibited_content_field']+=1
     for field in ('independent_human_review','scholarly_reviewed','raw_text_saved','raw_text_stored','raw_file_stored','original_file_stored'):
      if value.get(field) is True:errors['unverified_review_or_raw_storage']+=1
     if value.get('independent_review_status') in ('human_review_documented','scholarly_reviewed'):errors['unverified_human_review']+=1
     if value.get('authority_status')=='adoption_documented' or value.get('formal_adoption') is True:errors['adoption_requires_manual_review']+=1
 for item in d5.get('authority_registries',[]):
  value=item['value']; ident=value.get('tradition_id')
  if isinstance(ident,str) and ident:
   if ident in known:errors['duplicate_tradition_id']+=1
   else:known[ident]=('d5','authority_registry_traditions',item['line'])
 for table,entries in d7.items():
  for item in entries:
   value=item['value']
   for field,val in value.items():
    if field=='id' or not(field.endswith('_id') or field.endswith('_ids')):continue
    if field.endswith('_ids') and not isinstance(val,list):errors['reference_array_invalid']+=1;continue
    for target in val if isinstance(val,list) else [val]:
     if target in prior.EMPTY:
      if (table,field) in REQUIRED_FKS:errors['required_reference_pending']+=1
      continue
     if not isinstance(target,str) or target not in known:errors['reference_unresolved']+=1;continue
     loc=known[target];allowed=TYPED.get((table,field))
     if allowed and loc[1] not in allowed:errors['reference_wrong_type']+=1
     if (table,field)==('audit_reviews','baseline_record_id') and (loc[0]!='d6' or loc[1] not in ('claims','assessments')):errors['audit_target_not_d6']+=1
     refs.append({'layer':'d7','table':table,'row':item['line'],'field':field,'target_layer':loc[0],'target_table':'authority_registries' if loc[1]=='authority_registry_traditions' else loc[1],'target_row':loc[2],'target_field':'tradition_id' if loc[1]=='authority_registry_traditions' else 'id'})
   if table=='claims':
    if value.get('attribution_kind') not in prior.ATTRIBUTIONS:errors['invalid_attribution']+=1
    if value.get('attribution_kind')=='official_doctrine':errors['official_claim_requires_manual_review']+=1
    if not isinstance(value.get('passage_ids'),list) or not value['passage_ids']:errors['invalid_passage_list']+=1
   if table=='assessments':
    status=str(value.get('decision_status','')).lower()
    if status in ('final','final_decision','finalized') and not value.get('decision_evidence'):errors['unsupported_final_decision']+=1
    if status in ('pending','ongoing','investigation') and value.get('final_decision') is True:errors['ongoing_investigation_misrepresented']+=1
   if table=='rights':
    decision=value.get('decision');decision=decision.lower() if isinstance(decision,str) else ''
    if value.get('action') not in prior.ACTIONS:errors['invalid_rights_action']+=1
    if decision not in ('unknown','conditional','allowed','prohibited'):errors['invalid_rights_decision']+=1
    if decision in ('conditional','allowed') and (value.get('evidence_locator_id') in prior.EMPTY or not value.get('action_specific_basis')):errors['permission_evidence_missing']+=1
   if table=='relationships':
    predicate=value.get('predicate');a=known.get(value.get('subject_id'));b=known.get(value.get('object_id'))
    if predicate in RELATIONS and ((a and a[1] not in RELATIONS[predicate][0]) or (b and b[1] not in RELATIONS[predicate][1])):errors['relation_direction_or_type_mismatch']+=1
    if predicate in ('rebuts','directly_rebuts') and value.get('status') in ('verified','source_checked') and not value.get('direct_relation_evidence'):errors['unsupported_direct_rebuttal']+=1
   if table=='evidence':
    claim=objects.get(value.get('claim_id'))
    if claim and claim.get('source_locator_id')!=value.get('locator_id'):errors['claim_evidence_locator_mismatch']+=1
 # Complete edition/action matrix. Unknown and conditional are not permissions.
 pairs=collections.Counter((x['value'].get('edition_id'),x['value'].get('action')) for x in d7.get('rights',[]))
 for item in d7.get('editions',[]):
  for action in prior.ACTIONS:
   if pairs[(item['value'].get('id'),action)]!=1:errors['rights_matrix_incomplete']+=1
 # Every frozen D6 claim and assessment needs a fresh observation; retain all events.
 targets={x['value']['id']:x['value'] for t in ('claims','assessments') for x in d6.get(t,[])}
 events=collections.defaultdict(list)
 for item in d7.get('audit_reviews',[]):
  x=item['value'];target=x.get('baseline_record_id');orig=targets.get(target)
  if orig is not None:
   a=orig.get('source_verification');b=orig.get('verification_status')
   if a is not None and b is not None and a!=b:errors['baseline_status_fields_conflict']+=1
   original_status=a if a is not None else b
   if x.get('previous_verification_status')!=original_status:errors['audit_previous_status_changed']+=1
   if x.get('baseline_table') and x['baseline_table']!=known[target][1]:errors['audit_target_table_mismatch']+=1
   events[target].append(x.get('id'))
 if set(events)!=set(targets):errors['audit_coverage_incomplete']+=1
 seen=set()
 for item in crosswalk:
  x=item['value'];target=x.get('baseline_id');eventids=x.get('d7_audit_ids')
  if target not in targets or target in seen:errors['crosswalk_target_invalid']+=1;continue
  seen.add(target)
  if not isinstance(eventids,list) or collections.Counter(eventids)!=collections.Counter(events[target]):errors['crosswalk_event_mismatch']+=1
  if x.get('baseline_type') and x['baseline_type']!= {'claims':'claim','assessments':'assessment'}[known[target][1]]:errors['crosswalk_type_mismatch']+=1
  original=targets[target];old=original.get('source_verification') if original.get('source_verification') is not None else original.get('verification_status')
  if x.get('prior_verification_status')!=old:errors['crosswalk_previous_status_changed']+=1
  if x.get('baseline_locator_id')!=original.get('source_locator_id',original.get('locator_id')):errors['crosswalk_locator_mismatch']+=1
  statuses=[objects[v].get('observation_status') for v in events[target] if v in objects]
  if not isinstance(x.get('d7_observation_statuses'),list) or collections.Counter(x['d7_observation_statuses'])!=collections.Counter(statuses):errors['crosswalk_observation_mismatch']+=1
 if seen!=set(targets):errors['crosswalk_coverage_incomplete']+=1
 return errors,refs,known,events

def _duplicates(base,d5,d6,d7):
 """No merging: produce only coordinate candidates, not text or source IDs."""
 seen={}; counts=collections.Counter(); candidates=[]
 for layer,tables in (('base',base),('d5',d5),('d6',d6),('d7',d7)):
  for item in tables.get('sources',[]):
   obj=item['value'];coord={'layer':layer,'table':'sources','row':item['line']}
   title=obj.get('title'); title=' '.join(unicodedata.normalize('NFKC',title).casefold().split()) if isinstance(title,str) else ''
   for label,value in [('url',_norm_url(obj.get('url'))),('doi',_norm_doi(obj.get('doi'))),('title',title)]:
    if not value:continue
    key=(label,value)
    for other in seen.get(key,[]):
     if layer=='d7' or other['layer']=='d7':
      counts[label+'_candidates']+=1
      candidates.append({'kind':label,'left':other,'right':coord,'disposition':'pending_not_merged'})
    seen.setdefault(key,[]).append(coord)
 return dict(counts),candidates

def _unknown_relation_count(rows):
 return sum(x['value'].get('predicate') not in RELATIONS for x in rows)

def validate_aux_source_coverage(d7,aux7):
 """Each source index has exactly one row for each D7 source, no duplicates."""
 errors=collections.Counter()
 expected=collections.Counter(x['value'].get('id') for x in d7.get('sources',[]))
 for name in ('SOURCE_DUPLICATE_REVIEW','SOURCE_ACCESS_INDEX'):
  path='d7/reports/'+name+'.jsonl'
  actual=collections.Counter(x['value'].get('source_id') for x in aux7.get(path,[]))
  if actual!=expected:errors['auxiliary_source_coverage_mismatch']+=1
 editions={x['value']['id']:x['value'] for x in d7.get('editions',[]) if 'id' in x['value']}
 locators={x['value']['id']:x['value'] for x in d7.get('locators',[]) if 'id' in x['value']}
 events={x['value']['id']:x['value'] for x in d7.get('source_access_events',[]) if 'id' in x['value']}
 for entry in aux7.get('d7/reports/SOURCE_ACCESS_INDEX.jsonl',[]):
  obj=entry['value'];source=obj.get('source_id')
  for key in ('edition_ids','locator_ids','access_event_ids'):
   if not isinstance(obj.get(key),list):errors['access_index_array_invalid']+=1
  for eid in obj.get('edition_ids',[]) if isinstance(obj.get('edition_ids'),list) else []:
   if editions.get(eid,{}).get('source_id')!=source:errors['access_index_source_mismatch']+=1
  for lid in obj.get('locator_ids',[]) if isinstance(obj.get('locator_ids'),list) else []:
   loc=locators.get(lid,{});edition=editions.get(loc.get('edition_id'),{})
   if edition.get('source_id')!=source:errors['access_index_source_mismatch']+=1
  for eid in obj.get('access_event_ids',[]) if isinstance(obj.get('access_event_ids'),list) else []:
   event=events.get(eid,{});loc=locators.get(event.get('locator_id') or event.get('source_locator_id'),{});edition=editions.get(loc.get('edition_id'),{})
   if event.get('source_id') is not None and event.get('source_id')!=source:errors['access_index_source_mismatch']+=1
   if edition.get('source_id') is not None and edition.get('source_id')!=source:errors['access_index_source_mismatch']+=1
   if not event or (event.get('source_id') is None and edition.get('source_id') is None):errors['access_index_source_unresolved']+=1
 return errors

def inspect_archive(path, *, mode='dry-run'):
 """Validate pinned D7 and embedded D6..D1 without writing research material."""
 errors=collections.Counter();report={'schema_version':'j1-d7-1','status':'fail','errors':{},'hashes':{},'manifests':{},'counts':{},'database_write':False,'canonical_promotion':False,'original_records_modified':False,'effective_real_data_permissions':{a:False for a in sorted(prior.ACTIONS)},'identity_values_emitted':False,'source_archive_required_to_recover_fields':True}
 def finish():report['errors']=dict(sorted(errors.items()));report['status']='fail' if errors else 'pass';return report
 archives=[]
 try:
  if isinstance(path, bytes):
   if len(path)>64*1024*1024:raise ValueError('archive too large')
   read_input=lambda: path
  else:
   read_input=lambda: prior._bounded_read(path)
  blob=read_input();report['hashes']['d7_before']=prior._sha(blob)
  if report['hashes']['d7_before']!=D7_SHA:errors['d7_sha_mismatch']+=1;return finish()
  def open_zip(blob,label,pin,manifest):
   report['hashes'][label]=prior._sha(blob)
   if pin and report['hashes'][label]!=pin:errors[label+'_sha_mismatch']+=1;return None
   z=prior._safe_archive(blob,errors)
   if z is None:return None
   archives.append(z)
   if manifest:report['manifests'][label]=prior._manifest(z,manifest,errors)
   return z
  d7=open_zip(blob,'d7',D7_SHA,'SHA256SUMS.txt')
  if not d7 or errors:return finish()
  # Prior handoff lists files in an older archive, not members of D7.
  # Compare only explicit corresponding members; report the rest pending.
  oldlines=d7.read('logs/HANDOFF_SHA256SUMS.txt').decode('utf8').splitlines();matched=0
  related={'contracts/GATE_J1_ACCEPTANCE.md':'contracts/GATE_J1_ACCEPTANCE.md','evidence/INDEPENDENT_D6_TESTS.json':'logs/HANDOFF_INDEPENDENT_D6_TESTS.json','inputs/SCRIPTURA_D6_SCOPE_RESEARCH.zip':'baseline/SCRIPTURA_D6_SCOPE_RESEARCH.zip'}
  if len(oldlines)!=6:errors['prior_handoff_manifest_invalid']+=1
  seen=set()
  for line in oldlines:
   match=re.fullmatch(r'([0-9a-f]{64})  (.+)',line)
   if not match:errors['prior_handoff_manifest_invalid']+=1;continue
   digest,name=match.groups()
   if name in seen:errors['prior_handoff_manifest_invalid']+=1
   seen.add(name)
   if name in related:
    if prior._sha(d7.read(related[name]))!=digest:errors['prior_handoff_mismatch']+=1
    matched+=1
  report['prior_external_handoff_manifest']={'entries':len(oldlines),'corresponding_members_checked':matched,'remaining_require_prior_handoff':len(oldlines)-matched}
  d6=open_zip(d7.read('baseline/SCRIPTURA_D6_SCOPE_RESEARCH.zip'),'d6',prior.D6_SHA,'SHA256SUMS.txt')
  if not d6 or errors:return finish()
  # D6 also carries a historical external handoff list. Only two members
  # have an exact correspondence in the pinned D6; the rest remain pending.
  d6_handoff=d6.read('logs/HANDOFF_SHA256SUMS.txt').decode('utf8').splitlines();matched6=0;seen6=set()
  related6={'contracts/RELIGIOUS_SCOPE_v0.2.md':'contracts/RELIGIOUS_SCOPE_v0.2.md','evidence/SCRIPTURA_D5_AUTHORITY_RESEARCH.zip':'baseline/SCRIPTURA_D5_AUTHORITY_RESEARCH.zip'}
  if len(d6_handoff)!=5:errors['d6_prior_handoff_manifest_invalid']+=1
  for line in d6_handoff:
   match=re.fullmatch(r'([0-9a-f]{64})  (.+)',line)
   if not match:errors['d6_prior_handoff_manifest_invalid']+=1;continue
   digest,name=match.groups()
   if name in seen6:errors['d6_prior_handoff_manifest_invalid']+=1
   seen6.add(name)
   if name in related6:
    if prior._sha(d6.read(related6[name]))!=digest:errors['d6_prior_handoff_mismatch']+=1
    matched6+=1
  report['d6_prior_external_handoff_manifest']={'entries':len(d6_handoff),'corresponding_members_checked':matched6,'remaining_require_prior_handoff':len(d6_handoff)-matched6}
  d5=open_zip(d6.read('baseline/SCRIPTURA_D5_AUTHORITY_RESEARCH.zip'),'d5',prior.D5_SHA,'logs/FILE_SHA256SUMS.txt')
  if not d5 or errors:return finish()
  d4=open_zip(d5.read('baseline/SCRIPTURA_D4_RESEARCH.zip'),'d4',prior.D4_SHA,'logs/FILE_SHA256SUMS.txt')
  if not d4 or errors:return finish()
  d3=open_zip(d4.read('baseline/SCRIPTURA_D3_DATA_RESEARCH.zip'),'d3',prior.D3_SHA,'logs/FILE_SHA256SUMS.txt')
  if not d3 or errors:return finish()
  d2=open_zip(d3.read('baseline/SCRIPTURA_D11_D2_RESEARCH.zip'),'d2',prior.D2_SHA,None)
  if not d2 or errors:return finish()
  d2manifest,report['manifests']['d2']=prior._json_manifest(d2,errors)
  d1bytes=d2.read('baseline/SCRIPTURA_GATE_D1_RESEARCH.zip')
  if prior._sha(d1bytes)!=d2manifest.get('baseline_d1_sha256'):errors['d1_sha_mismatch']+=1
  d1=open_zip(d1bytes,'d1',None,None)
  if not d1 or errors:return finish()
  _,report['manifests']['d1']=prior._json_manifest(d1,errors)
  base={};ds5={};ds6={};ds7={};aux6={};aux7={}
  for table in prior.BASE_TABLES:
   name=f'baseline/records/{table}.jsonl';base[table]=prior._records(d5,name,errors)
   prior._same_member(d5,name,d4,f'd4/records_merged/{table}.jsonl',errors,'d5_baseline_changed')
   prior._same_member(d4,f'baseline/records/{table}.jsonl',d3,f'd3/records_merged/{table}.jsonl',errors,'d4_baseline_changed')
   prior._same_member(d3,f'baseline/records/{table}.jsonl',d2,f'd2/records_merged/{table}.jsonl',errors,'d3_baseline_changed')
  for name in d5.namelist():
   if name.startswith('d5/records/') and name.endswith('.jsonl'):ds5[name.rsplit('/',1)[-1][:-6]]=prior._records(d5,name,errors)
  for table in prior.TABLES:
   ds6[table]=prior._records(d6,f'd6/records/{table}.jsonl',errors)
   if len(ds6[table])!=prior.EXPECTED[table]:errors['d6_count_mismatch']+=1
  for table in TABLES:
   ds7[table]=prior._records(d7,f'd7/records/{table}.jsonl',errors)
   if len(ds7[table])!=EXPECTED[table]:errors['d7_count_mismatch']+=1
  for z,prefix,out in ((d6,'d6/reports/',aux6),(d7,'d7/reports/',aux7)):
   for name in z.namelist():
    if name.startswith(prefix) and name.endswith('.jsonl'):out[name]=prior._records(z,name,errors)
  p_errors,p_refs=prior.validate_records(base,ds5,ds6);errors.update(p_errors)
  crosswalk=aux7.get('d7/reports/BASELINE_D6_D7_CROSSWALK.jsonl',[])
  semantic,refs,known,events=validate_records(base,ds5,ds6,ds7,crosswalk);errors.update(semantic)
  # Aux reports refer to a pending scope label once. It is not a real entity.
  pending_aux6=0;pending_aux7=0
  alias_allowed={'community_scope_id','community_or_target_id'}
  for label,tables in (('d6',aux6),('d7',aux7)):
   for aux_path,items in tables.items():
    for item in items:
     for field,value in item['value'].items():
      if field=='id' or not(field.endswith('_id') or field.endswith('_ids')):continue
      if field.endswith('_ids') and not isinstance(value,list):errors['auxiliary_reference_array_invalid']+=1;continue
      for target in value if isinstance(value,list) else [value]:
       if target in prior.EMPTY:continue
       if not isinstance(target,str) or target not in known:
        if field in alias_allowed:
         if label=='d6':pending_aux6+=1
         else:pending_aux7+=1
        else:errors['auxiliary_reference_unresolved']+=1
       else:
        loc=known[target];refs.append({'layer':label+'_auxiliary','table':aux_path.rsplit('/',1)[-1][:-6],'row':item['line'],'field':field,'target_layer':loc[0],'target_table':'authority_registries' if loc[1]=='authority_registry_traditions' else loc[1],'target_row':loc[2],'target_field':'tradition_id' if loc[1]=='authority_registry_traditions' else 'id'})
  errors.update(validate_aux_source_coverage(ds7,aux7))
  report['counts']={'baseline_d4':{k:len(v) for k,v in base.items()},'d5':{k:len(v) for k,v in ds5.items()},'d6':{k:len(v) for k,v in ds6.items()},'d7':{k:len(v) for k,v in ds7.items()},'d6_auxiliary':{k.rsplit('/',1)[-1]:len(v) for k,v in aux6.items()},'d7_auxiliary':{k.rsplit('/',1)[-1]:len(v) for k,v in aux7.items()}}
  report['totals']={'baseline_d4':sum(map(len,base.values())),'d5':sum(map(len,ds5.values())),'d6':sum(map(len,ds6.values())),'d7':sum(map(len,ds7.values())),'d6_auxiliary':sum(map(len,aux6.values())),'d7_auxiliary':sum(map(len,aux7.values())),'d7_and_auxiliary_reference_occurrences':len(refs)}
  duplicate_counts,duplicate_candidates=_duplicates(base,ds5,ds6,ds7)
  c=collections.Counter(x['value'].get('attribution_kind') if x['value'].get('attribution_kind') in prior.ATTRIBUTIONS else 'other_or_missing' for x in ds7['claims'])
  rights=collections.Counter(x['value'].get('decision','').lower() if isinstance(x['value'].get('decision'),str) and x['value']['decision'].lower() in ('unknown','conditional','allowed','prohibited') else 'other_or_missing' for x in ds7['rights'])
  report['semantics']={'d7_attributions':dict(sorted(c.items())),'d7_rights':dict(sorted(rights.items())),'d6_audit_targets':len(events),'d6_audit_events':len(ds7['audit_reviews']),'d6_crosswalk_rows':len(crosswalk),'d6_audit_multiple_events':sum(len(v)>1 for v in events.values()),'duplicate_candidates':duplicate_counts,'semantic_deduplication':'pending','official_adoption':'not_inferred','independent_human_review':'not_inferred','claim_truth':'not_adjudicated','verse_alignment':'not_inferred','corrections':'not_applied'}
  report['pending']={'source_truth_authority_rights_review':True,'semantic_deduplication':True,'external_historical_handoff_manifests':True,'versification_alignment':True,'d6_auxiliary_scope_references':pending_aux6,'d7_auxiliary_scope_references':pending_aux7,'unmapped_relation_predicates':_unknown_relation_count(ds7['relationships'])}
  if mode in ('dry-run','mapping-preview'):
   entries=[]
   for layer,tables in (('baseline_d4',base),('d5',ds5),('d6',ds6),('d7',ds7)):
    for table,items in tables.items():
     for item in items:entries.append({'layer':layer,'table':table,'row':item['line'],'line_sha256':item['sha256'],'disposition':'quarantined','reason_codes':['actual_research_read_only','rights_and_authority_not_granted']})
   for layer,tables in (('d6_auxiliary',aux6),('d7_auxiliary',aux7)):
    for name,items in tables.items():
     for item in items:entries.append({'layer':layer,'table':name.rsplit('/',1)[-1][:-6],'row':item['line'],'line_sha256':item['sha256'],'disposition':'quarantined','reason_codes':['actual_research_read_only','auxiliary_not_canonical']})
   report['quarantine']={'record_count':len(entries),'records':entries}
   if mode=='mapping-preview':report['mapping_preview']={'reference_occurrences':p_refs+refs,'raw_values_emitted':False,'source_zip_required_to_recover_fields':True,'duplicate_candidate_coordinates':duplicate_candidates}
  report['hashes']['d7_after']=prior._sha(read_input())
  if report['hashes']['d7_after']!=report['hashes']['d7_before']:errors['input_changed_during_inspection']+=1
 except (OSError,KeyError,UnicodeError,ValueError,TypeError,RuntimeError,RecursionError):errors['archive_processing_error']+=1
 finally:
  for z in reversed(archives):z.close()
 return finish()
