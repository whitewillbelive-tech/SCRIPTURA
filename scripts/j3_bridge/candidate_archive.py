"""Pinned D8/D9 read-only adapter. No upload, DB, promotion, or file extraction."""
import collections
import io
import os
import re
from zipfile import ZipFile
from i3_bridge import d6 as prior
from j2_bridge import candidate_readonly as base
from .d9_validation import TABLE_COUNTS, validate_d9, RELATIONS
from .private_io import read_checked_d8_layers

D9_SHA='d28a03e440ec6d330bf895d00cc6c01afd6e79b31feaf24ceb4ebccc612ba78e'

_GROUPS=('bibliography','own_summary','short_quote','full_text','private_link')
_SAFE_STATUS=frozenset(('verified_exact','partially_verified','source_checked','metadata_checked','pending','unknown','unmapped','direct_published_source_rechecked','translation_checked_human_review_pending','rendered_content_checked_adoption_unknown','source_label_checked_legal_event_ambiguous','direct_rendered_browser_checked','review_scan_checked_book_unseen'))

def _status(value): return value if isinstance(value,str) and value in _SAFE_STATUS else 'unmapped'

def _attach_d9_observations(existing, additions, layers, visibility):
 """Add D9 observations without overwriting older source or claim state."""
 coordinates={};objects={}
 for stage,tables in layers.items():
  for table,rows in tables.items():
   for item in rows:
    value=item['value'];ident=value.get('id')
    if isinstance(ident,str):
     coordinates[ident]=f'{stage}:{table}:{item["line"]}';objects[ident]=value
 records=[dict(row) for row in existing+additions]
 targets={row.get('key'):row for row in records}
 eligibility={}
 for item in visibility:
  value=item['value'];ident=value.get('entity_id');group=value.get('field_group');decision=value.get('decision')
  if group in _GROUPS and decision in ('unknown','unmapped','metadata_candidate'):
   eligibility.setdefault(ident,{})[group]=decision
 # A field group is source evidence, never permission to unmask the field.
 for ident,coord in coordinates.items():
  row=targets.get(coord)
  if row is None:continue
  raw=objects[ident];relevant={'source':ident} if row.get('record_kind')=='source' else {'claim':ident}
  if row.get('record_kind')=='claim':
   lid=raw.get('source_locator_id') or raw.get('locator_id');loc=objects.get(lid,{})
   eid=loc.get('edition_id');ed=objects.get(eid,{})
   relevant.update({'locator':lid,'edition':eid,'source':ed.get('source_id') or loc.get('source_id')})
  field_e={kind:{g:eligibility[ref].get(g,'unmapped') for g in _GROUPS} for kind,ref in relevant.items() if ref in eligibility}
  row['field_eligibility']=field_e
  row['d9_observations']=[];row['d9_rights_observations']=[]
 # Only D9 dataset receives these additional observations. D8 records are not mutated.
 d9=layers['d9']
 for table,field,kind in (('audit_reviews','baseline_record_id','audit_review'),('review_queue','baseline_target_id','review_queue'),('evidence','claim_id','evidence')):
  for item in d9.get(table,[]):
   raw=item['value']; row=targets.get(coordinates.get(raw.get(field)))
   if row is not None:
    row['d9_observations'].append({'kind':kind,'status':_status(raw.get('observation_status') or raw.get('result_status') or raw.get('status')),'method':'unknown','direction':'unknown','target_key':None,'relation_type':'unmapped'})
 for item in d9.get('relationships',[]):
  raw=item['value'];subject=raw.get('subject_id');obj=raw.get('object_id')
  for ident,target,direction in ((subject,obj,'outgoing'),(obj,subject,'incoming')):
   row=targets.get(coordinates.get(ident))
   if row is not None:
    row['d9_observations'].append({'kind':'relationship','status':_status(raw.get('status')),'method':'unknown','direction':direction,'target_key':coordinates.get(target),'relation_type':raw.get('predicate') if raw.get('predicate') in RELATIONS else 'unmapped'})
 # A new D9 edition may be attached to a previous source: append a distinct
 # edition observation, never replace any previous edition or decision.
 for item in d9.get('editions',[]):
  raw=item['value']; eid=raw.get('id');edition_key=coordinates.get(eid)
  source_row=targets.get(coordinates.get(raw.get('source_id')))
  if source_row is not None:
   rights={action:'not_recorded' for action in prior.ACTIONS}
   for right in d9.get('rights',[]):
    v=right['value']
    if v.get('edition_id')==eid and v.get('action') in rights and v.get('decision') in ('unknown','conditional','allowed','prohibited'):
     rights[v['action']]=v['decision']
   entry={'key':edition_key,'rights':rights,'rights_overrides':[],'effective_permissions':{a:False for a in prior.ACTIONS}}
   previous=list(source_row.get('edition_rights',[]))
   if not any(x.get('key')==edition_key for x in previous if isinstance(x,dict)):
    previous.append(entry);source_row['edition_rights']=previous
 for item in d9.get('rights_actions',[]):
  raw=item['value'];eid=raw.get('edition_id');edition=objects.get(eid,{})
  action=raw.get('action');decision=raw.get('decision')
  if action not in prior.ACTIONS or decision not in ('unknown','conditional','allowed','prohibited'):continue
  edition_key=coordinates.get(eid);source_key=coordinates.get(edition.get('source_id'))
  for row in records:
   if row.get('key')==source_key or row.get('edition_key')==edition_key:
    row.setdefault('d9_rights_observations',[]).append({'edition_key':edition_key,'action':action,'decision':decision})
 return records

def load_versioned_archive(path):
 """Fixed D8/D9 only; fail closed with non-sensitive errors and no raw output."""
 try:
  if isinstance(path,bytes):
   if len(path)>64*1024*1024:raise base.CandidateError('archive_invalid')
   read=lambda:path
  else:
   location=os.fspath(path)
   if not isinstance(location,str) or location.startswith(('\\\\','//','\\/','/\\')) or re.match(r'^[A-Za-z][A-Za-z0-9+.-]+:',location):raise base.CandidateError('archive_not_local')
   read=lambda:prior._bounded_read(path)
  blob=read();digest=prior._sha(blob)
  if digest==base.D8_SHA:
   result=base.load_candidate_archive(blob)
   if prior._sha(read())!=digest:raise base.CandidateError('archive_changed')
   return result
  if digest!=D9_SHA:raise base.CandidateError('archive_not_recognized')
  errors=collections.Counter();z=prior._safe_archive(blob,errors)
  if z is None:raise base.CandidateError('archive_invalid')
  with z:
   count=prior._manifest(z,'SHA256SUMS.txt',errors)
   if count!=46 or errors:raise base.CandidateError('archive_invalid')
   d8blob=z.read('baseline/SCRIPTURA_D8_RESEARCH.zip')
   original=base.load_candidate_archive(d8blob)
   with ZipFile(io.BytesIO(d8blob)) as d8:
    snapshot=read_checked_d8_layers(d8)
   if snapshot.error_count:raise base.CandidateError('baseline_invalid')
   layers=snapshot.layers
   d9={t:prior._records(z,f'd9/records/{t}.jsonl',errors) for t in TABLE_COUNTS}
   visibility=prior._records(z,'d9/PREVIEW_ELIGIBILITY.jsonl',errors)
   auxiliary={n:prior._records(z,'d9/reports/'+n+'.jsonl',errors) for n in ('SOURCE_ACCESS_INDEX','SOURCE_DUPLICATE_REVIEW')}
   baseline_targets=prior._records(z,'logs/BASELINE_TARGETS.jsonl',errors)
   validation,metrics=validate_d9(d9,layers,visibility,auxiliary=auxiliary,baseline_targets=baseline_targets)
   if validation or errors:raise base.CandidateError('archive_invalid')
   layers['d9']=d9
   additions=[r for r in base._build_projection(layers) if r.get('stage')=='d9']
   if len(additions)!=20 or sum(r.get('record_kind')=='claim' for r in additions)!=6 or sum(r.get('record_kind')=='source' for r in additions)!=14:raise base.CandidateError('archive_invalid')
   existing=original['records'];keys=[r.get('key') for r in existing+additions]
   if None in keys or len(keys)!=len(set(keys)):raise base.CandidateError('archive_invalid')
   if prior._sha(read())!=D9_SHA:raise base.CandidateError('archive_changed')
   combined=_attach_d9_observations(existing, additions, layers, visibility)
   summary={k:metrics['visibility'].get(k,0) for k in ('metadata_candidate','candidate_visible_local','unknown','unmapped')};summary['total']=metrics['eligibility_total']
   by_stage=original['counts'].get('by_stage',{}).copy();by_stage['d9']=metrics['counts']
   unmapped=original['unmapped_summary'].copy();partial={'claims','sources','editions','locators','passages','rights','evidence','relationships','source_access_events','audit_reviews','review_queue','rights_actions'}
   unmapped['d9']={k:{'input_count':v,'mapping':'partial' if k in partial else 'unmapped'} for k,v in metrics['counts'].items()}
   return {'dataset':'D9','counts':{'d8':original['counts']['d8'],'d9':metrics['counts'],'by_stage':by_stage,'display_records':len(existing)+len(additions)},
     'unmapped_summary':unmapped,'validation_metrics':{'d9_unmapped_relations':metrics['unmapped_relation_predicates']},
     'visibility_summary':summary,'warnings':original['warnings']+['D9 metadata_candidate는 표시 승인이 아니며 이름·원문·URL은 가려집니다.'],
     'facets':{},'records':combined}
 except base.CandidateError as exc:
  # Re-raise only known fixed codes; an upstream exception can otherwise
  # smuggle a record, path or other private value into a traceback.
  allowed={'archive_invalid','archive_not_local','archive_not_recognized','archive_changed','baseline_invalid'}
  code=exc.args[0] if len(exc.args)==1 and type(exc.args[0]) is str and exc.args[0] in allowed else 'archive_invalid'
  raise base.CandidateError(code) from None
 except Exception:raise base.CandidateError('archive_invalid') from None
