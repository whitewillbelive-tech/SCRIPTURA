"""Build fictional nested D4-style ZIPs; never use the research archive."""
import csv
import hashlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

from i1_synthetic_factory import build_archive as build_d3
from s1b2_synthetic_factory import TABLES

RIGHT_HEADERS=('origin','id','source_id','source_title','edition_id','edition_label','action','decision','purpose','territory','period','rights_holder','exceptions','attribution_requirements','checked_at','evidence_url','evidence_missing_reason','license_statement','scope_note')
COVERAGE_HEADERS=('id','work_label','opc_wcf_listing_status','usccb_bible_listing_status','chabad_tanakh_listing_status','chabad_group','oca_institutional_explanation_status','d3_merged_passage_records','d3_merged_claim_links','d3_address_coverage','d4_merged_passage_records','d4_merged_claim_links','d4_address_coverage','d4_coverage_note')


def _csv_bytes(headers, rows):
    out=io.StringIO(newline='');writer=csv.DictWriter(out,fieldnames=headers,extrasaction='ignore',lineterminator='\n');writer.writeheader();writer.writerows(rows);return out.getvalue().encode('utf8')


def build_d4(path, *, mutate_files=None, mutate_manifest=None, extra_entries=None):
    with TemporaryDirectory(prefix='i2-fictional-d3-') as temp:
        d3path=Path(temp)/'synthetic-d3.zip';d3sha,d2sha,counts=build_d3(d3path)
        blob=d3path.read_bytes()
    files={'baseline/SCRIPTURA_D3_DATA_RESEARCH.zip':blob}
    with ZipFile(io.BytesIO(blob)) as z:
        for t in TABLES:
            base=z.read(f'd3/records_merged/{t}.jsonl')
            files[f'baseline/records/{t}.jsonl']=base
            files[f'd4/records_delta/{t}.jsonl']=b''
            files[f'd4/records_merged/{t}.jsonl']=base
        edges=z.read('d3/graph/bibliographic_edges.jsonl')
        files['baseline/bibliographic_edges.jsonl']=edges
        files['d4/graph/bibliographic_edges_delta.jsonl']=b''
        files['d4/graph/bibliographic_edges_merged.jsonl']=edges
        coverage=[json.loads(x) for x in z.read('d3/coverage/CANON_COVERAGE_D3_FINAL.jsonl').splitlines() if x.strip()]
        for row in coverage:
            row['d4_merged_passage_records']=row['d3_merged_passage_records'];row['d4_merged_claim_links']=row['d3_merged_claim_links'];row['d4_address_coverage']=row['d3_address_coverage'];row['d4_coverage_note']='fictional test'
        files['d4/coverage/CANON_COVERAGE_D4.jsonl']=''.join(json.dumps(row,sort_keys=True,ensure_ascii=False)+'\n' for row in coverage).encode('utf8')
        files['d4/coverage/CANON_COVERAGE_D4.csv']=_csv_bytes(COVERAGE_HEADERS,coverage)
        reader=csv.DictReader(io.StringIO(z.read('d3/D3_RIGHTS_MATRIX.csv').decode('utf8'),newline=''))
        rights=[]
        for row in reader:row['origin']='D3';rights.append(row)
        files['d4/D4_RIGHTS_MATRIX.csv']=_csv_bytes(RIGHT_HEADERS,rights)
    for name in ('d4/SOURCE_ACCESS_LOG.jsonl','d4/graph/CITATION_ACCESS_EVENTS.jsonl','d4/graph/DOI_ACCESS_EVENTS.jsonl','d4/graph/D4_ARGUMENT_OBSERVATIONS.jsonl'):
        files[name]=b''
    files['d4/coverage/D4_RESEARCH_UNIT_COVERAGE.json']=b'[]'
    files['d4/coverage/D4_RESEARCH_UNIT_COVERAGE.csv']=_csv_bytes(('passage_id','work','reference','claim_count','context_count','perspective_contexts'),[])
    for i in range(23):files[f'fictional/support-{i:02d}.txt']=b'fictional only\n'
    if mutate_files:mutate_files(files)
    lines=[f'{hashlib.sha256(raw).hexdigest()}  {name}' for name,raw in sorted(files.items())]
    if mutate_manifest:mutate_manifest(lines)
    manifest=('\n'.join(lines)+'\n').encode()
    with ZipFile(path,'w') as z:
        for name,raw in [*sorted(files.items()),('logs/FILE_SHA256SUMS.txt',manifest),*(extra_entries or [])]:
            info=ZipInfo(name,(2020,1,1,0,0,0));info.create_system=3;info.external_attr=0o600<<16;info.compress_type=ZIP_DEFLATED;z.writestr(info,raw,compresslevel=6)
    return hashlib.sha256(Path(path).read_bytes()).hexdigest(),d3sha,d2sha,counts
