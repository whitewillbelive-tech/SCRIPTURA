"""Generate synthetic D-2-style archives; never uses the actual research ZIP."""
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

TABLES = ('sources', 'editions', 'locators', 'rights', 'passages', 'alignments', 'agents', 'affiliations', 'claims', 'evidence', 'relations', 'reviews')
ACTIONS = ('browse', 'collect_metadata', 'store_raw', 'store_excerpt', 'index_fulltext', 'embed', 'send_to_model', 'redistribute', 'public_link')
SNAPSHOT = 'TEST-SYNTHETIC-ONLY-v1'


def synthetic_rows(source_count=1):
    if source_count < 1:
        raise ValueError('at least one synthetic source required')
    sources = [{'id': f'src:synthetic-{i}', 'title': f'Fictional source {i}', 'kind': 'book', 'creator': 'Invented author', 'url': 'https://example.invalid/source', 'doi': f'10.99999/fiction-{i}'} for i in range(source_count)]
    return {
        'sources': sources,
        'editions': [{'id':'ed:synthetic-1','source_id':'src:synthetic-0','label':'Fictional edition','language':'en','version_status':'partial'}],
        'locators': [{'id':'loc:synthetic-1','edition_id':'ed:synthetic-1','location':'fictional page 1','verification_status':'unchecked','checked_at':None}],
        'rights': [{'id':f'right:synthetic-{a}','edition_id':'ed:synthetic-1','action':a,'decision':'unknown','checked_at':None,'evidence_url':None,'evidence_missing_reason':'fictional test, no permission'} for a in ACTIONS],
        'passages': [{'id':'passage:synthetic-1','corpus':'Fictional corpus','work':'Fictional work','reference_scheme':'Fictional scheme','reference':'1.1','coverage_status':'partial'}, {'id':'passage:synthetic-2','corpus':'Fictional corpus','work':'Fictional work','reference_scheme':'Other fictional scheme','reference':'1.2','coverage_status':'partial'}],
        'alignments':[{'id':'alignment:synthetic-1','from_passage_id':'passage:synthetic-1','to_passage_id':'passage:synthetic-2','alignment_type':'equivalent_segment','review_status':'partial_pending','locator_id':'loc:synthetic-1'}],
        'agents':[{'id':'agent:synthetic-1','name':'Fictional researcher','kind':'person'}],
        'affiliations':[],
        'claims':[{'id':'claim:synthetic-1','statement_ko':'합성 검증 예시','passage_ids':['passage:synthetic-1'],'agent_id':'agent:synthetic-1','attribution_kind':'individual_opinion','locator_id':'loc:synthetic-1','review_status':'candidate','scope_note':'Fictional test only'}],
        'evidence':[{'id':'evidence:synthetic-1','claim_id':'claim:synthetic-1','role':'context','locator_id':'loc:synthetic-1','review_status':'proposed','explanation_ko':'합성 근거 예시'}],
        'relations':[],
        'reviews':[{'id':'review:synthetic-1','target_type':'claim','target_id':'claim:synthetic-1','reviewer':'Fictional reviewer','decision':'candidate','reviewed_at':'2026-01-01T00:00:00Z','notes':'Synthetic test'}],
    }


def write_archive(path, rows=None, *, snapshot=SNAPSHOT, alter_files=None, alter_manifest=None, extra_entries=None):
    """Return (SHA256, merged counts). All payloads are generated synthetic values."""
    rows = rows if rows is not None else synthetic_rows()
    files = {}
    for table in TABLES:
        payload = ''.join(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n' for row in rows[table]).encode('utf-8')
        files[f'd1_1/records/{table}.jsonl'] = b''
        files[f'd2/records_delta/{table}.jsonl'] = payload
        files[f'd2/records_merged/{table}.jsonl'] = payload
    for n in range(29):
        files[f'synthetic/support-{n:02d}.txt'] = f'Synthetic test file {n}\n'.encode()
    if alter_files:
        alter_files(files)
    entries = [{'path':name, 'bytes':len(raw), 'sha256':hashlib.sha256(raw).hexdigest()} for name,raw in sorted(files.items())]
    counts = {table:len(rows[table]) for table in TABLES}
    manifest = {'dataset_snapshot':snapshot, 'created_at':'2026-01-01T00:00:00Z','d11_counts':{table:0 for table in TABLES}, 'd2_merged_counts':counts, 'file_hashes':entries, 'self_hash_policy':'RUN_MANIFEST.json excluded from self hash'}
    if alter_manifest:
        alter_manifest(manifest)
    out = Path(path)
    def write_deterministic(z, name, raw):
        info = ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
        info.create_system = 3
        info.external_attr = 0o600 << 16
        info.compress_type = ZIP_DEFLATED
        z.writestr(info, raw, compress_type=ZIP_DEFLATED, compresslevel=6)
    with ZipFile(out, 'w', compression=ZIP_DEFLATED) as z:
        for name,raw in files.items(): write_deterministic(z,name,raw)
        write_deterministic(z,'RUN_MANIFEST.json',json.dumps(manifest,ensure_ascii=False).encode())
        for name,raw in (extra_entries or []): write_deterministic(z,name,raw)
    return hashlib.sha256(out.read_bytes()).hexdigest(), counts
