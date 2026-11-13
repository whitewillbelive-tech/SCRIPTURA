"""Fixed D12 receipt. No research strings, identifiers or paths are logged."""
import io
import os
import re
from collections import Counter
from zipfile import ZipFile
from i3_bridge import d6 as prior
from j2_bridge import candidate_readonly as base
from j3_bridge.d9_validation import TABLE_COUNTS
from j3_bridge.private_io import read_checked_d8_layers
from k1_bridge.candidate_archive import load_k1_archive, _D10_TABLES, _one_suffix
from k13_bridge.local_candidate import prepare_local_candidate_index

D12_SHA = 'b7ece239f5800cc601b525525963870f6e0a6d83ed62cdffeaf5a49d128cbc12'
_D12_COUNTS = {'sources':41, 'editions':41, 'locators':42, 'passages':26,
               'passage_coverage':26, 'claims':44, 'evidence':44,
               'relationships':0, 'rights':649, 'source_access_events':41}
_D11_COUNTS = {'sources':8, 'locators':8, 'rights_actions':72,
               'source_access_events':3, 'review_queue':11}


def _read_layers(blob):
    errors = Counter()
    with ZipFile(io.BytesIO(blob)) as d12:
        d11blob = d12.read(_one_suffix(d12, '.zip'))
        with ZipFile(io.BytesIO(d11blob)) as d11:
            d10blob = d11.read(_one_suffix(d11, '.zip'))
            with ZipFile(io.BytesIO(d10blob)) as d10:
                d9blob = d10.read(_one_suffix(d10, '.zip'))
                with ZipFile(io.BytesIO(d9blob)) as d9:
                    with ZipFile(io.BytesIO(d9.read('baseline/SCRIPTURA_D8_RESEARCH.zip'))) as d8:
                        snapshot = read_checked_d8_layers(d8)
                    if snapshot.error_count:
                        raise base.CandidateError('archive_invalid')
                    layers = snapshot.layers
                    layers['d9'] = {table: prior._records(d9, 'd9/records/' + table + '.jsonl', errors) for table in TABLE_COUNTS}
                layers['d10'] = {table: prior._records(d10, _one_suffix(d10, '/records/' + table + '.jsonl'), errors) for table in _D10_TABLES}
            layers['d11'] = {table: prior._records(d11, 'd11/records/' + table + '.jsonl', errors) for table in _D11_COUNTS}
        layers['d12'] = {table: prior._records(d12, 'd12/records/' + table + '.jsonl', errors) for table in _D12_COUNTS}
    if errors:
        raise base.CandidateError('archive_invalid')
    for stage, counts in (('d11', _D11_COUNTS), ('d12', _D12_COUNTS)):
        if any(len(layers[stage][table]) != count for table, count in counts.items()):
            raise base.CandidateError('archive_invalid')
    # Author fallback is an in-memory derived field; original archive is intact.
    for stage in ('d11', 'd12'):
        copied=[]
        for entry in layers[stage]['sources']:
            row=dict(entry['value'])
            if not row.get('creator') and isinstance(row.get('author'), str):
                row['creator']=row['author']
            copied.append({'line':entry['line'], 'value':row})
        layers[stage]['sources']=copied
    return layers, d10blob


def _validate(layers):
    d12=layers['d12']; all_ids={}
    for stage,tables in layers.items():
        for table,items in tables.items():
            if table not in ('sources','claims','editions','locators','passages','evidence'):
                continue
            for entry in items:
                ident=entry['value'].get('id')
                if isinstance(ident,str): all_ids.setdefault(ident,[]).append((stage,table))
    for stage in ('d11','d12'):
        for table,entries in layers[stage].items():
            for entry in entries:
                ident=entry['value'].get('id')
                if isinstance(ident,str) and table in ('sources','claims','editions','locators','passages','evidence') and len(all_ids.get(ident,[]))!=1:
                    raise base.CandidateError('archive_invalid')
    def hits(ident,table):
        return len(all_ids.get(ident,[]))==1 and all_ids[ident][0][1]==table
    counts=Counter()
    for entry in d12['claims']:
        row=entry['value']; passages=row.get('passage_ids')
        if not isinstance(passages,list) or len(passages)!=1 or not hits(passages[0],'passages') or not hits(row.get('source_locator_id') or row.get('locator_id'),'locators'):
            raise base.CandidateError('archive_invalid')
        counts[passages[0]]+=1
    for entry in d12['evidence']:
        row=entry['value']
        if not hits(row.get('claim_id'),'claims') or not hits(row.get('locator_id'),'locators'):
            raise base.CandidateError('archive_invalid')
    claims={e['value']['id']:e['value'] for e in d12['claims']}
    editions={e['value']['id']:e['value'] for e in d12['editions']}
    locators={e['value']['id']:e['value'] for e in d12['locators']}
    for entry in d12['evidence']:
        row=entry['value']; claim=claims[row['claim_id']]
        if row['locator_id'] != (claim.get('source_locator_id') or claim.get('locator_id')):
            raise base.CandidateError('archive_invalid')
    for entry in d12['editions']:
        if not hits(entry['value'].get('source_id'),'sources'): raise base.CandidateError('archive_invalid')
    for entry in d12['locators']:
        row=entry['value']
        if not hits(row.get('source_id'),'sources') or not hits(row.get('edition_id'),'editions'): raise base.CandidateError('archive_invalid')
        if row['edition_id'] in editions and editions[row['edition_id']].get('source_id') != row['source_id']:
            raise base.CandidateError('archive_invalid')
    if sum(counts.values())!=44 or len(counts)!=25 or sum(x>=2 for x in counts.values())!=16:
        raise base.CandidateError('archive_invalid')
    return {'sources':41, 'claims':44, 'passages':26, 'evidence':44, 'claim_passage_links':44, 'multiple_passages':16, 'direct_rebuttals':0, 'd11_sources':8}


def _read_d12(blob):
    layers,d10blob=_read_layers(blob)
    summary=_validate(layers)
    original=load_k1_archive(d10blob)
    if original.get('dataset')!='D10' or len(original.get('records',[]))!=528:
        raise base.CandidateError('baseline_invalid')
    projected=base._build_projection(layers)
    additions=[r for r in projected if (r.get('stage')=='d11' and r.get('record_kind')=='source') or (r.get('stage')=='d12' and r.get('record_kind') in ('source','claim'))]
    if len(additions)!=93 or len({r.get('key') for r in additions})!=93:
        raise base.CandidateError('archive_invalid')
    result=dict(original); result['dataset']='D12'; result['records']=list(original['records'])+additions
    passages=_d12_passage_map(layers)
    result['_k2_passages']=[p for p in passages.values() if p]
    claims_by_key={f'd12:claims:{e["line"]}':e['value'] for e in layers['d12']['claims']}
    for record in additions:
        claim=claims_by_key.get(record.get('key'))
        if claim:
            resolved=[passages.get(ident) for ident in claim.get('passage_ids',[])]
            record['passages']=[p for p in resolved if p]
            first=record['passages'][0] if record['passages'] else {}
            record['passage_corpus']=first.get('corpus');record['passage_scheme']=first.get('scheme');record['passage_reference']=first.get('reference')
    result['_local_candidate_index']=prepare_local_candidate_index(result,layers)
    result['_k2_summary_index']=_summary_index(layers,additions,result['_local_candidate_index'])
    result['_k2_tradition_index']=_tradition_index(layers,additions,result['_local_candidate_index'])
    result['d12_receipt']=summary
    result['counts']=dict(original.get('counts',{}))
    result['counts']['d11']={'sources':8}; result['counts']['d12']=dict(summary)
    result['counts']['by_stage']=dict(result['counts'].get('by_stage',{}))
    result['counts']['by_stage']['d11']={'sources':8}; result['counts']['by_stage']['d12']=dict(summary)
    result['unmapped_summary']=dict(original.get('unmapped_summary',{}))
    result['unmapped_summary']['d11']={'sources':{'input_count':8,'mapping':'partial'}}
    result['unmapped_summary']['d12']={k:{'input_count':v,'mapping':'partial'} for k,v in _D12_COUNTS.items()}
    return result


def load_k2_archive(path):
    """Accept D8-D10 or pinned D12 only, with generic exceptions."""
    try:
        if isinstance(path,bytes):
            if len(path)>64*1024*1024: raise base.CandidateError('archive_invalid')
            read=lambda:path
        else:
            location=os.fspath(path)
            if not isinstance(location,str) or location.startswith(('\\\\','//','\\/','/\\')) or re.match(r'^[A-Za-z][A-Za-z0-9+.-]+:',location):
                raise base.CandidateError('archive_not_local')
            read=lambda:prior._bounded_read(path)
        blob=read()
        if prior._sha(blob)!=D12_SHA: return load_k1_archive(path)
        result=_read_d12(blob)
        if prior._sha(read())!=D12_SHA: raise base.CandidateError('archive_changed')
        return result
    except base.CandidateError as exc:
        allowed={'archive_invalid','archive_not_local','archive_not_recognized','archive_changed','baseline_invalid'}
        code=exc.args[0] if len(exc.args)==1 and type(exc.args[0]) is str and exc.args[0] in allowed else 'archive_invalid'
        raise base.CandidateError(code) from None
    except Exception:
        raise base.CandidateError('archive_invalid') from None

class _SummaryIndex:
    __slots__=('__values',)
    def __init__(self, values): self.__values=values
    def __repr__(self): return '<PrivateResearchSummaries redacted>'
    def get(self, key): return self.__values.get(key)


def summary_for_record(index, dataset, key):
    """Return only a locally vetted self-summary for one opaque coordinate."""
    if type(index) is not _SummaryIndex or dataset!='D12' or not isinstance(key,str): return None
    return index.get(key)


# Conventional books only; arbitrary source prose is never an address.
_K2_BOOKS=(r'Genesis|Exodus|Leviticus|Numbers|Deuteronomy|Joshua|Judges|Ruth|'
           r'Samuel|Kings|Chronicles|Ezra|Nehemiah|Esther|Job|Psalms?|Proverbs|'
           r'Ecclesiastes|Song of Songs|Song of Solomon|Isaiah|Jeremiah|Lamentations|'
           r'Ezekiel|Daniel|Hosea|Joel|Amos|Obadiah|Jonah|Micah|Nahum|Habakkuk|'
           r'Zephaniah|Haggai|Zechariah|Malachi|Matthew|Mark|Luke|John|Acts|Romans|'
           r'Corinthians|Galatians|Ephesians|Philippians|Colossians|Thessalonians|'
           r'Timothy|Titus|Philemon|Hebrews|James|Peter|Jude|Revelation')
_K2_PART=re.compile(r'^(?:[1-3]\s*)?(?:'+_K2_BOOKS+r')\s+\d{1,3}:\d{1,3}(?:\s*[-–]\s*\d{1,3}(?::\d{1,3})?)?$',re.I)

def _valid_bible_reference(ref):
    parts=[x.strip() for x in ref.split(';')]
    if not 1<=len(parts)<=3 or not (base._REF.fullmatch(parts[0]) or _K2_PART.fullmatch(parts[0])):
        return False
    return all(base._REF.fullmatch(p) or _K2_PART.fullmatch(p) or re.fullmatch(r'\d{1,3}:\d{1,3}(?:\s*[-–]\s*\d{1,3})?',p) for p in parts[1:])


def safe_k2_passage(value):
    """Return canonical address only when opaque numbering and corpus match."""
    if not isinstance(value,dict): return None
    corpus=value.get('corpus'); scheme=value.get('scheme'); ref=value.get('reference')
    if not isinstance(corpus,str) or not isinstance(scheme,str) or not isinstance(ref,str): return None
    if not re.fullmatch(r'd12_scheme_[1-9][0-9]*',scheme): return None
    if len(ref)<=100 and re.fullmatch(r'Bible_[1-9][0-9]*',corpus) and _valid_bible_reference(ref) and not base._QURAN_PREFIX.match(ref):
        return {'corpus':corpus,'scheme':scheme,'reference':ref,'alignment_status':'pending'}
    if re.fullmatch(r'Quran_[1-9][0-9]*',corpus) and base._QURAN_REF.fullmatch(ref):
        return {'corpus':corpus,'scheme':scheme,'reference':ref,'alignment_status':'pending'}
    return None


def _d12_passage_map(layers):
    rows=[e['value'] for e in layers['d12']['passages']]
    corpora=sorted({str(r.get('corpus')) for r in rows if isinstance(r.get('corpus'),str)})
    schemes=sorted({str(r.get('reference_scheme')) for r in rows if isinstance(r.get('reference_scheme'),str)})
    labels={}
    for c in corpora:
        lower=c.casefold()
        kind='Bible' if 'bible' in lower and 'quran' not in lower else ('Quran' if 'quran' in lower and 'bible' not in lower else None)
        if kind: labels[c]=kind+'_'+str(1+sum(1 for v in labels.values() if v.startswith(kind+'_')))
    return {r['id']:safe_k2_passage({'corpus':labels.get(r.get('corpus')),'scheme':'d12_scheme_'+str(schemes.index(r['reference_scheme'])+1) if r.get('reference_scheme') in schemes else '', 'reference':r.get('reference')}) for r in rows}


def _summary_index(layers, records, candidate_index):
    from k13_bridge.local_candidate import _field, _flags, _display_restriction
    claims={f'd12:claims:{entry["line"]}':entry['value'] for entry in layers['d12']['claims']}
    sources={e['value'].get('id'):e['value'] for e in layers['d12']['sources']}
    editions={e['value'].get('id'):e['value'] for e in layers['d12']['editions']}
    locators={e['value'].get('id'):e['value'] for e in layers['d12']['locators']}
    evidence=layers['d12']['evidence'];rights=layers['d12']['rights'];out={}
    protected=[]
    for tables in layers.values():
        for table,field in (('agents','name'),('communities','canonical_name')):
            for entry in tables.get(table,[]):
                item=entry.get('value') if isinstance(entry,dict) else None
                if isinstance(item,dict) and _flags(item) and isinstance(item.get(field),str) and item[field].strip():
                    protected.append(item[field].strip().casefold())
    for record in records:
        key=record.get('key'); row=claims.get(key)
        if not isinstance(row,dict): continue
        method=row.get('verification_method'); value=row.get('statement_ko')
        if not isinstance(method,str) or not all(s in method for s in ('자체 요약','인용 없이')) or any(s in method for s in ('아님','금지','불가','아니','미확인')) or row.get('original_text_stored') is not False or row.get('statement_original_quote'):
            continue
        if not isinstance(value,str) or len(value)>500 or any(q in value for q in ('“','”','"','「','」','\n','\r')) or _field(value,'source_title').get('status')!='recorded_unverified':
            continue
        if any(name in value.casefold() for name in protected): continue
        loc_id=row.get('source_locator_id') or row.get('locator_id'); loc=locators.get(loc_id)
        if not isinstance(loc,dict): continue
        edition=editions.get(loc.get('edition_id')); source=sources.get(loc.get('source_id'))
        if not isinstance(edition,dict) or not isinstance(source,dict) or edition.get('source_id')!=source.get('id'):
            continue
        aliases=('statement_ko','summary','summary_ko','own_summary')
        blocked=False
        for obj in (row,source,edition,loc):
            for kind in ('restricted_fields','private_fields','personal_fields','sensitive_fields'):
                members=obj.get(kind)
                if isinstance(members,(list,tuple,set)) and any(x in members for x in aliases): blocked=True
            field_policy=obj.get('field_restrictions')
            if isinstance(field_policy,dict):
                for name in aliases:
                    v=field_policy.get(name)
                    if v is True or (isinstance(v,str) and v.strip().casefold().replace('-','_') in ('denied','prohibited','restricted','blocked','conditional','private','sensitive','personal','not_allowed','forbidden')): blocked=True
        if blocked: continue
        if row.get('source_id') and row['source_id']!=source.get('id'): continue
        if row.get('edition_id') and row['edition_id']!=edition.get('id'): continue
        if sum(e['value'].get('claim_id')==row.get('id') and e['value'].get('locator_id')==loc_id for e in evidence)!=1: continue
        related=[e['value'] for e in rights if e['value'].get('edition_id')==edition.get('id') or e['value'].get('source_id')==source.get('id')]
        if _display_restriction(related) or any(_flags(x) for x in (row,source,edition,loc)): continue
        summary_actions=('own_summary','summary','display_summary','local_summary')
        denied=('denied','prohibited','restricted','blocked','conditional','not_allowed','not_permitted','forbidden')
        if any(str(x.get('action','')).strip().casefold().replace('-','_') in summary_actions and any(str(x.get(k,'')).strip().casefold().replace('-','_') in denied for k in ('decision','new_decision','permission')) for x in related): continue
        item=candidate_index.for_record('D12',key).get('source_title',{})
        if item.get('status') not in ('recorded_unverified','source_confirmed'): continue
        out[key]=value
    return _SummaryIndex(out)


def get_k2_passages(dataset):
    """Return only structured, independently validated D12 scripture addresses."""
    if not isinstance(dataset,dict) or dataset.get('dataset')!='D12': return []
    values=dataset.get('_k2_passages')
    if not isinstance(values,list): return []
    return [item for item in (safe_k2_passage(p) for p in values) if item]

class _TraditionIndex:
    __slots__=('__values',)
    def __init__(self, values): self.__values=values
    def __repr__(self): return '<PrivateTraditionLabels redacted>'
    def get(self,key): return self.__values.get(key)


def tradition_for_record(index,dataset,key):
    """Unverified source label only: never speaker, affiliation or official doctrine."""
    if type(index) is not _TraditionIndex or dataset!='D12' or not isinstance(key,str): return None
    return index.get(key)


def _tradition_index(layers, records, candidate_index):
    from k13_bridge.local_candidate import _field, _flags, _display_restriction
    claims={f'd12:claims:{entry["line"]}':entry['value'] for entry in layers['d12']['claims']}
    sources={e['value'].get('id'):e['value'] for e in layers['d12']['sources']}
    editions={e['value'].get('id'):e['value'] for e in layers['d12']['editions']}
    locators={e['value'].get('id'):e['value'] for e in layers['d12']['locators']}
    rights=layers['d12']['rights']
    protected=[]
    for tables in layers.values():
        for table,field in (('agents','name'),('communities','canonical_name')):
            for entry in tables.get(table,[]):
                item=entry.get('value') if isinstance(entry,dict) else None
                if isinstance(item,dict) and _flags(item) and isinstance(item.get(field),str) and item[field].strip():
                    protected.append(item[field].strip().casefold())
    out={}
    for record in records:
        key=record.get('key');row=claims.get(key)
        if not isinstance(row,dict) or _flags(row): continue
        value=row.get('tradition')
        if not isinstance(value,str) or len(value)>120 or _field(value,'source_title').get('status')!='recorded_unverified' or any(q in value for q in ('“','”','"','「','」')): continue
        if any(name in value.casefold() for name in protected): continue
        loc=locators.get(row.get('source_locator_id') or row.get('locator_id'))
        edition=editions.get(loc.get('edition_id')) if isinstance(loc,dict) else None
        source=sources.get(loc.get('source_id')) if isinstance(loc,dict) else None
        if not isinstance(source,dict) or not isinstance(edition,dict) or edition.get('source_id')!=source.get('id'):
            continue
        if any(_flags(x) for x in (source,edition,loc)):continue
        related=[e['value'] for e in rights if e['value'].get('edition_id')==edition.get('id') or e['value'].get('source_id')==source.get('id')]
        if _display_restriction(related):continue
        denied=('denied','prohibited','restricted','blocked','conditional','not_allowed','not_permitted','forbidden')
        if any(str(x.get('action','')).strip().casefold().replace('-','_') in ('tradition','community_name','display_tradition') and any(str(x.get(k,'')).strip().casefold().replace('-','_') in denied for k in ('decision','new_decision','permission')) for x in related):continue
        restricted=False
        for obj in (row,source,edition,loc):
            for label in ('restricted_fields','private_fields','personal_fields','sensitive_fields'):
                members=obj.get(label)
                if isinstance(members,(list,tuple,set)) and any(x in members for x in ('tradition','community_name')): restricted=True
            rule=obj.get('field_restrictions')
            if isinstance(rule,dict):
                for label in ('tradition','community_name'):
                    v=rule.get(label)
                    if v is True or (isinstance(v,str) and v.strip().casefold().replace('-','_') in ('denied','prohibited','restricted','blocked','conditional','private','sensitive','personal','not_allowed','forbidden')): restricted=True
        if restricted: continue
        title=candidate_index.for_record('D12',key).get('source_title',{})
        if title.get('status') not in ('recorded_unverified','source_confirmed'):continue
        out[key]=value
    return _TraditionIndex(out)
