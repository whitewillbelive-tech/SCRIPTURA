"""Validate a frozen D-2 archive without executing it or printing its contents.

`validate_archive` is also usable by tests with explicit expected-* overrides.
CLI callers must never expose those overrides: the actual D-2 snapshot is pinned.
The returned records contain sensitive research metadata and MUST remain private.
"""
from __future__ import annotations

import collections
import hashlib
import io
import json
import re
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath

EXPECTED_SHA256 = 'c8b64b9144367a8526c77b121b3343f04a7c683276f9fd239b2cc51458589a47'
EXPECTED_SNAPSHOT = 'SCRIPTURA-D11-D2-20261105-v1'
EXPECTED_COUNTS = {'sources':96,'editions':97,'locators':131,'rights':873,'passages':75,'alignments':35,'agents':24,'affiliations':0,'claims':30,'evidence':30,'relations':2,'reviews':32}
TABLES = tuple(EXPECTED_COUNTS)
ACTIONS = ('browse','collect_metadata','store_raw','store_excerpt','index_fulltext','embed','send_to_model','redistribute','public_link')
REQUIRED = {
'sources':('id','title','kind','creator','url'), 'editions':('id','source_id','label','language','version_status'),
'locators':('id','edition_id','location','verification_status','checked_at'), 'rights':('id','edition_id','action','decision','checked_at','evidence_url'),
'passages':('id','corpus','work','reference_scheme','reference','coverage_status'), 'alignments':('id','from_passage_id','to_passage_id','alignment_type','review_status','locator_id'),
'agents':('id','name','kind'), 'affiliations':('id','agent_id','tradition','relation_kind','locator_id'),
'claims':('id','statement_ko','passage_ids','agent_id','attribution_kind','locator_id','review_status','scope_note'),
'evidence':('id','claim_id','role','locator_id','review_status','explanation_ko'),
'relations':('id','from_claim_id','to_claim_id','relation_type','locator_id','review_status','rationale_ko'),
'reviews':('id','target_type','target_id','reviewer','decision','reviewed_at','notes')}
ENUMS = {
('editions','version_status'):{'confirmed','partial','unknown'}, ('locators','verification_status'):{'unchecked','source_checked','edition_checked','disputed'},
('rights','action'):set(ACTIONS), ('rights','decision'):{'allowed','conditional','unknown','prohibited'},
('passages','coverage_status'):{'documented','partial','unknown','not_in_canon','not_in_edition'},
('agents','kind'):{'person','institution','collective','literary_voice'},
('claims','attribution_kind'):{'official_doctrine','institutional_statement','scholarly_interpretation','individual_opinion','reported_view','textual_narrative','community_explanation','external_criticism'},
('claims','review_status'):{'candidate','source_verified','scholarly_reviewed','disputed'},
('evidence','role'):{'supports','rebuts','counterexample','context','original_quote','translation_argument'},
('alignments','alignment_type'):{'equivalent_segment','overlapping','partial','addition','omission','uncertain'},
('relations','relation_type'):{'supports','contradicts','qualifies','rebuts','depends_on','historically_influenced_by'},
('affiliations','relation_kind'):{'self_identified','officially_affiliated','historically_attributed','reported_by_other','contested'},
('reviews','target_type'):{'source','edition','locator','rights','passage','alignment','agent','affiliation','claim','evidence','relation'},
('reviews','decision'):{'source_verified','scholarly_reviewed','approve_source','approve_scholarly','request_changes','reject','mark_disputed','candidate','pending'}}
for _table in ('evidence','relations','alignments'):
    ENUMS[(_table,'review_status')]={'proposed','verified','partial_pending','disputed'}
NULLABLE = {'checked_at','scope_note','notes','evidence_url','locator_id'}
REFERENCES = [('editions','source_id','sources',False,False),('locators','edition_id','editions',False,False),('rights','edition_id','editions',False,False),('alignments','from_passage_id','passages',False,False),('alignments','to_passage_id','passages',False,False),('alignments','locator_id','locators',False,True),('affiliations','agent_id','agents',False,False),('affiliations','locator_id','locators',False,True),('claims','agent_id','agents',False,False),('claims','locator_id','locators',False,False),('claims','passage_ids','passages',True,False),('evidence','claim_id','claims',False,False),('evidence','locator_id','locators',False,False),('relations','from_claim_id','claims',False,False),('relations','to_claim_id','claims',False,False),('relations','locator_id','locators',False,False)]
FORBIDDEN = {'raw_text','full_text','embedding','embeddings','html_full_text','pdf_bytes','raw_content','original_text','fulltext','text_chunks','quote','excerpt','transcript','full_quote','snippet','content','text','direct_quote','raw_html','full_body'}
URL = re.compile(r'^https?://[^\s/]+(?:/[^\s]*)?$', re.I)
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 128 * 1024 * 1024
MAX_ENTRY_BYTES = 32 * 1024 * 1024


def _valid_timestamp(value):
    if not isinstance(value,str) or not value.strip() or value != value.strip(): return False
    try:
        datetime.fromisoformat(value.replace('Z','+00:00'))
        return True
    except ValueError:
        return False


def _canonical(x):
    return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _json_loads(value):
    def unique_pairs(pairs):
        result={}
        for key,item in pairs:
            if key in result: raise ValueError('duplicate JSON key')
            result[key]=item
        return result
    def reject_constant(_): raise ValueError('invalid JSON constant')
    return json.loads(value, object_pairs_hook=unique_pairs, parse_constant=reject_constant)


def _synthetic(value):
    if isinstance(value,dict):
        return value.get('is_synthetic') is True or value.get('data_class') == 'synthetic' or any(_synthetic(v) for v in value.values())
    return isinstance(value,list) and any(_synthetic(v) for v in value)


def _forbidden(value):
    if isinstance(value, dict):
        return any(str(k).lower() in FORBIDDEN or _forbidden(v) for k,v in value.items())
    if isinstance(value, list):
        return any(_forbidden(v) for v in value)
    return False


def validate_archive(path, *, expected_sha256=EXPECTED_SHA256, expected_snapshot=EXPECTED_SNAPSHOT,
                     expected_counts=None, expected_manifest_count=65, allow_synthetic=False):
    """Return a safe aggregate report plus private in-memory source records.

    `status=fail` prohibits all staging. Rights decisions are not approvals. The
    hashes are over the exact original JSONL line bytes including newline if present.
    No row content, raw identifier, or source URL appears in the report.
    """
    counts_expected = EXPECTED_COUNTS if expected_counts is None else expected_counts
    errors = collections.Counter()
    quarantine_reasons = collections.Counter()
    records = {t: [] for t in TABLES}
    report = {'schema_version':'1.0', 'status':'fail', 'errors':{}, 'snapshot':None,
              'archive_sha256':None,'manifest_entries':0,'tables':{},'dispositions':{},
              'quarantine_reasons':{},'rights':{},'verification':{},'records':[], 'note':'Structural checks only; no academic, rights or human-review approval.'}
    def fail(code): errors[code] += 1
    def finish():
        report['errors'] = dict(sorted(errors.items()))
        report['status'] = 'pass' if not errors else 'fail'
        report['tables'] = {t:len(records[t]) for t in TABLES}
        return report, records
    try:
        path = Path(path)
        if path.stat().st_size > MAX_ARCHIVE_BYTES:
            fail('archive_too_large'); return finish()
        blob = path.read_bytes()
        report['archive_sha256'] = hashlib.sha256(blob).hexdigest()
        if report['archive_sha256'] != expected_sha256:
            fail('archive_sha256_mismatch'); return finish()
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            infos = z.infolist()
            names = [x.filename for x in infos]
            if len(names) != len(set(names)): fail('duplicate_archive_member')
            if len(infos) > 1000 or sum(x.file_size for x in infos) > MAX_UNCOMPRESSED_BYTES: fail('archive_uncompressed_limit')
            if any(x.file_size > MAX_ENTRY_BYTES for x in infos): fail('archive_entry_limit')
            if any(x.file_size > 1024 * 1024 and x.file_size > max(x.compress_size,1) * 200 for x in infos): fail('archive_compression_ratio_limit')
            if any(PurePosixPath(n).is_absolute() or '..' in PurePosixPath(n).parts or '\\' in n for n in names): fail('unsafe_archive_path')
            if errors: return finish()
            if z.testzip() is not None: fail('archive_crc_mismatch'); return finish()
            try: manifest = _json_loads(z.read('RUN_MANIFEST.json'))
            except (KeyError, ValueError, UnicodeError): fail('manifest_invalid'); return finish()
            if not isinstance(manifest,dict): fail('manifest_invalid'); return finish()
            snapshot=manifest.get('dataset_snapshot')
            if snapshot != expected_snapshot: fail('snapshot_mismatch')
            else: report['snapshot']=snapshot
            hashes=manifest.get('file_hashes')
            if not isinstance(hashes,list): fail('manifest_entries_invalid'); return finish()
            report['manifest_entries']=len(hashes)
            if len(hashes)!=expected_manifest_count: fail('manifest_entry_count')
            paths=set()
            for ent in hashes:
                if not isinstance(ent,dict): fail('manifest_entry_invalid'); continue
                name=ent.get('path'); checksum=ent.get('sha256'); size=ent.get('bytes')
                if not isinstance(name,str) or name in paths or name=='RUN_MANIFEST.json' or name not in names:
                    fail('manifest_path_invalid'); continue
                paths.add(name)
                try: content=z.read(name)
                except (KeyError,zipfile.BadZipFile,RuntimeError): fail('manifest_member_unreadable'); continue
                if not isinstance(checksum,str) or hashlib.sha256(content).hexdigest()!=checksum: fail('manifest_hash_mismatch')
                if not isinstance(size,int) or len(content)!=size: fail('manifest_size_mismatch')
            # Files omitted from the manifest undermine the snapshot's asserted coverage.
            actual_files={x.filename for x in infos if not x.is_dir()} - {'RUN_MANIFEST.json'}
            if actual_files != paths: fail('manifest_coverage_mismatch')
            if errors: return finish()
            chunks={}
            for group,prefix in (('base','d1_1/records/'),('delta','d2/records_delta/'),('merged','d2/records_merged/')):
                chunks[group]={}
                for table in TABLES:
                    name=prefix+table+'.jsonl'
                    if name not in paths: fail('record_file_missing'); continue
                    entries=[]
                    for number,line in enumerate(z.read(name).splitlines(keepends=True),1):
                        if not line.strip(): continue
                        try:
                            obj=_json_loads(line.decode('utf-8-sig'))
                        except (UnicodeError,ValueError,RecursionError): fail('record_json_invalid'); continue
                        if not isinstance(obj,dict): fail('record_not_object'); continue
                        entries.append({'data':obj,'row_number':number,'file':name,
                                        'sha256':hashlib.sha256(line).hexdigest(),
                                        'disposition':'quarantined','reasons':[],'rights':{}})
                    chunks[group][table]=entries
            if errors: return finish()
            for table in TABLES:
                merged=chunks['merged'][table]
                records[table]=merged
                d11_counts = manifest.get('d11_counts')
                d2_counts = manifest.get('d2_merged_counts')
                if not isinstance(d11_counts,dict) or d11_counts.get(table) != len(chunks['base'][table]): fail('manifest_baseline_count_mismatch')
                if not isinstance(d2_counts,dict) or d2_counts.get(table) != len(merged): fail('manifest_merged_count_mismatch')
                if len(merged)!=counts_expected.get(table): fail('record_count_mismatch')
                if collections.Counter(_canonical(r['data']) for r in chunks['base'][table]+chunks['delta'][table]) != collections.Counter(_canonical(r['data']) for r in merged): fail('baseline_delta_merge_mismatch')
    except (OSError,zipfile.BadZipFile,RuntimeError,ValueError,OverflowError):
        fail('archive_unreadable'); return finish()

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
    # Structural validity never means safe canonical promotion. Preserve original
    # values in private staging only after a separate, explicit human review.
    per_table={'sources':'metadata_only_review_required','editions':'edition_mapping_incomplete','locators':'edition_locator_mapping_required','rights':'action_rights_review_required','passages':'canon_scheme_mapping_required','alignments':'mapping_scope_unconfirmed','agents':'agent_kind_mapping_required','affiliations':'affiliation_review_required','claims':'claim_version_mapping_required','evidence':'evidence_mapping_required','relations':'relation_mapping_required','reviews':'historical_review_preservation_required'}
    for table,entries in records.items():
        for item in entries:
            reason=per_table[table];item['reasons']=[reason];quarantine_reasons[reason]+=1
            public_item={'table':table,'row_number':item['row_number'],'line_sha256':item['sha256'],
                         'disposition':item['disposition'],'reason_codes':item['reasons']}
            if table=='rights':
                x=item['data'];item['rights']={'action':x.get('action'),'decision':x.get('decision'),'effective_allowed':False,'reason':'independent_rights_review_required'}
                public_item.update({'action':x.get('action'),'decision':x.get('decision')})
            report['records'].append(public_item)
    report['dispositions']={'eligible':0,'quarantined':sum(len(x) for x in records.values())}
    report['quarantine_reasons']=dict(sorted(quarantine_reasons.items()))
    return finish()
