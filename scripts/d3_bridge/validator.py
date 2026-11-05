"""Pinned D-3 read-only reception validation; source records stay private in memory."""
from __future__ import annotations
import collections
import csv
import hashlib
import io
import re
import zipfile
from pathlib import Path, PurePosixPath
from d2_bridge.validator import TABLES, ACTIONS, URL, _json_loads, _canonical, _valid_timestamp, _forbidden, _synthetic
from .semantic import validate_semantics

EXPECTED_SHA256='baf206d2846544f1e1bb20622ac10c557394b71aa41cfd6e2be5bbafade347be'
D2_SHA256='c8b64b9144367a8526c77b121b3343f04a7c683276f9fd239b2cc51458589a47'
EXPECTED_COUNTS={'sources':180,'editions':182,'locators':226,'rights':1638,'passages':79,'alignments':39,'agents':32,'affiliations':12,'claims':40,'evidence':40,'relations':2,'reviews':58}
AUXILIARY={'bibliographic_edges':11,'coverage':80}
PATHS={'bibliographic_edges':'d3/graph/bibliographic_edges.jsonl','coverage':'d3/coverage/CANON_COVERAGE_D3_FINAL.jsonl'}
MAX_ARCHIVE_BYTES=64*1024*1024
MAX_UNCOMPRESSED_BYTES=128*1024*1024
MAX_ENTRY_BYTES=32*1024*1024


def validate_archive(path, *, expected_sha256=EXPECTED_SHA256, expected_baseline_sha256=D2_SHA256,
                     expected_counts=None, expected_manifest_count=69, expected_auxiliary_counts=None,
                     allow_synthetic=False):
    """Return safe hash/aggregate report and PRIVATE record objects (never log records).

    Override arguments are for synthetic tests only. Public CLI must use fixed pins.
    """
    expected_counts = EXPECTED_COUNTS if expected_counts is None else expected_counts
    expected_auxiliary_counts = AUXILIARY if expected_auxiliary_counts is None else expected_auxiliary_counts
    records={t:[] for t in (*TABLES,*PATHS)}
    errors=collections.Counter()
    report={'schema_version':'i1.1','status':'fail','errors':{},'archive_sha256':None,
            'baseline_sha256':None,'manifest_entries':0,'tables':{},'auxiliary':{},
            'verification':{},'rights':{},'dispositions':{},'quarantine_reasons':{},
            'records':[],'database_write':False,'canonical_promotion':False}
    def fail(k):errors[k]+=1
    def finish():
        report['errors']=dict(sorted(errors.items()))
        report['status']='fail' if errors else 'pass'
        report['tables']={t:len(records[t]) for t in TABLES}
        report['auxiliary']={t:len(records[t]) for t in PATHS}
        return report,records
    try:
        path=Path(path)
        if path.stat().st_size>MAX_ARCHIVE_BYTES:fail('archive_too_large');return finish()
        blob=path.read_bytes(); report['archive_sha256']=hashlib.sha256(blob).hexdigest()
        if report['archive_sha256']!=expected_sha256:fail('archive_sha256_mismatch');return finish()
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            infos=z.infolist();names=[x.filename for x in infos]
            if len(names)!=len(set(names)):fail('duplicate_archive_member')
            if len(infos)>1000 or sum(x.file_size for x in infos)>MAX_UNCOMPRESSED_BYTES:fail('archive_uncompressed_limit')
            if any(x.file_size>MAX_ENTRY_BYTES or (x.file_size>1024*1024 and x.file_size>max(x.compress_size,1)*200) for x in infos):fail('archive_entry_or_compression_limit')
            if any(PurePosixPath(n).is_absolute() or '..' in PurePosixPath(n).parts or '\\' in n for n in names):fail('unsafe_archive_path')
            if errors:return finish()
            if z.testzip() is not None:fail('archive_crc_mismatch');return finish()
            manifest_name='logs/FILE_SHA256SUMS.txt'
            try: lines=z.read(manifest_name).decode('utf-8').splitlines()
            except (KeyError,UnicodeError):fail('manifest_invalid');return finish()
            report['manifest_entries']=len(lines)
            if len(lines)!=expected_manifest_count:fail('manifest_entry_count')
            listed={}
            for line in lines:
                m=re.fullmatch(r'([0-9a-f]{64})  (.+)',line)
                if not m:fail('manifest_entry_invalid');continue
                sha,name=m.groups()
                if name in listed or name==manifest_name or name not in names or PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts:
                    fail('manifest_path_invalid');continue
                listed[name]=sha
                if hashlib.sha256(z.read(name)).hexdigest()!=sha:fail('manifest_hash_mismatch')
            if {x.filename for x in infos if not x.is_dir()}-{manifest_name} != set(listed):fail('manifest_coverage_mismatch')
            if errors:return finish()
            try: base_blob=z.read('baseline/SCRIPTURA_D11_D2_RESEARCH.zip')
            except KeyError:fail('baseline_archive_missing');return finish()
            report['baseline_sha256']=hashlib.sha256(base_blob).hexdigest()
            if report['baseline_sha256']!=expected_baseline_sha256:fail('baseline_archive_sha_mismatch');return finish()
            def rows(name):
                try: raw=z.read(name)
                except KeyError:fail('record_file_missing');return []
                out=[]
                for no,line in enumerate(raw.splitlines(keepends=True),1):
                    if not line.strip():continue
                    try: obj=_json_loads(line.decode('utf-8-sig'))
                    except (ValueError,UnicodeError,RecursionError):fail('record_json_invalid');continue
                    if not isinstance(obj,dict):fail('record_not_object');continue
                    out.append({'data':obj,'file':name,'row_number':no,'sha256':hashlib.sha256(line).hexdigest(),'disposition':'quarantined','reasons':[]})
                return out
            baseline_rows={}
            with zipfile.ZipFile(io.BytesIO(base_blob)) as base_zip:
                inner=base_zip.infolist(); inner_names=[x.filename for x in inner]
                if len(inner_names)!=len(set(inner_names)) or len(inner)>1000 or sum(x.file_size for x in inner)>MAX_UNCOMPRESSED_BYTES or any(x.file_size>MAX_ENTRY_BYTES or (x.file_size>1024*1024 and x.file_size>max(x.compress_size,1)*200) for x in inner) or any(PurePosixPath(n).is_absolute() or '..' in PurePosixPath(n).parts or '\\' in n for n in inner_names):fail('baseline_archive_unsafe');return finish()
                if base_zip.testzip() is not None:fail('baseline_crc_mismatch');return finish()
                for table in TABLES:
                    base_path=f'baseline/records/{table}.jsonl'
                    nested_path=f'd2/records_merged/{table}.jsonl'
                    try:
                        if z.read(base_path)!=base_zip.read(nested_path):fail('baseline_records_changed')
                    except KeyError:fail('baseline_record_file_missing');continue
                    baseline=rows(base_path);baseline_rows[table]=baseline;delta=rows(f'd3/records_delta/{table}.jsonl')
                    merged=rows(f'd3/records_merged/{table}.jsonl');records[table]=merged
                    if len(merged)!=expected_counts.get(table):fail('record_count_mismatch')
                    if collections.Counter(_canonical(x['data']) for x in baseline+delta)!=collections.Counter(_canonical(x['data']) for x in merged):fail('baseline_delta_merge_mismatch')
            for table,name in PATHS.items():
                records[table]=rows(name)
                if len(records[table])!=expected_auxiliary_counts.get(table):fail('auxiliary_count_mismatch')
            try:
                rights_reader=csv.DictReader(io.StringIO(z.read('d3/D3_RIGHTS_MATRIX.csv').decode('utf-8-sig'),newline=''))
                required_right_fields={'record_origin','id','source_id','source_title','edition_id','edition_label','action','decision','checked_at','evidence_url','purpose','territory','period','rights_holder','exceptions','attribution_requirements','evidence_missing_reason','license_statement','scope_note'}
                if not rights_reader.fieldnames or len(rights_reader.fieldnames)!=len(set(rights_reader.fieldnames)) or set(rights_reader.fieldnames)!=required_right_fields: fail('rights_csv_header_invalid')
                rights_csv=list(rights_reader)
            except (KeyError,UnicodeError,csv.Error):fail('rights_csv_invalid');rights_csv=[]
            by_right_id={x['data'].get('id'):x['data'] for x in records['rights'] if isinstance(x['data'].get('id'),str)}
            if len(rights_csv)!=len(records['rights']):fail('rights_csv_count_mismatch')
            csv_ids=set()
            editions_by_id={x['data'].get('id'):x['data'] for x in records['editions'] if isinstance(x['data'].get('id'),str)}
            sources_by_id={x['data'].get('id'):x['data'] for x in records['sources'] if isinstance(x['data'].get('id'),str)}
            baseline_right_ids={x['data'].get('id') for x in baseline_rows['rights'] if isinstance(x['data'].get('id'),str)}
            for row in rights_csv:
                if None in row or any(v is None for v in row.values()):fail('rights_csv_row_malformed');continue
                rid=row.get('id'); rhs=by_right_id.get(rid)
                if not isinstance(rid,str) or rid in csv_ids or not rhs:fail('rights_csv_id_invalid');continue
                csv_ids.add(rid)
                edition_id=rhs.get('edition_id')
                if not isinstance(edition_id,str):fail('rights_csv_provenance_mismatch');continue
                edition=editions_by_id.get(edition_id,{})
                source_id=edition.get('source_id')
                source=sources_by_id.get(source_id,{}) if isinstance(source_id,str) else {}
                if row.get('record_origin') != ('D2_baseline' if rid in baseline_right_ids else 'D3') or row.get('source_id') != edition.get('source_id') or row.get('source_title') != source.get('title') or row.get('edition_label') != edition.get('label'):fail('rights_csv_provenance_mismatch')
                for k in ('edition_id','action','decision'):
                    if k not in row or row[k]!=rhs.get(k):fail('rights_csv_mismatch')
                for k in ('checked_at','evidence_url','purpose','territory','period','rights_holder','exceptions','attribution_requirements','evidence_missing_reason','license_statement','scope_note'):
                    if k in row and row[k] != ('' if rhs.get(k) is None else str(rhs.get(k))):fail('rights_csv_mismatch')
            try:
                data=io.StringIO(z.read('d3/coverage/CANON_COVERAGE_D3_FINAL.csv').decode('utf-8-sig'),newline='')
                coverage_reader=csv.DictReader(data)
                required_coverage_fields={'id','work_label','opc_wcf_listing_status','usccb_bible_listing_status','chabad_tanakh_listing_status','chabad_group','oca_institutional_explanation_status','d2_passage_records','d2_claim_links','d2_address_coverage','d3_merged_passage_records','d3_merged_claim_links','d3_address_coverage','scope_note'}
                if not coverage_reader.fieldnames or len(coverage_reader.fieldnames)!=len(set(coverage_reader.fieldnames)) or not required_coverage_fields.issubset(coverage_reader.fieldnames): fail('coverage_csv_header_invalid')
                coverage_csv=list(coverage_reader)
            except (KeyError,UnicodeError,csv.Error):fail('coverage_csv_invalid');coverage_csv=[]
            if len(coverage_csv)!=len(records['coverage']):fail('coverage_csv_count_mismatch')
            else:
                for csvrow,item in zip(coverage_csv,records['coverage']):
                    if not csvrow or None in csvrow or any(k not in item['data'] or ('' if item['data'][k] is None else str(item['data'][k]))!=v for k,v in csvrow.items()):fail('coverage_csv_mismatch')
    except (OSError,zipfile.BadZipFile,RuntimeError,ValueError,OverflowError,RecursionError):
        fail('archive_unreadable');return finish()
    if errors:return finish()
    sem_errors,facts=validate_semantics({t:records[t] for t in TABLES},allow_synthetic=allow_synthetic)
    errors.update(sem_errors);report.update(facts)
    if errors:return finish()
    idx={t:{x['data']['id']:x['data'] for x in records[t]} for t in TABLES}
    seen=set().union(*(set(i) for i in idx.values()))
    statuses=collections.Counter()
    for item in records['bibliographic_edges']:
        x=item['data'];rid=x.get('id')
        if _forbidden(x):fail('forbidden_content_field')
        if not allow_synthetic and _synthetic(x):fail('synthetic_research_mixture')
        if not isinstance(rid,str) or not rid.strip() or rid in seen:fail('auxiliary_id_invalid_or_duplicate')
        else:seen.add(rid)
        fs=x.get('from_source_id');ts=x.get('to_source_id');loc=x.get('locator_id')
        if not isinstance(fs,str) or not isinstance(ts,str) or fs not in idx['sources'] or ts not in idx['sources'] or not isinstance(loc,str) or loc not in idx['locators']:fail('bibliographic_reference_missing');continue
        edition=idx['editions'].get(idx['locators'][loc].get('edition_id'),{})
        if edition.get('source_id')!=fs:fail('bibliographic_locator_source_mismatch')
        if x.get('relation_type')!='bibliographic_citation':fail('bibliographic_type_invalid')
        st=x.get('review_status')
        if st not in ('source_checked','partial_pending','candidate','disputed'):fail('bibliographic_status_invalid')
        if st=='source_checked' and (idx['locators'][loc].get('verification_status') not in ('source_checked','edition_checked') or not _valid_timestamp(idx['locators'][loc].get('checked_at'))):fail('bibliographic_unchecked_locator')
        if st=='source_checked' and not _valid_timestamp(x.get('checked_at')): item['edge_date_missing']=True
        if not isinstance(x.get('prior_origin'),str) or not x['prior_origin'].strip():fail('bibliographic_prior_origin_missing')
        if not isinstance(x.get('relation_scope'),str) or not x['relation_scope'].strip():fail('bibliographic_scope_missing')
        if isinstance(st,str):statuses[st]+=1
    report['bibliography']={'edge_type':'bibliographic_citation','claim_relation_conversion':False,'statuses':dict(sorted(statuses.items()))}
    report['bibliography']['source_checked_without_edge_date']=sum(bool(x.get('edge_date_missing')) for x in records['bibliographic_edges'])
    coverage_enums={
        'opc_wcf_listing_status':{'listed','not_in_66_list'},
        'usccb_bible_listing_status':{'listed','not_in_usccb_73_list','included_within_book'},
        'chabad_tanakh_listing_status':{'listed','not_in_chabad_24_list','outside_tanakh_corpus'},
        'oca_institutional_explanation_status':{'not_checked','institutional_explanation_included'},
        'd3_address_coverage':{'partial','not_recorded'}}
    coverage_status={k:collections.Counter() for k in ('opc_wcf_listing_status','usccb_bible_listing_status','chabad_tanakh_listing_status','oca_institutional_explanation_status','d3_address_coverage')}
    numfields=('d2_passage_records','d2_claim_links','d3_merged_passage_records','d3_merged_claim_links')
    def work_key(value):
        if not isinstance(value,str): return ''
        name=value.strip().casefold()
        return 'psalm' if name in ('psalm','psalms') else name
    def work_counts(data):
        passages={x['data']['id']:work_key(x['data'].get('work')) for x in data['passages']}
        pcounts=collections.Counter(passages.values())
        ccounts=collections.Counter()
        for entry in data['claims']:
            for pid in entry['data'].get('passage_ids',[]):
                if pid in passages: ccounts[passages[pid]]+=1
        return pcounts,ccounts
    base_p,base_c=work_counts(baseline_rows)
    merged_p,merged_c=work_counts(records)
    coverage_work_seen=set()
    for item in records['coverage']:
        x=item['data'];rid=x.get('id')
        if _forbidden(x):fail('forbidden_content_field')
        if not allow_synthetic and _synthetic(x):fail('synthetic_research_mixture')
        if not isinstance(rid,str) or not rid.strip() or rid in seen:fail('auxiliary_id_invalid_or_duplicate')
        else:seen.add(rid)
        for key in ('work_label','comparison_unit','review_status','scope_note'):
            if not isinstance(x.get(key),str) or not x[key].strip():fail('coverage_required_field_missing')
        work=work_key(x.get('work_label'))
        if not work or work in coverage_work_seen:fail('coverage_work_duplicate_or_missing')
        coverage_work_seen.add(work)
        for field,expected in (('d2_passage_records',base_p[work]),('d2_claim_links',base_c[work]),('d3_merged_passage_records',merged_p[work]),('d3_merged_claim_links',merged_c[work])):
            if x.get(field)!=expected:fail('coverage_work_count_mismatch')
        for key in numfields:
            if not isinstance(x.get(key),int) or isinstance(x[key],bool) or x[key]<0:fail('coverage_count_invalid')
        for key,c in coverage_status.items():
            if not isinstance(x.get(key),str) or not x[key].strip():fail('coverage_status_invalid')
            elif x[key] not in coverage_enums[key]:fail('coverage_status_invalid')
            else:c[x[key]]+=1
        if not isinstance(x.get('citation_sources'),dict) or not x['citation_sources']:fail('coverage_sources_missing')
        elif any(not isinstance(k,str) or not isinstance(v,str) or not URL.fullmatch(v) for k,v in x['citation_sources'].items()):fail('coverage_source_url_invalid')
        if not _valid_timestamp(x.get('checked_at')):fail('coverage_checked_date_invalid')
        if x.get('d3_address_coverage') not in ('partial','not_recorded'):fail('coverage_address_status_invalid')
        if isinstance(x.get('d3_merged_passage_records'),int) and (x.get('d3_address_coverage')=='partial') != (x['d3_merged_passage_records']>0):fail('coverage_address_count_mismatch')
    expected_links=sum(len(x['data'].get('passage_ids',[])) for x in records['claims'])
    if sum(x['data'].get('d3_merged_passage_records',0) for x in records['coverage'] if isinstance(x['data'].get('d3_merged_passage_records'),int))!=len(records['passages']):fail('coverage_passage_total_mismatch')
    if sum(x['data'].get('d3_merged_claim_links',0) for x in records['coverage'] if isinstance(x['data'].get('d3_merged_claim_links'),int))!=expected_links:fail('coverage_claim_link_total_mismatch')
    report['coverage']={'rows':len(records['coverage']), 'passage_record_references':len(records['passages']), 'claim_passage_references':expected_links,'status_counts':{k:dict(sorted(v.items())) for k,v in coverage_status.items()},'scope':'listing comparisons only; no textual alignment or full canon verification'}
    source_kinds={'platform_or_resource_registry_candidate','bible_translation','reference_work','document','commentary','official_document','homily','article','scholarly_article','scholarly_chapter','dataset','dataset_documentation','translation','scholarly_bibliographic_record','historical_theological_work','web_comment','biographical_or_institutional_statement','book'}
    def safe_kind(value): return value if isinstance(value,str) and value in source_kinds else 'other_unrecognized'
    def safe_metadata(value): return value if value in ('source_checked','search_result_only') else ('unrecorded' if value is None or value=='' else 'other_unrecognized')
    report['source_kinds']=dict(sorted(collections.Counter(safe_kind(x['data'].get('kind')) for x in records['sources']).items()))
    report['source_metadata_status']={'counts':dict(sorted(collections.Counter(safe_metadata(x['data'].get('metadata_status')) for x in records['sources']).items())), 'note':'Reported provenance, not proof of DOI or scholarly verification.'}
    dois=[x['data']['doi'].strip().lower() for x in records['sources'] if isinstance(x['data'].get('doi'),str) and x['data']['doi'].strip()]
    normalized=[re.sub(r'^(?:doi:\s*|https?://(?:dx\.)?doi\.org/)', '', d).strip() for d in dois]
    checked_edition_ids={l.get('edition_id') for l in idx['locators'].values() if l.get('verification_status') in ('source_checked','edition_checked') and _valid_timestamp(l.get('checked_at'))}
    checked_sources={e.get('source_id') for e in idx['editions'].values() if e.get('id') in checked_edition_ids}
    doi_sources={x['data']['id'] for x in records['sources'] if isinstance(x['data'].get('doi'),str) and x['data']['doi'].strip()}
    doi_status=collections.Counter(safe_metadata(x['data'].get('metadata_status')) for x in records['sources'] if x['data'].get('id') in doi_sources)
    report['doi']={'unique_identifiers':len(set(normalized)),'sources_with_checked_locator':len(doi_sources & checked_sources), 'source_metadata_status':dict(sorted(doi_status.items())), 'note':'Input statuses and locator checks are provenance only, not independent DOI verification, full-text access, or reuse rights.'}
    reasons={'sources':'source_metadata_and_rights_review_required','editions':'edition_work_corpus_fk_unresolved','locators':'edition_locator_mapping_unresolved','rights':'action_rights_independent_review_required','passages':'canon_work_scheme_mapping_unresolved','alignments':'bidirectional_scope_and_enum_unresolved','agents':'literary_voice_and_agent_kind_mapping_required','affiliations':'tradition_affiliation_provenance_review_required','claims':'claim_version_and_attribution_mapping_required','evidence':'claim_version_evidence_mapping_required','relations':'claim_version_relation_mapping_required','reviews':'historical_review_not_independent_approval','bibliographic_edges':'bibliographic_citation_separate_from_argument','coverage':'canon_coverage_comparison_not_alignment'}
    report['virtual_mapping']={t:{'disposition':'quarantined','reason':reason,'target':'separate auxiliary' if t in ('bibliographic_edges','coverage') else 'canonical mapping not authorized'} for t,reason in reasons.items()}
    for table,items in records.items():
        for item in items:
            item['reasons']=[reasons[table]] + (['source_checked_edge_date_missing'] if item.get('edge_date_missing') else [])
            report['records'].append({'table':table,'row_number':item['row_number'],'line_sha256':item['sha256'],'disposition':'quarantined','reason_codes':item['reasons']})
    report['quarantine_reasons']=dict(sorted(collections.Counter(reason for items in records.values() for item in items for reason in item['reasons']).items()))
    report['dispositions']={'eligible':0,'quarantined':sum(len(v) for v in records.values())}
    report['data_classes']={'scope':'claim input statuses only; other entities are not automatically classified', 'candidate_claims':sum(x['data'].get('review_status')=='candidate' for x in records['claims']), 'source_verified_claims':sum(x['data'].get('review_status')=='source_verified' for x in records['claims']), 'scholarly_reviewed_claims':sum(x['data'].get('review_status')=='scholarly_reviewed' for x in records['claims']), 'other_records_unclassified':sum(len(records[t]) for t in records if t!='claims'), 'synthetic_in_research':0}
    evidence_claims={x['data'].get('claim_id') for x in records['evidence']}
    checked_loc_ids={l['id'] for l in idx['locators'].values() if l.get('verification_status') in ('source_checked','edition_checked') and _valid_timestamp(l.get('checked_at')) and isinstance(l.get('location'),str) and l['location'].strip()}
    supported_claims={x['data'].get('claim_id') for x in records['evidence'] if x['data'].get('review_status')=='verified' and x['data'].get('locator_id') in checked_loc_ids}
    report['claim_evidence_reference']={'claims':len(records['claims']),'claims_with_evidence':sum(x['data']['id'] in evidence_claims for x in records['claims']), 'claims_with_verified_evidence_checked_locator':sum(x['data']['id'] in supported_claims for x in records['claims']), 'claims_with_source_checked_status':sum(x['data'].get('review_status')=='source_verified' for x in records['claims']), 'note':'claim source status does not establish independent scholarly review or reuse rights'}
    return finish()
