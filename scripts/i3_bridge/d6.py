"""Read-only fixed D6 receipt; never connects to any database or emits research text."""
from __future__ import annotations
import collections
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path, PurePosixPath

D6_SHA = '6d94de447eba8517c038f6f709c8b1040e0c6efbdd4676f9e19aea568d3e59da'
D5_SHA = '4709ddbe914c276e68ebcc66cee1d76e1c096e0071992eb53b9e4c2f03e96d19'
D4_SHA = '05ab5bdf3fc258f39b926257c771ef4a17138355aa072cb8bc97c56387999beb'
D3_SHA = 'baf206d2846544f1e1bb20622ac10c557394b71aa41cfd6e2be5bbafade347be'
D2_SHA = 'c8b64b9144367a8526c77b121b3343f04a7c683276f9fd239b2cc51458589a47'
TABLES = ('communities','sources','editions','locators','passages','claims','assessments','rights','relationships','authority','evidence','source_access_events')
EXPECTED = dict(zip(TABLES,(5,31,31,42,53,33,8,279,11,24,34,33)))
BASE_TABLES = ('sources','editions','locators','rights','passages','alignments','agents','affiliations','claims','evidence','relations','reviews')
ACTIONS = frozenset(('browse','collect_metadata','store_raw','store_excerpt','index_fulltext','embed','send_to_model','redistribute','public_link'))
ATTRIBUTIONS = frozenset(('official_doctrine','community_self_explanation','academic_interpretation','individual_opinion','external_critique','scriptural_narrative','textual_narrative','unknown'))
FORBIDDEN = frozenset(('raw_text','full_text','html_full_text','pdf_bytes','embedding','embeddings'))
REQUIRED = {
 'communities':('id','canonical_name','self_designation','aliases','relation_to_bible','authority_structure','coverage_status','independent_review_status'),
 'sources':('id','title','creator','url','kind'), 'editions':('id','source_id','label'),
 'locators':('id','edition_id','location','verification_status'), 'passages':('id','corpus','reference_scheme','reference'),
 'claims':('id','community_id','source_locator_id','passage_ids','statement_ko','attribution_kind','authority_status','verification_status'),
 'assessments':('id','target_community_id','assessor','assessment_date','status_as_of','locator_id'),
 'rights':('id','edition_id','action','decision','evidence_locator_id'),
 'relationships':('id','subject_id','predicate','object_id','locator_id','status'),
 'authority':('id',), 'evidence':('id','claim_id','locator_id'), 'source_access_events':('id',),
}
# D5 attribute names and D6 use overlapping names with differing ranges. A target
# is never manufactured: unresolved or ambiguous links block structural PASS.
TYPED = {
 ('d5','editions','source_id'):{'sources'},('d5','locators','edition_id'):{'editions'},
 ('d5','authority_documents','authority_registry_id'):{'authority_registries'},
 ('d5','claim_scope_audits','baseline_claim_id'):{'claims'},('d5','claim_scope_audits','authority_document_id'):{'authority_documents'},
 ('d5','position_attestations','document_id'):{'authority_documents'},('d5','position_attestations','baseline_claim_id'):{'claims'},
 ('d5','position_attestations','passage_ids'):{'passages'},('d5','interpretive_evidence','position_attestation_id'):{'position_attestations'},
 ('d5','rights_delta','edition_id'):{'editions'},('d5','audit_conflicts','claim_id'):{'claims'},('d5','audit_conflicts','selected_audit_id'):{'claim_scope_audits'},
 ('d6','editions','source_id'):{'sources'},('d6','locators','edition_id'):{'editions'},
 ('d6','claims','source_locator_id'):{'locators'},('d6','claims','passage_ids'):{'passages'},
 ('d6','assessments','target_community_id'):{'communities','authority_registry_traditions'},
 ('d6','rights','edition_id'):{'editions'},('d6','rights','evidence_locator_id'):{'locators'},
 ('d6','evidence','claim_id'):{'claims'},('d6','evidence','locator_id'):{'locators'},('d6','evidence','passage_ids'):{'passages'},
 ('d6','authority','edition_id'):{'editions'},('d6','authority','locator_id'):{'locators'},('d6','authority','source_locator_ids'):{'locators'},
 ('d6','assessments','locator_id'):{'locators'},('d6','relationships','locator_id'):{'locators'},
 ('d6','source_access_events','source_id'):{'sources'},('d6','source_access_events','edition_id'):{'editions'},
 ('d6','source_access_events','locator_id'):{'locators'},('d6','source_access_events','source_locator_id'):{'locators'},
 ('d6','communities','identity_locator_id'):{'locators'},('d6','communities','identity_locator_ids'):{'locators'},('d6','communities','inclusion_evidence_locator_ids'):{'locators'},
 ('d6','communities','institution_document_id'):{'authority_documents','sources'},
 ('d6','claims','community_id'):{'communities','authority_registry_traditions'},
 ('d6','authority','community_id'):{'communities','authority_registry_traditions'},
}
# Checked only for known predicate families; unknown types stay quarantined.
RELATION_TYPES = {
 'interpretive_contrast_candidate':({'claims'},{'claims'}),
 'response_to_specific_assessment_candidate':({'claims'},{'assessments'}),
 'contrasting_interpretation_on_shared_text':({'claims'},{'claims'}),
 'similar_topic_and_conclusion_to':({'claims'},{'claims'}),
 'external_institutional_assessment_of':({'assessments'},{'communities','authority_registry_traditions'}),
 'community_context_from':({'claims'},{'authority_documents'}),
 'documented_in_reported_community_interview':({'claims'},{'editions'}),
 'reports_process_about':({'assessments'},{'communities'}),
 'critiques_personal_lectures_of':({'assessments'},{'communities'}),
 'shares_topic_with_later_material':({'assessments'},{'claims'}),
 'possible_related_criticism':({'claims'},{'claims'}),
 'rebuts':({'claims'},{'claims'}), 'directly_rebuts':({'claims'},{'claims'}),
}
REQUIRED_FKS = {
 ('d6','editions','source_id'),('d6','locators','edition_id'),('d6','claims','source_locator_id'),
 ('d6','assessments','target_community_id'),('d6','assessments','locator_id'),
 ('d6','rights','edition_id'),('d6','relationships','subject_id'),('d6','relationships','object_id'),
 ('d6','evidence','claim_id'),('d6','evidence','locator_id'),
 ('d5','editions','source_id'),('d5','locators','edition_id'),('d5','rights_delta','edition_id'),
 ('d5','authority_documents','authority_registry_id'),('d5','authority_documents','locator_id'),
 ('d5','claim_scope_audits','baseline_claim_id'),('d5','position_attestations','document_id'),
 ('d5','interpretive_evidence','position_attestation_id'),('d5','interpretive_evidence','source_locator_id'),
}
EMPTY = (None,'','UNKNOWN','unknown','pending')

def _sha(data): return hashlib.sha256(data).hexdigest()

def _bounded_read(path):
 with Path(path).open('rb') as stream:
  blob=stream.read(64*1024*1024+1)
 if len(blob)>64*1024*1024:raise ValueError('archive too large')
 return blob

def _same_member(left,left_name,right,right_name,errors,code):
 try:
  if left.read(left_name)!=right.read(right_name):errors[code]+=1
 except KeyError:errors[code]+=1

def _safe_archive(blob, errors):
 try:
  if len(blob)>64*1024*1024: raise ValueError('size')
  z=zipfile.ZipFile(io.BytesIO(blob)); infos=z.infolist(); names=[x.filename for x in infos]
  if len(infos)>1000 or len(names)!=len(set(names)) or sum(x.file_size for x in infos)>128*1024*1024: raise ValueError('limits')
  for x in infos:
   p=PurePosixPath(x.filename)
   if p.is_absolute() or '..' in p.parts or '\\' in x.filename or x.file_size>32*1024*1024 or (x.file_size>1024*1024 and x.file_size>200*max(1,x.compress_size)): raise ValueError('unsafe')
  if z.testzip() is not None: raise ValueError('crc')
  return z
 except (ValueError,zipfile.BadZipFile,RuntimeError,OSError):
  errors['unsafe_or_corrupt_archive']+=1;return None

def _manifest(z,path,errors):
 members={i.filename for i in z.infolist() if not i.is_dir()}; seen=set()
 try: lines=z.read(path).decode('utf8').splitlines()
 except (KeyError,UnicodeError):errors['manifest_missing_or_invalid']+=1;return 0
 for line in lines:
  m=re.fullmatch(r'([0-9a-f]{64})  (.+)',line)
  if not m:errors['manifest_entry_invalid']+=1;continue
  h,name=m.groups()
  if name not in members or name==path or name in seen:errors['manifest_entry_invalid']+=1;continue
  seen.add(name)
  if _sha(z.read(name))!=h:errors['manifest_hash_mismatch']+=1
 if seen!=members-{path}:errors['manifest_coverage_mismatch']+=1
 return len(lines)

def _strict_json(s):
 def pairs(seq):
  d={}
  for k,v in seq:
   if k in d: raise ValueError('duplicate json key')
   d[k]=v
  return d
 return json.loads(s,object_pairs_hook=pairs,parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite')))

def _json_manifest(z,errors):
 """Verify path/size/SHA-256 for the complete D1 or D2 ZIP member set."""
 members={i.filename for i in z.infolist() if not i.is_dir()}; seen=set()
 try:
  doc=_strict_json(z.read('RUN_MANIFEST.json').decode('utf8'))
  values=doc['file_hashes']
  if not isinstance(doc,dict) or not isinstance(values,list):raise ValueError('invalid manifest')
  for entry in values:
   if not isinstance(entry,dict):errors['json_manifest_entry_invalid']+=1;continue
   name=entry.get('path');digest=entry.get('sha256');size=entry.get('bytes')
   if not isinstance(name,str) or name not in members or name=='RUN_MANIFEST.json' or name in seen or not isinstance(size,int) or isinstance(size,bool) or not isinstance(digest,str) or not re.fullmatch('[0-9a-f]{64}',digest):
    errors['json_manifest_entry_invalid']+=1;continue
   seen.add(name); raw=z.read(name)
   if len(raw)!=size or _sha(raw)!=digest:errors['json_manifest_hash_or_size_mismatch']+=1
  if seen!=members-{'RUN_MANIFEST.json'}:errors['json_manifest_coverage_mismatch']+=1
  return doc,len(values)
 except (KeyError,ValueError,UnicodeError,TypeError,RecursionError):
  errors['json_manifest_invalid']+=1;return {},0

def _records(z,name,errors):
 try: lines=z.read(name).splitlines(keepends=True)
 except KeyError:errors['record_file_missing']+=1;return []
 out=[]
 for n,line in enumerate(lines,1):
  if not line.strip():errors['blank_jsonl_line']+=1;continue
  try:
   data=_strict_json(line.decode('utf-8-sig'))
   if not isinstance(data,dict):raise ValueError('not an object')
   out.append({'value':data,'line':n,'sha256':_sha(line)})
  except (ValueError,UnicodeError,RecursionError):errors['invalid_jsonl']+=1
 return out

def validate_records(base,d5,d6):
 """Structural checks only; no fact, copyright, person, or doctrine certification."""
 e=collections.Counter(); all_ids={}; aliases={}; refs=[]
 for layer,tables in (('base',base),('d5',d5),('d6',d6)):
  for table,entries in tables.items():
   for entry in entries:
    x=entry['value']; ident=x.get('id')
    # D5 audit_conflicts has no ID by design.
    if ident is None and layer=='d5' and table=='audit_conflicts':continue
    if not isinstance(ident,str) or not ident.strip():e['invalid_id']+=1;continue
    if ident in all_ids:e['duplicate_record_id']+=1
    else:all_ids[ident]=(layer,table,entry['line'])
    if layer=='d6':
     for k in REQUIRED[table]:
      if k not in x:e['required_field_missing']+=1
      elif x[k] in (None,'') and (table,k) not in {('claims','community_id'),('assessments','assessment_date'),('rights','evidence_locator_id')}:e['required_field_empty']+=1
     if FORBIDDEN.intersection(x):e['prohibited_content_field']+=1
     if x.get('raw_text_saved') is True or x.get('raw_file_stored') is True:e['raw_content_persisted_flag']+=1
     if x.get('independent_human_review') is True or x.get('scholarly_reviewed') is True or x.get('independent_review_status') in ('human_review_documented','scholarly_reviewed'):e['unverified_human_review_claim']+=1
     if x.get('authority_status')=='adoption_documented' and not any(x.get(k) for k in ('adoption_evidence_locator_id','adoption_evidence','formal_adoption_evidence','adoption_basis')):e['unsupported_adoption']+=1
 for entry in d5.get('authority_registries',[]):
  x=entry['value']; ident=x.get('tradition_id')
  if isinstance(ident,str) and ident:
   # A tradition reference is an alias, not another community record.
   if ident in all_ids or ident in aliases:e['duplicate_tradition_alias']+=1
   aliases[ident]=('d5','authority_registry_traditions',entry['line'])
 known={**all_ids,**aliases}
 for layer,tables in (('d5',d5),('d6',d6)):
  for table,entries in tables.items():
   for entry in entries:
    x=entry['value']
    for key,v in x.items():
     if key=='id' or not (key.endswith('_id') or key.endswith('_ids')):continue
     if key.endswith('_ids') and not isinstance(v,list):e['reference_array_invalid']+=1;continue
     for val in v if isinstance(v,list) else [v]:
      if val in EMPTY:
       if (layer,table,key) in REQUIRED_FKS:e['required_reference_pending']+=1
       continue
      if not isinstance(val,str) or val not in known:e['reference_unresolved']+=1;continue
      target=known[val]; expected=TYPED.get((layer,table,key))
      if expected is None and ('locator_id' in key or key.endswith('locator_ids')):expected={'locators'}
      if expected and target[1] not in expected:e['reference_wrong_type']+=1
      refs.append({'layer':layer,'table':table,'row':entry['line'],'field':key,'target_layer':target[0],'target_table':'authority_registries' if target[1]=='authority_registry_traditions' else target[1],'target_row':target[2],'target_field':'tradition_id' if target[1]=='authority_registry_traditions' else 'id'})
    if layer!='d6':continue
    if table=='claims':
     if x.get('attribution_kind') not in ATTRIBUTIONS:e['invalid_attribution']+=1
     if not isinstance(x.get('passage_ids'),list):e['passage_reference_invalid']+=1
     if x.get('attribution_kind')=='official_doctrine' and not any(x.get(k) for k in ('adoption_evidence_locator_id','adoption_evidence','formal_adoption_evidence','adoption_basis')):e['unsupported_official_doctrine']+=1
    if table=='assessments':
     status=str(x.get('decision_status',x.get('status',''))).lower()
     if status in ('final','final_decision','confirmed_final','finalized') and not any(x.get(k) for k in ('decision_evidence','decision_evidence_locator_id','final_decision_basis')):e['unsupported_final_decision']+=1
     if status in ('pending','ongoing','investigation','investigation_ongoing') and x.get('final_decision') is True:e['investigation_misrepresented_final']+=1
    if table=='relationships' and x.get('predicate') in RELATION_TYPES:
     subjects,objects=RELATION_TYPES[x['predicate']]
     subject=known.get(x.get('subject_id'));obj=known.get(x.get('object_id'))
     if subject and subject[1] not in subjects or obj and obj[1] not in objects:e['relation_direction_or_type_mismatch']+=1
    if table=='relationships' and x.get('predicate') in ('rebuts','directly_rebuts') and x.get('status') in ('verified','source_checked') and not x.get('direct_relation_evidence'):e['unsupported_direct_rebuttal']+=1
    if table=='rights':
     decision=x.get('decision');decision=decision.lower() if isinstance(decision,str) else ''
     if x.get('action') not in ACTIONS:e['invalid_rights_action']+=1
     if decision not in ('unknown','conditional','allowed','prohibited'):e['invalid_rights_decision']+=1
     if decision in ('allowed','conditional') and (x.get('evidence_locator_id') in EMPTY or not any(x.get(k) for k in ('action_specific_basis','action_specific_evidence','permission_scope','scope_note','notes'))):e['permission_evidence_missing']+=1
 claims={x['value'].get('id'):x['value'] for x in d6.get('claims',[])}
 for item in d6.get('evidence',[]):
  evidence=item['value'];claim=claims.get(evidence.get('claim_id'))
  if claim and evidence.get('locator_id')!=claim.get('source_locator_id'):e['evidence_claim_locator_mismatch']+=1
 pairs=collections.Counter((x['value'].get('edition_id'),x['value'].get('action')) for x in d6.get('rights',[]))
 for x in d6.get('editions',[]):
  for action in ACTIONS:
   if pairs[(x['value'].get('id'),action)]!=1:e['rights_matrix_incomplete']+=1
 return e,refs

def inspect_archive(path, *, mode='dry-run'):
 """Read pinned bytes only; output hashes, field names, fixed codes, counts.

 The source ZIP remains the sole lossless archive. Hashes cannot reconstruct it.
 No database connections, file extraction, rights grants, or promotions occur.
 """
 errors=collections.Counter(); report={'schema_version':'i3-d6-1','status':'fail','errors':{},'hashes':{},'manifests':{},'counts':{},'database_write':False,'canonical_promotion':False,'actual_research_quarantined':True,'original_records_modified':False,'public_report_reconstructs_original':False}
 def finish():
  report['errors']=dict(sorted(errors.items()));report['status']='fail' if errors else 'pass';report['actual_research_quarantined']=not bool(errors);return report
 try:
  blob=_bounded_read(path); report['hashes']['d6_before']=_sha(blob)
  if report['hashes']['d6_before']!=D6_SHA:errors['d6_sha_mismatch']+=1;return finish()
  archives=[]
  def open_nested(blob,label,pin,manifest):
   digest=_sha(blob);report['hashes'][label]=digest
   if digest!=pin:errors[label+'_sha_mismatch']+=1;return None
   z=_safe_archive(blob,errors)
   if z is None:return None
   archives.append(z)
   if manifest:report['manifests'][label]=_manifest(z,manifest,errors)
   return z
  try:
   d6=open_nested(blob,'d6',D6_SHA,'SHA256SUMS.txt')
   if not d6 or errors:return finish()
   # This is an inherited, external handoff listing, not D6's file manifest.
   # Two correspondences exist in D6; the remaining three require that older ZIP.
   oldlines=d6.read('logs/HANDOFF_SHA256SUMS.txt').decode('utf8').splitlines();matched=0
   related={'contracts/RELIGIOUS_SCOPE_v0.2.md':'contracts/RELIGIOUS_SCOPE_v0.2.md','evidence/SCRIPTURA_D5_AUTHORITY_RESEARCH.zip':'baseline/SCRIPTURA_D5_AUTHORITY_RESEARCH.zip'}
   if len(oldlines)!=5:errors['prior_handoff_manifest_invalid']+=1
   for line in oldlines:
    m=re.fullmatch(r'([0-9a-f]{64})  (.+)',line)
    if not m:errors['prior_handoff_manifest_invalid']+=1;continue
    h,name=m.groups()
    if name in related:
     if _sha(d6.read(related[name]))!=h:errors['prior_handoff_mismatch']+=1
     matched+=1
   report['prior_external_handoff_manifest']={'entries':len(oldlines),'corresponding_members_checked':matched,'remaining_require_prior_handoff':len(oldlines)-matched}
   d5=open_nested(d6.read('baseline/SCRIPTURA_D5_AUTHORITY_RESEARCH.zip'),'d5',D5_SHA,'logs/FILE_SHA256SUMS.txt')
   if not d5 or errors:return finish()
   d4=open_nested(d5.read('baseline/SCRIPTURA_D4_RESEARCH.zip'),'d4',D4_SHA,'logs/FILE_SHA256SUMS.txt')
   if not d4 or errors:return finish()
   d3=open_nested(d4.read('baseline/SCRIPTURA_D3_DATA_RESEARCH.zip'),'d3',D3_SHA,'logs/FILE_SHA256SUMS.txt')
   if not d3 or errors:return finish()
   d2=open_nested(d3.read('baseline/SCRIPTURA_D11_D2_RESEARCH.zip'),'d2',D2_SHA,None)
   if not d2 or errors:return finish()
   # D2 and D1 manifests list each member, byte size and SHA-256;
   # pin the nested D1 archive recorded in D2 as well.
   d2_manifest,d2_manifest_entries=_json_manifest(d2,errors)
   report['manifests']['d2']=d2_manifest_entries
   d1_blob=d2.read('baseline/SCRIPTURA_GATE_D1_RESEARCH.zip')
   d1_sha=_sha(d1_blob);report['hashes']['d1']=d1_sha
   if d2_manifest.get('baseline_d1_sha256')!=d1_sha:errors['d1_sha_mismatch']+=1
   d1=_safe_archive(d1_blob,errors)
   if d1:
    archives.append(d1)
    _,d1_manifest_entries=_json_manifest(d1,errors)
    report['manifests']['d1']=d1_manifest_entries
   base={};ds5={};ds6={}
   for table in BASE_TABLES:
    name=f'baseline/records/{table}.jsonl'; base[table]=_records(d5,name,errors)
    _same_member(d5,name,d4,f'd4/records_merged/{table}.jsonl',errors,'d5_baseline_record_changed')
    _same_member(d4,f'baseline/records/{table}.jsonl',d3,f'd3/records_merged/{table}.jsonl',errors,'d4_baseline_record_changed')
    _same_member(d3,f'baseline/records/{table}.jsonl',d2,f'd2/records_merged/{table}.jsonl',errors,'d3_baseline_record_changed')
   for name in d5.namelist():
    if name.startswith('d5/records/') and name.endswith('.jsonl'):
     ds5[name.rsplit('/',1)[-1][:-6]]=_records(d5,name,errors)
   for table in TABLES:ds6[table]=_records(d6,f'd6/records/{table}.jsonl',errors)
   for table,count in EXPECTED.items():
    if len(ds6[table])!=count:errors['d6_record_count_mismatch']+=1
   # Auxiliary report JSONL is inspected structurally, but never interpreted
   # as additional canonical claims or authorizations.
   auxiliary={}
   for name in d6.namelist():
    if name.startswith('d6/reports/') and name.endswith('.jsonl'):
     auxiliary[name]=_records(d6,name,errors)
   sem,refs=validate_records(base,ds5,ds6);errors.update(sem)
   # Auxiliary rows without IDs remain observations, not canonical entities.
   # D6 candidate community_scope_id is an unresolved work-in-progress label.
   known={r['value']['id'] for layer in (base,ds5,ds6) for rows in layer.values() for r in rows if isinstance(r['value'].get('id'),str)}
   known.update(r['value']['tradition_id'] for r in ds5.get('authority_registries',[]) if isinstance(r['value'].get('tradition_id'),str))
   aux_ids=set();pending_aux_refs=0
   for aux_path,rows in auxiliary.items():
    for row in rows:
     obj=row['value']; ident=obj.get('id')
     if ident is not None:
      if not isinstance(ident,str) or not ident or ident in known or ident in aux_ids:errors['auxiliary_id_invalid']+=1
      else:aux_ids.add(ident)
     for field,val in obj.items():
      if field=='id' or not (field.endswith('_id') or field.endswith('_ids')):continue
      if field.endswith('_ids') and not isinstance(val,list):errors['auxiliary_reference_array_invalid']+=1;continue
      for target in val if isinstance(val,list) else [val]:
       if target in EMPTY:continue
       if not isinstance(target,str) or target not in known:
        if field=='community_scope_id':pending_aux_refs+=1
        else:errors['auxiliary_reference_unresolved']+=1
   report['auxiliary_pending_scope_references']=pending_aux_refs
   report['counts']={'baseline_d4':{k:len(v) for k,v in base.items()},'d5':{k:len(v) for k,v in ds5.items()},'d6':{k:len(v) for k,v in ds6.items()},'d6_auxiliary':{k.rsplit('/',1)[-1]:len(v) for k,v in auxiliary.items()}}
   report['totals']={'baseline_d4':sum(map(len,base.values())),'d5':sum(map(len,ds5.values())),'d6':sum(map(len,ds6.values())),'d6_auxiliary':sum(map(len,auxiliary.values())),'resolved_reference_occurrences':len(refs)}
   claims=[x['value'] for x in ds6['claims']];rights=[x['value'] for x in ds6['rights']]; relationships=[x['value'] for x in ds6['relationships']]
   def count_enum(values, allowed):
    # Untrusted values are mapped to a fixed fallback, never directly published.
    c=collections.Counter(v if isinstance(v,str) and v in allowed else 'other_or_missing' for v in values)
    return dict(sorted(c.items()))
   report['semantics']={
    'attributions':count_enum((x.get('attribution_kind') for x in claims),ATTRIBUTIONS),
    'claims_without_community':sum(x.get('community_id') is None for x in claims),
    'claims_community_role_present':sum('community_id_role' in x for x in claims),
    'rights_decisions':count_enum((x.get('decision','').lower() if isinstance(x.get('decision'),str) else '' for x in rights),{'unknown','conditional','allowed','prohibited'}),
    'effective_real_data_permissions':{k:False for k in sorted(ACTIONS)},
    'no_automatic_official_adoption':True,'no_inferred_speaker_membership':True,'no_inferred_direct_rebuttal':True,'no_inferred_passage_alignment':True,
    'passages_without_alignment_status':sum('alignment_status' not in x['value'] for x in ds6['passages']),
    'relationship_records':len(relationships),
   }
   # Quarantine entries refer to immutable location and full raw-line digest.
   # The metadata/record content remains solely in the source archive.
   if mode in ('dry-run','mapping-preview'):
    entries=[]
    for layer,tables in (('baseline_d4',base),('d5',ds5),('d6',ds6)):
     for table,items in tables.items():
      for item in items:
       record={'layer':layer,'table':table,'row':item['line'],'line_sha256':item['sha256'],'disposition':'quarantined','reason_codes':['actual_research_read_only','rights_and_authority_not_granted']}
       entries.append(record)
    for aux_path,items in auxiliary.items():
     for item in items:entries.append({'layer':'d6_auxiliary','table':aux_path.rsplit('/',1)[-1][:-6],'row':item['line'],'line_sha256':item['sha256'],'disposition':'quarantined','reason_codes':['actual_research_read_only','auxiliary_not_canonical']})
    report['quarantine']={'record_count':len(entries),'records':entries}
    if mode=='mapping-preview':report['mapping_preview']={'reference_occurrences':refs,'raw_values_emitted':False,'source_zip_required_to_recover_fields':True}
  finally:
   for a in reversed(archives):a.close()
  # Detect source changes during inspection. Never open the input for writing.
  report['hashes']['d6_after']=_sha(_bounded_read(path))
  if report['hashes']['d6_after']!=report['hashes']['d6_before']:errors['input_changed_during_inspection']+=1
 except (OSError,KeyError,UnicodeError,ValueError,zipfile.BadZipFile,RuntimeError,TypeError,RecursionError):errors['archive_processing_error']+=1
 return finish()
