"""Generate a deterministic D-3-shaped archive from fictional records only."""
import copy
import csv
import hashlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

from s1b2_synthetic_factory import TABLES, synthetic_rows, write_archive as write_d2

RIGHTS_CSV = ('record_origin','id','source_id','source_title','edition_id','edition_label','action','decision','purpose','territory','period','rights_holder','exceptions','attribution_requirements','checked_at','evidence_url','evidence_missing_reason','license_statement','scope_note')

COVERAGE_CSV = ('id','work_label','opc_wcf_listing_status','usccb_bible_listing_status',
                'chabad_tanakh_listing_status','chabad_group','oca_institutional_explanation_status',
                'd2_passage_records','d2_claim_links','d2_address_coverage',
                'd3_merged_passage_records','d3_merged_claim_links','d3_address_coverage','scope_note')


def _jsonl(rows):
    return ''.join(json.dumps(row, ensure_ascii=False, sort_keys=True)+'\n' for row in rows).encode('utf8')


def synthetic_edges():
    return [{'id':f'bib:fiction-{i}', 'from_source_id':'src:synthetic-0',
             'to_source_id':f'src:synthetic-{i+1}', 'relation_type':'bibliographic_citation',
             'locator_id':'loc:synthetic-1', 'review_status':'partial_pending',
             'observed_at':'2026-01-01T00:00:00Z', 'citation_identity_note':'Fictional, no confirmation',
             'relation_scope':'fictional bibliographic citation only','prior_origin':'none'} for i in range(11)]


def synthetic_coverage():
    rows = [{'id':f'coverage:fiction-{i}', 'work_label':f'Fictional Coverage Unit {i}',
             'comparison_unit':'book_or_addition_segment', 'opc_wcf_listing_status':'not_in_66_list',
             'usccb_bible_listing_status':'not_in_usccb_73_list',
             'chabad_tanakh_listing_status':'not_in_chabad_24_list', 'chabad_group':None,
             'oca_institutional_explanation_status':'not_checked', 'd2_passage_records':0,
             'd2_claim_links':0, 'd2_address_coverage':'not_recorded', 'd3_address_coverage':'not_recorded',
             'citation_sources':{key:'https://example.invalid/synthetic' for key in ('chabad','oca','oca_history','oca_prophets','opc','usccb')},
             'review_status':'source_checked_list_mapping_not_textual_alignment',
             'checked_at':'2026-01-01T00:00:00Z', 'scope_note':'Synthetic test only',
             'd3_merged_passage_records':0, 'd3_merged_claim_links':0} for i in range(80)]
    rows[0].update(work_label='Fictional work',d2_passage_records=2,d2_claim_links=1,d2_address_coverage='partial',d3_merged_passage_records=2,d3_merged_claim_links=1,d3_address_coverage='partial')
    return rows


def build_archive(path, *, base_rows=None, delta_rows=None, edges=None, coverage=None,
                  mutate_files=None, mutate_manifest=None, extra_entries=None):
    """Return ZIP digest, D2 digest, and merged counts; mutations are synthetic test only."""
    base = copy.deepcopy(base_rows if base_rows is not None else synthetic_rows(12))
    delta = copy.deepcopy(delta_rows if delta_rows is not None else {table:[] for table in TABLES})
    edges = copy.deepcopy(edges if edges is not None else synthetic_edges())
    if coverage is None:
        coverage = synthetic_coverage()
        count_base = len(base['passages'])
        count_merged = count_base + len(delta['passages'])
        links_base = sum(len(c.get('passage_ids', [])) for c in base['claims'])
        links_merged = links_base + sum(len(c.get('passage_ids', [])) for c in delta['claims'])
        coverage[0].update(d2_passage_records=count_base, d3_merged_passage_records=count_merged, d2_claim_links=links_base, d3_merged_claim_links=links_merged, d2_address_coverage='partial' if count_base else 'not_recorded', d3_address_coverage='partial' if count_merged else 'not_recorded')
        if base['passages']:
            coverage[0]['work_label'] = base['passages'][0]['work']
    coverage = copy.deepcopy(coverage)
    with TemporaryDirectory(prefix='i1-synthetic-d2-') as tmp:
        old = Path(tmp)/'synthetic-d2.zip'
        d2_sha, _ = write_d2(old, base)
        nested = old.read_bytes()
    files = {'baseline/SCRIPTURA_D11_D2_RESEARCH.zip':nested}
    for table in TABLES:
        files[f'baseline/records/{table}.jsonl']=_jsonl(base[table])
        files[f'd3/records_delta/{table}.jsonl']=_jsonl(delta[table])
        files[f'd3/records_merged/{table}.jsonl']=_jsonl(base[table]+delta[table])
    files['d3/graph/bibliographic_edges.jsonl']=_jsonl(edges)
    files['d3/coverage/CANON_COVERAGE_D3_FINAL.jsonl']=_jsonl(coverage)
    csv_text=io.StringIO(newline='')
    writer=csv.DictWriter(csv_text, fieldnames=COVERAGE_CSV, extrasaction='ignore', lineterminator='\n')
    writer.writeheader(); writer.writerows(coverage)
    files['d3/coverage/CANON_COVERAGE_D3_FINAL.csv']=csv_text.getvalue().encode('utf8')
    rights_csv=io.StringIO(newline='')
    rights_writer=csv.DictWriter(rights_csv, fieldnames=RIGHTS_CSV, extrasaction='ignore', lineterminator='\n')
    rights_writer.writeheader()
    editions={e['id']:e for e in base['editions']+delta['editions']}
    sources={r['id']:r for r in base['sources']+delta['sources']}
    for origin, values in (('D2_baseline',base['rights']),('D3',delta['rights'])):
        for right in values:
            edition=editions.get(right.get('edition_id'),{})
            source=sources.get(edition.get('source_id'),{})
            row=dict(right,record_origin=origin,source_id=edition.get('source_id',''),source_title=source.get('title',''),edition_label=edition.get('label',''))
            rights_writer.writerow(row)
    files['d3/D3_RIGHTS_MATRIX.csv']=rights_csv.getvalue().encode('utf8')
    for i in range(28):files[f'synthetic/support-{i:02d}.txt']=f'Fictional support {i}\n'.encode()
    if mutate_files: mutate_files(files)
    lines=[f'{hashlib.sha256(raw).hexdigest()}  {name}' for name,raw in sorted(files.items())]
    if mutate_manifest: mutate_manifest(lines)
    manifest=('\n'.join(lines)+'\n').encode('utf8')
    path=Path(path)
    with ZipFile(path,'w') as z:
        for name,raw in [*sorted(files.items()),('logs/FILE_SHA256SUMS.txt',manifest),*(extra_entries or [])]:
            info=ZipInfo(name,(2020,1,1,0,0,0));info.create_system=3;info.external_attr=0o600<<16;info.compress_type=ZIP_DEFLATED
            z.writestr(info,raw,compresslevel=6)
    return hashlib.sha256(path.read_bytes()).hexdigest(), d2_sha, {t:len(base[t])+len(delta[t]) for t in TABLES}
