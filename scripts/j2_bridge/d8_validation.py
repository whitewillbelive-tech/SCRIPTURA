"""D-8 structural checks on in-memory records; errors contain codes only.

These checks do not establish display eligibility, legal permission, scholarly
review, official adoption, truth, or identity. No original record is changed.
"""
from collections import Counter, defaultdict

ACTIONS=frozenset(('browse','collect_metadata','store_raw','store_excerpt','index_fulltext','embed','send_to_model','redistribute','public_link'))
D8_COUNTS={'assessments':7,'audit_reviews':27,'authority':18,'claims':17,
 'communities':0,'conflicts':1,'editions':24,'evidence':17,
 'institutional_assertions':6,'locators':29,'passages':11,'relationships':15,
 'rights':216,'rights_overrides':27,'source_access_events':29,'sources':23,
 'unresolved_gaps':9}
D8_TABLES=('assessments','audit_reviews','authority','claims','communities','conflicts','editions','evidence','institutional_assertions','locators','passages','relationships','rights','rights_overrides','source_access_events','sources','unresolved_gaps')
ALLOWED_ATTRIBUTIONS=frozenset(('community_self_explanation','individual_opinion','external_critique','academic_interpretation','official_doctrine','scriptural_narrative','textual_narrative','unknown'))
MISSING=(None,'','UNKNOWN','unknown','pending')
TYPED={
 ('editions','source_id'):{'sources'},('locators','edition_id'):{'editions'},
 ('claims','community_id'):{'communities','authority_registry_traditions'},('claims','source_locator_id'):{'locators'},('claims','passage_ids'):{'passages'},
 ('assessments','target_community_id'):{'communities','authority_registry_traditions'},('assessments','locator_id'):{'locators'},
 ('authority','community_id'):{'communities','authority_registry_traditions'},('authority','source_locator_id'):{'locators'},('authority','source_locator_ids'):{'locators'},
 ('evidence','claim_id'):{'claims'},('evidence','locator_id'):{'locators'},
 ('rights','edition_id'):{'editions'},('rights','evidence_locator_id'):{'locators'},
 ('rights_overrides','baseline_right_id'):{'rights'},('rights_overrides','baseline_edition_id'):{'editions'},('rights_overrides','evidence_locator_id'):{'locators'},('rights_overrides','additional_evidence_locator_ids'):{'locators'},
 ('source_access_events','source_id'):{'sources'},('source_access_events','edition_id'):{'editions'},('source_access_events','source_locator_id'):{'locators'},
 ('audit_reviews','baseline_record_id'):{'claims','assessments'},('audit_reviews','locator_id'):{'locators'},
 ('institutional_assertions','community_id'):{'communities','authority_registry_traditions'},('institutional_assertions','locator_id'):{'locators'},
 ('conflicts','community_id'):{'communities','authority_registry_traditions'},('conflicts','fact_ids'):{'institutional_assertions'},
 ('relationships','subject_id'):{'claims','assessments'},('relationships','object_id'):{'claims','assessments','communities','authority_registry_traditions','sources','authority_documents'},('relationships','locator_id'):{'locators'},
 ('unresolved_gaps','source_locator_ids'):{'locators'},
}
MANDATORY={('editions','source_id'),('locators','edition_id'),('claims','source_locator_id'),('assessments','target_community_id'),('assessments','locator_id'),('evidence','claim_id'),('evidence','locator_id'),('rights','edition_id'),('rights_overrides','baseline_right_id'),('rights_overrides','baseline_edition_id'),('rights_overrides','evidence_locator_id'),('source_access_events','source_locator_id'),('audit_reviews','baseline_record_id'),('audit_reviews','locator_id'),('institutional_assertions','community_id'),('institutional_assertions','locator_id'),('relationships','subject_id'),('relationships','object_id'),('relationships','locator_id')}
FORBIDDEN={'raw_text','full_text','html_full_text','pdf_bytes','embedding','embeddings'}
RELATION_TYPES={
 'criticizes_community_position':({'claims','assessments'},{'communities','authority_registry_traditions'}),
 'criticizes_reported_position_of':({'claims','assessments'},{'communities','authority_registry_traditions'}),
 'published_review_criticizes_book_treatment':({'claims'},{'sources'}),
 **{name:({'claims'},{'claims'}) for name in (
  'contrasting_interpretation_on_shared_text','same_passage_research_not_direct_rebuttal',
  'possible_same_topic_criticism','academic_secondary_interpretation_of',
  'interpretive_contrast_candidate','shares_1950_edition_critique_topic',
  'critiques_group_argument_related_to','related_criticism_on_same_passage',
  'directly_rebuts','academic_analysis_of')},
}


def validate_d8(d8, prior, auxiliary=None, *, expected_counts=True):
 """Return (error code Counter, aggregate metrics) for D8 and known prior layers.

 ``prior`` maps layers (base,d5,d6,d7) to table dictionaries. Each table is a
 list of parsed ``{'value':dict,'line':int}`` rows. ``auxiliary`` optionally
 maps D8 report basename (without .jsonl) to rows. Caller verifies pinned ZIP
 and all nested manifests first. All output is aggregate and contains no IDs.
 """
 errors=Counter(); known={}; values={}
 for layer in ('base','d5','d6','d7','d8'):
  tables=d8 if layer=='d8' else prior.get(layer,{})
  for table,rows in tables.items():
   for item in rows:
    x=item.get('value')
    if not isinstance(x,dict):errors['invalid_record']+=1;continue
    ident=x.get('id')
    if ident is None and layer=='d5' and table=='audit_conflicts':continue
    if not isinstance(ident,str) or not ident.strip():errors['invalid_id']+=1;continue
    if ident in known:errors['duplicate_id']+=1;continue
    known[ident]=(layer,table);values[ident]=x
 for item in prior.get('d5',{}).get('authority_registries',[]):
  x=item['value'];ident=x.get('tradition_id')
  if isinstance(ident,str) and ident:
   if ident in known:errors['duplicate_tradition_alias']+=1
   else:known[ident]=('d5','authority_registry_traditions')
 if expected_counts:
  for table,count in D8_COUNTS.items():
   if len(d8.get(table,[]))!=count:errors['d8_count_mismatch']+=1
  for table in D8_TABLES:
   if table not in d8:errors['d8_record_file_missing']+=1
 reviewed=defaultdict(list)
 for table,rows in d8.items():
  for item in rows:
   x=item['value']
   if FORBIDDEN.intersection(x):errors['prohibited_content_field']+=1
   if x.get('independent_human_review') is True or x.get('scholarly_reviewed') is True or x.get('independent_review_status') in ('human_review_documented','scholarly_reviewed'):errors['unsupported_human_review']+=1
   if x.get('raw_text_stored') is True or x.get('raw_text_saved') is True or x.get('original_content_stored') is True:errors['raw_content_stored']+=1
   if x.get('formal_adoption') is True or x.get('authority_status')=='adoption_documented':errors['unreviewed_formal_adoption']+=1
   for field,raw in x.items():
    if field=='id' or not (field.endswith('_id') or field.endswith('_ids')):continue
    if field.endswith('_ids') and not isinstance(raw,list):errors['invalid_reference_array']+=1;continue
    for v in raw if isinstance(raw,list) else [raw]:
     if v in MISSING:
      if (table,field) in MANDATORY:errors['required_reference_missing']+=1
      continue
     if not isinstance(v,str) or v not in known:errors['unresolved_reference']+=1;continue
     target=known[v]; allowed=TYPED.get((table,field))
     if allowed is None and ('locator_id' in field or field.endswith('locator_ids')):allowed={'locators'}
     if allowed and target[1] not in allowed:errors['reference_wrong_type']+=1
   if table=='claims':
    if x.get('attribution_kind') not in ALLOWED_ATTRIBUTIONS:errors['invalid_attribution']+=1
    if x.get('attribution_kind')=='official_doctrine':errors['official_claim_requires_manual_review']+=1
    if not isinstance(x.get('passage_ids'),list):errors['invalid_passage_references']+=1
   if table=='relationships' and x.get('predicate') in ('directly_rebuts','rebuts') and x.get('status') in ('source_checked','verified') and not x.get('direct_relation_evidence'):
    errors['direct_rebuttal_evidence_missing']+=1
   if table=='relationships' and x.get('predicate') in RELATION_TYPES:
    subjects,objects=RELATION_TYPES[x['predicate']];subject=known.get(x.get('subject_id'));obj=known.get(x.get('object_id'))
    if (subject and subject[1] not in subjects) or (obj and obj[1] not in objects):errors['relation_direction_or_type_mismatch']+=1
   if table=='rights':
    decision=x.get('decision');decision=decision.lower() if isinstance(decision,str) else ''
    if decision not in ('unknown','conditional','allowed','prohibited'):errors['invalid_rights_decision']+=1
    if x.get('action') not in ACTIONS:errors['invalid_rights_action']+=1
    if decision in ('conditional','allowed') and (x.get('evidence_locator_id') in MISSING or not x.get('action_specific_basis')):errors['rights_evidence_missing']+=1
   if table=='evidence':
    claim=values.get(x.get('claim_id'))
    if claim and claim.get('source_locator_id')!=x.get('locator_id'):errors['evidence_claim_locator_mismatch']+=1
   if table=='rights_overrides':
    original=values.get(x.get('baseline_right_id'));loc=known.get(x.get('baseline_right_id'))
    if original is None or not loc or loc[0]!='d7' or loc[1]!='rights':errors['rights_override_not_d7']+=1
    elif (original.get('edition_id')!=x.get('baseline_edition_id') or original.get('action')!=x.get('action') or original.get('decision')!=x.get('previous_decision')):errors['rights_override_baseline_mismatch']+=1
    if x.get('original_baseline_mutated') is not False:errors['baseline_mutation_flag']+=1
    decision=x.get('new_decision');decision=decision.lower() if isinstance(decision,str) else ''
    if decision not in ('unknown','conditional','allowed','prohibited'):errors['invalid_rights_decision']+=1
    # Missing scope remains pending and grants nothing; it is not an archive
    # corruption and must not stop inspection of the pinned original.
   if table=='audit_reviews':
    target=x.get('baseline_record_id'); original=values.get(target);loc=known.get(target)
    if not loc or loc[0] not in ('d6','d7') or loc[1] not in ('claims','assessments'):errors['audit_target_invalid']+=1
    elif original is not None:
     a=original.get('source_verification');b=original.get('verification_status')
     if a is not None and b is not None and a!=b:errors['audit_prior_status_conflict']+=1
     status=a if a is not None else b
     if x.get('previous_verification_status')!=status:errors['audit_previous_status_changed']+=1
     reviewed[target].append(x)
   if table=='source_access_events':
    loc=values.get(x.get('source_locator_id')); edition=values.get(loc.get('edition_id')) if loc else None
    if x.get('edition_id') not in MISSING and (not loc or x.get('edition_id')!=loc.get('edition_id')):errors['access_edition_mismatch']+=1
    if x.get('source_id') not in MISSING and (not edition or x.get('source_id')!=edition.get('source_id')):errors['access_source_mismatch']+=1
 pairs=Counter((item['value'].get('edition_id'),item['value'].get('action')) for item in d8.get('rights',[]))
 for item in d8.get('editions',[]):
  for action in ACTIONS:
   if pairs[(item['value'].get('id'),action)]!=1:errors['rights_matrix_incomplete']+=1
 if auxiliary is not None:
  expected_targets={x['value']['id'] for t in ('claims','assessments') for x in prior.get('d7',{}).get(t,[])}
  seen=set()
  for item in auxiliary.get('D7_D8_REVIEW_CROSSWALK',[]):
   x=item['value'];target=x.get('baseline_id')
   if target not in expected_targets or target in seen:errors['crosswalk_target_invalid']+=1;continue
   seen.add(target)
   original=values[target];target_type=known[target][1]
   if x.get('baseline_table')!=target_type:errors['crosswalk_type_mismatch']+=1
   if x.get('baseline_locator_id')!=original.get('source_locator_id',original.get('locator_id')):errors['crosswalk_locator_mismatch']+=1
   eventids=[e.get('id') for e in reviewed[target]]
   if not isinstance(x.get('d8_review_event_ids'),list) or Counter(x['d8_review_event_ids'])!=Counter(eventids):errors['crosswalk_events_mismatch']+=1
   statuses=[e.get('observation_status') for e in reviewed[target]]
   if not isinstance(x.get('d8_observation_statuses'),list) or Counter(x['d8_observation_statuses'])!=Counter(statuses):errors['crosswalk_statuses_mismatch']+=1
   if x.get('d8_review_state')=='not_reviewed_this_gate' and eventids:errors['crosswalk_review_state_mismatch']+=1
   if x.get('d8_review_state')=='reviewed_this_gate' and not eventids:errors['crosswalk_review_state_mismatch']+=1
   if x.get('d8_review_state') not in ('reviewed_this_gate','not_reviewed_this_gate'):errors['crosswalk_review_state_unknown']+=1
  if seen!=expected_targets:errors['crosswalk_coverage_incomplete']+=1
  for table in ('SOURCE_ACCESS_INDEX','SOURCE_DUPLICATE_REVIEW'):
   expected=Counter(item['value'].get('id') for item in d8.get('sources',[]))
   actual=Counter(item['value'].get('source_id') for item in auxiliary.get(table,[]))
   if expected!=actual:errors['source_report_coverage_mismatch']+=1
  for item in auxiliary.get('SOURCE_ACCESS_INDEX',[]):
   x=item['value'];source=x.get('source_id')
   for field,kind in (('edition_ids','editions'),('locator_ids','locators'),('access_event_ids','source_access_events')):
    candidates=x.get(field)
    if not isinstance(candidates,list):errors['source_report_reference_array_invalid']+=1;continue
    for ident in candidates:
     info=known.get(ident);obj=values.get(ident)
     if not info or info[0]!='d8' or info[1]!=kind:errors['source_report_reference_invalid']+=1;continue
     if kind=='editions':edition=obj
     elif kind=='locators':edition=values.get(obj.get('edition_id'))
     else:
      locator=values.get(obj.get('source_locator_id'));edition=values.get(locator.get('edition_id')) if locator else None
     if not edition or edition.get('source_id')!=source:errors['source_report_source_mismatch']+=1
 metrics={'d8_counts':{k:len(v) for k,v in d8.items()},'audit_events':len(d8.get('audit_reviews',[])),
          'unique_audit_targets':sum(bool(v) for v in reviewed.values()),
          'claims_without_passage':sum(not x['value'].get('passage_ids') for x in d8.get('claims',[])),
          'unmapped_relation_predicates':sum(x['value'].get('predicate') not in RELATION_TYPES for x in d8.get('relationships',[])),
          'rights_overrides_pending_scope':sum(str(x['value'].get('new_decision','')).lower() in ('conditional','allowed') and (not x['value'].get('additional_evidence_locator_ids') or not x['value'].get('candidate_content_scope') or not x['value'].get('jurisdiction')) for x in d8.get('rights_overrides',[])),
          'unreviewed_is_not_rejected':True}
 return errors,metrics
