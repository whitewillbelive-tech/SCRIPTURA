"""Pinned D4 read-only authority evidence gap report; records never leave memory."""
from __future__ import annotations
import collections
import csv
import hashlib
import io
import re
import zipfile
from pathlib import Path, PurePosixPath
from d2_bridge.validator import TABLES, URL, _json_loads, _canonical, _forbidden, _synthetic, _valid_timestamp
from d3_bridge.semantic import validate_semantics

D4_SHA='05ab5bdf3fc258f39b926257c771ef4a17138355aa072cb8bc97c56387999beb'
D3_SHA='baf206d2846544f1e1bb20622ac10c557394b71aa41cfd6e2be5bbafade347be'
D2_SHA='c8b64b9144367a8526c77b121b3343f04a7c683276f9fd239b2cc51458589a47'
COUNTS={'sources':215,'editions':217,'locators':266,'rights':1953,'passages':92,'alignments':41,'agents':52,'affiliations':12,'claims':78,'evidence':78,'relations':2,'reviews':98}
RIGHT_FIELDS={'origin','id','source_id','source_title','edition_id','edition_label','action','decision','purpose','territory','period','rights_holder','exceptions','attribution_requirements','checked_at','evidence_url','evidence_missing_reason','license_statement','scope_note'}
MAX_ARCHIVE=64*1024*1024
MAX_TOTAL=128*1024*1024
MAX_ENTRY=32*1024*1024


def _open_safe(blob, errors):
    z=zipfile.ZipFile(io.BytesIO(blob)); infos=z.infolist();names=[i.filename for i in infos]
    if (len(infos)>1000 or len(names)!=len(set(names)) or sum(i.file_size for i in infos)>MAX_TOTAL or
        any(i.file_size>MAX_ENTRY or (i.file_size>1048576 and i.file_size>max(i.compress_size,1)*200) for i in infos) or
        any(PurePosixPath(n).is_absolute() or '..' in PurePosixPath(n).parts or '\\' in n for n in names)):
        errors['unsafe_archive']+=1;z.close();return None
    if z.testzip() is not None:errors['crc_mismatch']+=1;z.close();return None
    return z


def _manifest(z, expected_count, errors):
    name='logs/FILE_SHA256SUMS.txt';members={x.filename for x in z.infolist() if not x.is_dir()}
    try: lines=z.read(name).decode('utf-8').splitlines()
    except (KeyError,UnicodeError):errors['manifest_invalid']+=1;return 0
    if len(lines)!=expected_count:errors['manifest_count_mismatch']+=1
    seen=set()
    for line in lines:
        m=re.fullmatch(r'([0-9a-f]{64})  (.+)',line)
        if not m:errors['manifest_entry_invalid']+=1;continue
        digest,path=m.groups()
        if path==name or path in seen or path not in members:errors['manifest_member_invalid']+=1;continue
        seen.add(path)
        if hashlib.sha256(z.read(path)).hexdigest()!=digest:errors['manifest_hash_mismatch']+=1
    if members-{name}!=seen:errors['manifest_coverage_mismatch']+=1
    return len(lines)


def _rows(z,name,errors):
    try: raw=z.read(name)
    except KeyError:errors['record_file_missing']+=1;return []
    out=[]
    for num,line in enumerate(raw.splitlines(keepends=True),1):
        if not line.strip():continue
        try: item=_json_loads(line.decode('utf-8-sig'))
        except (ValueError,UnicodeError,RecursionError):errors['record_json_invalid']+=1;continue
        if not isinstance(item,dict):errors['record_not_object']+=1;continue
        out.append({'data':item,'row_number':num,'file':name,'sha256':hashlib.sha256(line).hexdigest()})
    return out


def _rights_csv(z,records,baseline_ids,errors):
    try:
        reader=csv.DictReader(io.StringIO(z.read('d4/D4_RIGHTS_MATRIX.csv').decode('utf-8-sig'),newline=''))
        headers=reader.fieldnames
        if not headers or len(headers)!=len(set(headers)) or set(headers)!=RIGHT_FIELDS:errors['rights_csv_header_invalid']+=1;return
        csvrows=list(reader)
    except (KeyError,UnicodeError,csv.Error):errors['rights_csv_invalid']+=1;return
    rights={e['data']['id']:e['data'] for e in records['rights']}; editions={e['data']['id']:e['data'] for e in records['editions']};sources={e['data']['id']:e['data'] for e in records['sources']}
    if len(csvrows)!=len(rights):errors['rights_csv_count_mismatch']+=1
    seen=set()
    for row in csvrows:
        if None in row or any(v is None for v in row.values()):errors['rights_csv_row_malformed']+=1;continue
        rid=row.get('id');value=rights.get(rid)
        if not value or rid in seen:errors['rights_csv_id_invalid']+=1;continue
        seen.add(rid);edition=editions.get(value.get('edition_id'),{});source=sources.get(edition.get('source_id'),{})
        if row.get('origin') != ('D3' if rid in baseline_ids else 'D4') or row.get('source_id')!=edition.get('source_id') or row.get('source_title')!=source.get('title') or row.get('edition_label')!=edition.get('label'):errors['rights_csv_provenance_mismatch']+=1
        for key in RIGHT_FIELDS-{'origin','id','source_id','source_title','edition_label'}:
            expected=value.get(key);expected='' if expected is None else str(expected)
            if row.get(key)!=expected:errors['rights_csv_mismatch']+=1


def inspect_archive(path, *, expected_sha256=D4_SHA, expected_d3_sha256=D3_SHA, expected_d2_sha256=D2_SHA,
                    expected_counts=None, expected_manifest_count=72, expected_d3_manifest_count=69,
                    allow_synthetic=False):
    """Inspect frozen D4; test-only pins are not exposed by public CLI.

    All report fields are hashes, enum counts or fixed codes. No record values,
    identifiers, source URLs or contents are emitted or persisted.
    """
    errors=collections.Counter();counts=COUNTS if expected_counts is None else expected_counts
    report={'schema_version':'i2-d4-1','status':'fail','errors':{},'input_sha256':None,'d3_sha256':None,'d2_sha256':None,'manifest_entries':0,'tables':{},'rights':{},'claims':{},'authority_gaps':{},'quarantine':{},'database_write':False,'canonical_promotion':False}
    records={t:[] for t in TABLES}
    def finish():
        report['errors']=dict(sorted(errors.items()));report['status']='fail' if errors else 'pass';report['tables']={t:len(records[t]) for t in TABLES};return report
    try:
        path=Path(path)
        if path.stat().st_size>MAX_ARCHIVE:errors['archive_too_large']+=1;return finish()
        blob=path.read_bytes();report['input_sha256']=hashlib.sha256(blob).hexdigest()
        if report['input_sha256']!=expected_sha256:errors['archive_sha256_mismatch']+=1;return finish()
        z=_open_safe(blob,errors)
        if z is None:return finish()
        with z:
            report['manifest_entries']=_manifest(z,expected_manifest_count,errors)
            if errors:return finish()
            try: base=z.read('baseline/SCRIPTURA_D3_DATA_RESEARCH.zip')
            except KeyError:errors['baseline_archive_missing']+=1;return finish()
            report['d3_sha256']=hashlib.sha256(base).hexdigest()
            if report['d3_sha256']!=expected_d3_sha256:errors['baseline_sha256_mismatch']+=1;return finish()
            nested=_open_safe(base,errors)
            if nested is None:return finish()
            with nested:
                _manifest(nested,expected_d3_manifest_count,errors)
                try: d2=nested.read('baseline/SCRIPTURA_D11_D2_RESEARCH.zip')
                except KeyError:errors['d2_archive_missing']+=1;return finish()
                report['d2_sha256']=hashlib.sha256(d2).hexdigest()
                if report['d2_sha256']!=expected_d2_sha256:errors['d2_sha256_mismatch']+=1;return finish()
                d2zip=_open_safe(d2,errors)
                if d2zip is None:return finish()
                d2zip.close()
                baseline={}
                for t in TABLES:
                    b=f'baseline/records/{t}.jsonl';prev=f'd3/records_merged/{t}.jsonl'
                    try:
                        if z.read(b)!=nested.read(prev):errors['baseline_records_changed']+=1
                    except KeyError:errors['baseline_record_missing']+=1;continue
                    baseline[t]=_rows(z,b,errors);delta=_rows(z,f'd4/records_delta/{t}.jsonl',errors);merged=_rows(z,f'd4/records_merged/{t}.jsonl',errors);records[t]=merged
                    if len(merged)!=counts.get(t):errors['record_count_mismatch']+=1
                    if collections.Counter(_canonical(x['data']) for x in baseline[t]+delta)!=collections.Counter(_canonical(x['data']) for x in merged):errors['baseline_delta_merge_mismatch']+=1
                try:
                    if z.read('baseline/bibliographic_edges.jsonl')!=nested.read('d3/graph/bibliographic_edges.jsonl'):errors['bibliography_baseline_changed']+=1
                except KeyError:errors['bibliography_baseline_missing']+=1
            if errors:return finish()
            sem_errors,facts=validate_semantics(records,allow_synthetic=allow_synthetic);errors.update(sem_errors)
            if errors:return finish()
            _rights_csv(z,records,{x['data']['id'] for x in baseline['rights']},errors)
            b=_rows(z,'baseline/bibliographic_edges.jsonl',errors);d=_rows(z,'d4/graph/bibliographic_edges_delta.jsonl',errors);m=_rows(z,'d4/graph/bibliographic_edges_merged.jsonl',errors)
            if collections.Counter(_canonical(x['data']) for x in b+d)!=collections.Counter(_canonical(x['data']) for x in m):errors['bibliography_merge_mismatch']+=1
            if expected_counts is None and len(m)!=12:errors['bibliography_count_mismatch']+=1
            source_ids={x['data']['id'] for x in records['sources']}; locators={x['data']['id']:x['data'] for x in records['locators']}; editions={x['data']['id']:x['data'] for x in records['editions']}
            known_ids={x['data']['id'] for t in TABLES for x in records[t]}
            bib_ids=set(); bib_date_missing=0; bib_findings=[]
            for row in m:
                x=row['data'];rid=x.get('id');a=x.get('from_source_id');b_id=x.get('to_source_id');loc=x.get('locator_id')
                if _forbidden(x) or (not allow_synthetic and _synthetic(x)):errors['bibliography_forbidden_content']+=1
                if not isinstance(rid,str) or not rid.strip() or rid in bib_ids or rid in known_ids:errors['bibliography_id_invalid']+=1
                else:bib_ids.add(rid)
                if a not in source_ids or b_id not in source_ids or not isinstance(loc,str) or loc not in locators:errors['bibliography_reference_missing']+=1;continue
                if editions.get(locators[loc].get('edition_id'),{}).get('source_id')!=a:errors['bibliography_locator_source_mismatch']+=1
                if x.get('relation_type')!='bibliographic_citation':errors['bibliography_type_invalid']+=1
                status=x.get('review_status')
                if status not in ('source_checked','partial_pending','candidate','disputed'):errors['bibliography_status_invalid']+=1
                if status=='source_checked':
                    locator=locators[loc]
                    if locator.get('verification_status') not in ('source_checked','edition_checked') or not _valid_timestamp(locator.get('checked_at')) or not isinstance(locator.get('location'),str) or not locator['location'].strip():errors['bibliography_unchecked_locator']+=1
                    if not _valid_timestamp(x.get('checked_at')):bib_date_missing+=1
                if not isinstance(x.get('relation_scope'),str) or not x['relation_scope'].strip():errors['bibliography_scope_missing']+=1
                reasons=['bibliographic_citation_is_not_argument_support']
                if status=='source_checked' and not _valid_timestamp(x.get('checked_at')):reasons.append('edge_checked_date_missing')
                bib_findings.append({'row_number':row['row_number'],'line_sha256':row['sha256'],'disposition':'quarantined','reason_codes':reasons})
            report['bibliographic_records']=len(m)
            report['bibliography']={'input_status_only':True,'source_checked_without_edge_date':bib_date_missing,'claim_relation_conversion':False,'records':bib_findings}
            coverage=_rows(z,'d4/coverage/CANON_COVERAGE_D4.jsonl',errors)
            if expected_counts is None and len(coverage)!=80:errors['coverage_count_mismatch']+=1
            try:
                reader=csv.DictReader(io.StringIO(z.read('d4/coverage/CANON_COVERAGE_D4.csv').decode('utf-8-sig'),newline=''));head=reader.fieldnames
                expected_headers={'id','work_label','opc_wcf_listing_status','usccb_bible_listing_status','chabad_tanakh_listing_status','chabad_group','oca_institutional_explanation_status','d3_merged_passage_records','d3_merged_claim_links','d3_address_coverage','d4_merged_passage_records','d4_merged_claim_links','d4_address_coverage','d4_coverage_note'}
                if not head or len(head)!=len(set(head)) or set(head)!=expected_headers:errors['coverage_csv_header_invalid']+=1
                csvrows=list(reader)
            except (KeyError,UnicodeError,csv.Error):errors['coverage_csv_invalid']+=1;csvrows=[]
            if len(csvrows)!=len(coverage):errors['coverage_csv_count_mismatch']+=1
            for csvrow,item in zip(csvrows,coverage):
                if None in csvrow or any(v is None for v in csvrow.values()) or any(k not in item['data'] or ('' if item['data'][k] is None else str(item['data'][k]))!=v for k,v in csvrow.items()):errors['coverage_csv_mismatch']+=1
            def work_key(value):
                if not isinstance(value,str):return ''
                name=value.strip().casefold()
                return 'psalm' if name in ('psalm','psalms') else name
            def work_counts(dataset):
                pid={x['data']['id']:work_key(x['data'].get('work')) for x in dataset['passages']}
                pcounts=collections.Counter(pid.values());ccounts=collections.Counter()
                for row in dataset['claims']:
                    for pid_value in row['data'].get('passage_ids',[]):
                        if pid_value in pid:ccounts[pid[pid_value]]+=1
                return pcounts,ccounts
            base_p,base_c=work_counts(baseline); merged_p,merged_c=work_counts(records)
            known_ids |= bib_ids
            seen_coverage=set();seen_work=set()
            coverage_enums={'opc_wcf_listing_status':{'listed','not_in_66_list'}, 'usccb_bible_listing_status':{'listed','not_in_usccb_73_list','included_within_book'}, 'chabad_tanakh_listing_status':{'listed','not_in_chabad_24_list','outside_tanakh_corpus'}, 'oca_institutional_explanation_status':{'not_checked','institutional_explanation_included'}}
            for entry in coverage:
                x=entry['data'];cid=x.get('id');work=work_key(x.get('work_label'))
                if _forbidden(x) or (not allow_synthetic and _synthetic(x)):errors['coverage_forbidden_content']+=1
                if not isinstance(cid,str) or not cid.strip() or cid in known_ids or cid in seen_coverage:errors['coverage_id_invalid']+=1
                else:seen_coverage.add(cid)
                if not work or work in seen_work:errors['coverage_work_invalid']+=1
                seen_work.add(work)
                for field,expected in (('d3_merged_passage_records',base_p[work]),('d3_merged_claim_links',base_c[work]),('d4_merged_passage_records',merged_p[work]),('d4_merged_claim_links',merged_c[work])):
                    if not isinstance(x.get(field),int) or isinstance(x.get(field),bool) or x[field]!=expected:errors['coverage_work_count_mismatch']+=1
                for field,allowed in coverage_enums.items():
                    if x.get(field) not in allowed:errors['coverage_status_invalid']+=1
                citations=x.get('citation_sources')
                if not isinstance(citations,dict) or not citations or any(not isinstance(k,str) or not isinstance(v,str) or not URL.fullmatch(v) for k,v in citations.items()):errors['coverage_source_invalid']+=1
                if not _valid_timestamp(x.get('checked_at')):errors['coverage_date_invalid']+=1
                if x.get('d4_address_coverage') not in ('partial','not_recorded') or (x.get('d4_address_coverage')=='partial') != (merged_p[work]>0):errors['coverage_status_invalid']+=1
            report['coverage_rows']=len(coverage)
            report['coverage']={'scope':'comparison units only, not proof of canonical identity or theological agreement','address_status_counts':dict(sorted(collections.Counter(x['data'].get('d4_address_coverage') for x in coverage if isinstance(x['data'].get('d4_address_coverage'),str)).items()))}
            event_paths={'source_access':'d4/SOURCE_ACCESS_LOG.jsonl','citation_access':'d4/graph/CITATION_ACCESS_EVENTS.jsonl','doi_access':'d4/graph/DOI_ACCESS_EVENTS.jsonl','argument_observation':'d4/graph/D4_ARGUMENT_OBSERVATIONS.jsonl'}
            events={k:_rows(z,v,errors) for k,v in event_paths.items()}
            expected_event_counts={'source_access':36,'citation_access':4,'doi_access':6,'argument_observation':1}
            if expected_counts is None:
                for name,amount in expected_event_counts.items():
                    if len(events[name])!=amount:errors['event_count_mismatch']+=1
            event_ids=set(); all_seen=known_ids|seen_coverage
            baseline_source_ids={x['data']['id'] for x in baseline['sources']}; baseline_bib_ids={x['data']['id'] for x in b}
            claim_ids={x['data']['id'] for x in records['claims']};passages_by_id={x['data']['id']:x['data'] for x in records['passages']};passage_ids=set(passages_by_id)
            claim_links=collections.Counter(p for entry in records['claims'] for p in entry['data'].get('passage_ids',[]))
            for name,items in events.items():
                for item in items:
                    x=item['data'];rid=x.get('id')
                    if not isinstance(rid,str) or not rid.strip() or rid in all_seen or rid in event_ids:errors['event_id_invalid']+=1
                    else:event_ids.add(rid)
                    if _forbidden(x) or (not allow_synthetic and _synthetic(x)):errors['event_forbidden_content']+=1
                    if not _valid_timestamp(x.get('observed_at')):errors['event_observation_date_invalid']+=1
                    if name=='source_access':
                        refs=x.get('locators')
                        if x.get('source_id') not in source_ids or ('edition_id' in x and x['edition_id'] not in editions) or not isinstance(refs,list) or any(not isinstance(v,str) or v not in locators for v in refs):errors['source_access_reference_invalid']+=1
                        if isinstance(refs,list) and isinstance(x.get('source_id'),str) and any(isinstance(v,str) and v in locators and editions.get(locators[v].get('edition_id'),{}).get('source_id')!=x['source_id'] for v in refs):errors['source_access_provenance_mismatch']+=1
                        if isinstance(x.get('edition_id'),str) and x['edition_id'] in editions and editions[x['edition_id']].get('source_id')!=x.get('source_id'):errors['source_access_provenance_mismatch']+=1
                        if type(x.get('full_text_persisted_bytes')) is not int or x['full_text_persisted_bytes']!=0:errors['source_access_raw_storage_reported']+=1
                    if name=='citation_access' and (x.get('baseline_edge_id') not in baseline_bib_ids or x.get('changes_baseline') is not False or x.get('independent_human_review') is not False):errors['citation_access_event_invalid']+=1
                    if name=='doi_access' and (x.get('baseline_source_id') not in baseline_source_ids or x.get('changes_baseline') is not False or x.get('scholarly_reviewed') is not False or type(x.get('full_text_acquired_bytes')) is not int or x['full_text_acquired_bytes']!=0):errors['doi_access_event_invalid']+=1
                    if name=='argument_observation' and (x.get('speaker_claim_id') not in claim_ids or x.get('locator_id') not in locators or (x.get('target_claim_id') is not None and x.get('target_claim_id') not in claim_ids)):errors['argument_observation_reference_invalid']+=1
            try:
                unit_data=_json_loads(z.read('d4/coverage/D4_RESEARCH_UNIT_COVERAGE.json').decode('utf-8-sig'))
                unit_reader=csv.DictReader(io.StringIO(z.read('d4/coverage/D4_RESEARCH_UNIT_COVERAGE.csv').decode('utf-8-sig'),newline=''))
                unit_headers={'passage_id','work','reference','claim_count','context_count','perspective_contexts'}
                if not unit_reader.fieldnames or len(unit_reader.fieldnames)!=len(set(unit_reader.fieldnames)) or set(unit_reader.fieldnames)!=unit_headers:errors['research_units_header_invalid']+=1
                unit_csv=list(unit_reader)
                if not isinstance(unit_data,list) or any(not isinstance(x,dict) for x in unit_data):errors['research_units_invalid']+=1;unit_data=[]
            except (KeyError,ValueError,UnicodeError,csv.Error):errors['research_units_invalid']+=1;unit_data=[];unit_csv=[]
            if len(unit_data)!=len(unit_csv) or (expected_counts is None and len(unit_data)!=11):errors['research_units_count_mismatch']+=1
            seen_unit=set()
            for x,row in zip(unit_data,unit_csv):
                pid=x.get('passage_id');contexts=x.get('perspective_contexts')
                if not isinstance(pid,str) or pid not in passage_ids or pid in seen_unit:errors['research_unit_reference_invalid']+=1
                else:seen_unit.add(pid)
                if not isinstance(contexts,list) or any(not isinstance(v,str) or not v.strip() for v in contexts) or type(x.get('context_count')) is not int or x['context_count']!=len(contexts):errors['research_unit_context_invalid']+=1
                elif row.get('perspective_contexts')!=' | '.join(contexts):errors['research_unit_csv_mismatch']+=1
                if isinstance(pid,str) and pid in passage_ids:
                    passage=passages_by_id[pid]
                    if x.get('work')!=passage.get('work') or x.get('reference')!=passage.get('reference') or type(x.get('claim_count')) is not int or x['claim_count']!=claim_links[pid]:errors['research_unit_count_or_passage_mismatch']+=1
                if None in row or any(v is None for v in row.values()) or any(row.get(k)!=str(x.get(k)) for k in ('passage_id','work','reference','claim_count','context_count')):errors['research_unit_csv_mismatch']+=1
            report['additional_records']={k:len(v) for k,v in events.items()}|{'research_units':len(unit_data)}
    except (OSError,zipfile.BadZipFile,RuntimeError,ValueError,OverflowError,RecursionError,KeyError,TypeError):
        errors['archive_unreadable']+=1;return finish()
    if errors:return finish()
    report['checks']={'d4_manifest': 'pass', 'nested_d3_manifest': 'pass', 'd3_d2_archive_pins': 'pass', 'baseline_delta_merged': 'pass', 'row_identity_and_foreign_keys': 'pass', 'rights_matrix_consistency': 'pass', 'bibliography_separate': 'pass', 'coverage_per_work_and_csv': 'pass'}
    report['rights']=facts['rights']; report['source_verification']=facts['verification']
    claimrows=records['claims']; axes=('quotation_status','authority_status','argument_status','independent_review_status')
    gapkeys=('exact_locator','document_issuer','tradition','jurisdiction','published_or_revised','applicable_period','language_and_edition','original_verification_path','formal_adoption_document')
    gaps=collections.Counter(); findings=[]
    for entry in claimrows:
        c=entry['data'];loc=locators.get(c.get('locator_id'),{}); edition=editions.get(loc.get('edition_id'),{});source=next((x['data'] for x in records['sources'] if x['data']['id']==edition.get('source_id')), {})
        # Presence is not proof. Explicitly absent or unverified adoption is always insufficient.
        missing=[]
        if not isinstance(loc.get('location'),str) or not loc['location'].strip() or loc.get('verification_status') not in ('source_checked','edition_checked') or not loc.get('checked_at'):missing.append('exact_locator')
        if not c.get('document_issuer'):missing.append('document_issuer')
        if not c.get('tradition'):missing.append('tradition')
        if not c.get('jurisdiction'):missing.append('jurisdiction')
        if not (c.get('published_at') or c.get('revised_at') or source.get('publication_date') or source.get('publication_year')):missing.append('published_or_revised')
        if not (c.get('valid_from') and c.get('valid_to')):missing.append('applicable_period')
        if not (edition.get('language') and edition.get('label') and edition.get('version_status')=='confirmed'):missing.append('language_and_edition')
        if not c.get('original_verification_path'):missing.append('original_verification_path')
        if not (c.get('official_adoption_evidence') and c.get('official_basis_locator_id')):missing.append('formal_adoption_document')
        gaps.update(missing)
        findings.append({'table':'claims','row_number':entry['row_number'],'line_sha256':entry['sha256'],'result':'insufficient_evidence','reason_codes':missing or ['independent_authority_review_required']})
    report['claims']={'total':len(claimrows),'original_status':facts['verification']['claims_by_review_status'],'raw_attribution_kind_counts':dict(sorted(collections.Counter(x['data']['attribution_kind'] for x in claimrows).items())),'source_verified_is_not_adoption_or_scholarly_review':True,'automatic_authority_adoptions':0,'automatic_scholarly_promotions':0}
    report['authority_gaps']={'scope':'Contract-field presence only; related source metadata may exist but has not been mapped or independently verified. Missing fields do not prove evidence does not exist. No formal adoption inferred; all D4 claims remain unapproved and quarantined.','axis_absent_or_empty':{axis:sum(not isinstance(x['data'].get(axis),str) or not x['data'][axis].strip() for x in claimrows) for axis in axes},'missing_fields':{key:gaps[key] for key in gapkeys},'insufficient_evidence':len(claimrows),'records':findings}
    primary=sum(len(records[t]) for t in TABLES); auxiliary=len(m)+len(coverage)+sum(len(v) for v in events.values())+len(unit_data)
    report['quarantine']={'eligible':0,'quarantined':primary+auxiliary,'primary_records':primary,'auxiliary_records':auxiliary,'reason':'research data is read-only and requires independent authority/rights review'}
    return finish()
