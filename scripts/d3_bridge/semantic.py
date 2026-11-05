"""D-3 record semantic checks derived from the established D-2 contract.

Does not access a database or output source records or identifiers.
"""
import collections
import re
from d2_bridge.validator import (TABLES,ACTIONS,REQUIRED,ENUMS,NULLABLE,REFERENCES,URL,
                                 _forbidden,_synthetic,_valid_timestamp)


def validate_semantics(records, *, allow_synthetic=False):
    errors=collections.Counter()
    report={'rights':{},'verification':{}}
    def fail(code): errors[code]+=1
    def finish(): return errors,report
    indexed={t:{} for t in TABLES}; seen=set()
    for table,entries in records.items():
        for item in entries:
            data=item['data']; key=data.get('id')
            if not isinstance(key,str) or not key.strip(): fail('record_id_invalid'); continue
            if key in seen: fail('record_id_duplicate')
            seen.add(key); indexed[table][key]=data
            for field in REQUIRED[table]:
                if field not in data: fail('record_required_field_missing')
                elif field not in NULLABLE and (data[field] is None or data[field]==[] or (isinstance(data[field],str) and not data[field].strip())): fail('record_required_field_empty')
                elif field=='passage_ids' and not isinstance(data[field],list): fail('record_field_type_invalid')
                elif field!='passage_ids' and data[field] is not None and not isinstance(data[field],str): fail('record_field_type_invalid')
            for (t,field),allowed in ENUMS.items():
                if t==table and (not isinstance(data.get(field),str) or data[field] not in allowed): fail('record_enum_invalid')
            if table=='sources' and data.get('doi') is not None:
                doi=data['doi']
                if not isinstance(doi,str) or (doi.strip() and not re.fullmatch(r'(?:doi:\s*|https?://(?:dx\.)?doi\.org/)?10\.\d{4,9}/\S+', doi.strip(), re.I)):
                    fail('doi_invalid')
            if _forbidden(data): fail('forbidden_content_field')
            if not allow_synthetic and _synthetic(data): fail('synthetic_research_mixture')
    if not seen: fail('empty_dataset')
    if errors: return finish()
    for table,field,target,multiple,nullable in REFERENCES:
        for item in records[table]:
            val=item['data'].get(field)
            if nullable and val is None: continue
            if multiple:
                if not isinstance(val,list) or not val: fail('reference_invalid'); continue
                values=val
            else: values=[val]
            for ref in values:
                if not isinstance(ref,str) or ref not in indexed[target]: fail('reference_missing')
    targets={'source':'sources','edition':'editions','locator':'locators','rights':'rights','passage':'passages','alignment':'alignments','agent':'agents','affiliation':'affiliations','claim':'claims','evidence':'evidence','relation':'relations'}
    for x in indexed['reviews'].values():
        target_type=x.get('target_type'); target_id=x.get('target_id')
        target=targets.get(target_type) if isinstance(target_type,str) else None
        if not target or not isinstance(target_id,str) or target_id not in indexed[target]: fail('review_target_missing')
        if not isinstance(x.get('reviewer'),str) or not x['reviewer'].strip() or not _valid_timestamp(x.get('reviewed_at')): fail('review_identity_or_time_missing')
    for x in indexed['locators'].values():
        if x.get('checked_at') is not None and not _valid_timestamp(x.get('checked_at')): fail('locator_date_invalid')
        if x.get('verification_status') in ('source_checked','edition_checked') and not _valid_timestamp(x.get('checked_at')): fail('checked_locator_date_missing')
    decisions={action:collections.Counter() for action in ACTIONS}; pairs=set()
    for x in indexed['rights'].values():
        action=x.get('action'); decision=x.get('decision'); edition=x.get('edition_id')
        if not isinstance(action,str) or not isinstance(edition,str): fail('rights_pair_invalid'); continue
        pair=(edition,action)
        if pair in pairs: fail('rights_action_duplicate')
        pairs.add(pair)
        if action in decisions and isinstance(decision,str): decisions[action][decision]+=1
        u=x.get('evidence_url')
        if u is None:
            if not x.get('evidence_missing_reason'): fail('rights_evidence_reason_missing')
            if decision=='allowed': fail('rights_allowed_without_evidence')
        elif not isinstance(u,str) or not URL.fullmatch(u): fail('rights_evidence_url_invalid')
        if x.get('checked_at') is not None and not _valid_timestamp(x.get('checked_at')): fail('rights_date_invalid')
        if decision=='allowed' and not _valid_timestamp(x.get('checked_at')): fail('rights_allowed_date_missing')
    for eid in indexed['editions']:
        for action in ACTIONS:
            if (eid,action) not in pairs: fail('rights_action_missing')
    report['rights']={a:{'decisions':dict(sorted(decisions[a].items())), 'blocked':sum(decisions[a].values()),
                          'reason':'independent_rights_review_required', 'effective_allowed':0} for a in ACTIONS}
    # Preserve source history as aggregate observations, never as a promotion.
    report['verification']={
        'claims_by_review_status':dict(sorted(collections.Counter(x['review_status'] for x in indexed['claims'].values()).items())),
        'evidence_by_review_status':dict(sorted(collections.Counter(x['review_status'] for x in indexed['evidence'].values()).items())),
        'relations_by_review_status':dict(sorted(collections.Counter(x['review_status'] for x in indexed['relations'].values()).items())),
        'alignments_by_review_status':dict(sorted(collections.Counter(x['review_status'] for x in indexed['alignments'].values()).items())),
        'locators_by_verification_status':dict(sorted(collections.Counter(x['verification_status'] for x in indexed['locators'].values()).items())),
        'review_events_by_decision':dict(sorted(collections.Counter(x['decision'] for x in indexed['reviews'].values()).items())),
        'independent_human_scholarly_review_events':sum(1 for x in indexed['reviews'].values() if x.get('decision')=='scholarly_reviewed' and x.get('reviewer_type')=='independent_human' and bool(x.get('methodology'))),
        'statuses_automatically_promoted':0,
    }
    report['verification']['claims_by_review_status'].setdefault('scholarly_reviewed', 0)
    report['verification']['review_events_by_decision'].setdefault('scholarly_reviewed', 0)
    report['verification']['review_events_by_decision'].setdefault('approve_scholarly', 0)
    checked={'source_checked','edition_checked'}
    def locator_ok(id):
        v=indexed['locators'].get(id,{}) if isinstance(id,str) else {}
        location=v.get('location'); date=v.get('checked_at')
        return (v.get('verification_status') in checked and isinstance(location,str) and bool(location.strip())
                and _valid_timestamp(date))
    # Build support indexes once: a large batch with many claims must not run
    # a quadratic scan of evidence and review events for every claim.
    verified_evidence_claims={e.get('claim_id') for e in indexed['evidence'].values()
                              if isinstance(e.get('claim_id'),str) and e.get('review_status')=='verified' and locator_ok(e.get('locator_id'))}
    source_reviewed_claims={r.get('target_id') for r in indexed['reviews'].values()
                            if r.get('target_type')=='claim' and isinstance(r.get('target_id'),str) and r.get('decision') in ('source_verified','scholarly_reviewed')}
    scholarly_reviewed_claims={r.get('target_id') for r in indexed['reviews'].values()
                               if r.get('target_type')=='claim' and isinstance(r.get('target_id'),str) and r.get('decision')=='scholarly_reviewed' and r.get('reviewer_type')=='independent_human' and r.get('methodology')}
    for key,x in indexed['claims'].items():
        aid=x.get('agent_id'); agent=indexed['agents'].get(aid,{}) if isinstance(aid,str) else {}
        typ=x.get('attribution_kind')
        if (typ=='textual_narrative') != (agent.get('kind')=='literary_voice'): fail('narrative_voice_mismatch')
        if typ=='official_doctrine' and agent.get('kind') not in ('institution','collective'): fail('official_doctrine_not_institutional')
        if typ=='official_doctrine' and not locator_ok(x.get('official_basis_locator_id')): fail('official_basis_unverified')
        if x.get('review_status') in ('source_verified','scholarly_reviewed'):
            if not locator_ok(x.get('locator_id')): fail('verified_claim_locator_missing')
            if key not in verified_evidence_claims: fail('verified_claim_evidence_missing')
            if key not in source_reviewed_claims: fail('verified_claim_review_missing')
        if x.get('review_status')=='scholarly_reviewed' and key not in scholarly_reviewed_claims: fail('independent_review_missing')
    for table in ('alignments','relations','evidence'):
        for x in indexed[table].values():
            if x.get('review_status')=='verified' and not locator_ok(x.get('locator_id')): fail('verified_relation_locator_missing')
    dois=set()
    for x in indexed['sources'].values():
        doi=x.get('doi')
        if isinstance(doi,str) and doi.strip():
            normalized=re.sub(r'^(?:doi:\s*|https?://(?:dx\.)?doi\.org/)', '', doi.strip().lower()).strip()
            if normalized in dois: fail('duplicate_doi')
            dois.add(normalized)
    return errors,report
