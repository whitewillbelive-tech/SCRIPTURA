"""In-memory, local-only D-8 research-candidate reader.

The archive remains immutable.  No raw source, free-text claims, paths, URLs,
rights rationale or individual record IDs are returned.  Bibliographic labels
are *metadata candidates*, not evidence of copyright permission or of truth.
"""
from __future__ import annotations
import collections
import datetime
import io
import os
import re
from pathlib import Path
from zipfile import ZipFile
from i3_bridge import d6 as prior
from j1_bridge import d7 as baseline

D8_SHA = 'f5d27aca649b46b3ec17de172695adeaac13004105c516737a56dfbb1773413b'
D8_TABLES = ('assessments','audit_reviews','authority','claims','communities','conflicts','editions','evidence','institutional_assertions','locators','passages','relationships','rights','rights_overrides','source_access_events','sources','unresolved_gaps')
D8_COUNTS = {'sources':23,'editions':24,'locators':29,'claims':17,'relationships':15,'rights':216,'audit_reviews':27}
_ACTIONS = tuple(sorted(prior.ACTIONS))
_CODES = re.compile(r'^[A-Za-z0-9_:-]{1,110}$')
_DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
_DOI = re.compile(r'^10\.\d{4,9}/[-._;()/:A-Za-z0-9]+$', re.I)
# Only standalone conventional page/section numbers are displayable. Arbitrary
# locator prose, quoted phrases, search snippets and URLs remain redacted.
_LOCATOR = re.compile(r'^(?:p{1,2}\.?|page|pages|쪽|면|section|sec\.?|§)\s*[0-9]+(?:\s*[-–,]\s*[0-9]+)*$', re.I)
_BOOKS = (r'Genesis|Gen|Exodus|Exod?|Leviticus|Lev|Numbers|Num|Deuteronomy|Deut?|'
          r'Psalms?|Ps|Isaiah|Isa|Daniel|Dan|Matthew|Matt?|Mark|Mk|Luke|Lk|John|Jn|'
          r'Acts|Romans|Rom|Corinthians|Cor|Galatians|Gal|Ephesians|Eph|Philippians|Phil|'
          r'Colossians|Col|Thessalonians|Thess|Timothy|Tim|Titus|Titus|Hebrews|Heb|'
          r'James|Jas|Peter|Pet|Revelation|Rev|Quran|Qur.?an|꾸란|코란|'
          r'창세기|창|출애굽기|출|시편|시|이사야|사|마태복음|마|마가복음|막|'
          r'누가복음|눅|요한복음|요|사도행전|행|로마서|롬|고린도전서|고전|고린도후서|고후|'
          r'갈라디아서|갈|에베소서|엡|히브리서|히|요한계시록|계')
_REF = re.compile(r'^(?:[1-3]\s*)?(?:'+_BOOKS+r')\s*\d{1,3}:\d{1,3}(?:\s*[-–]\s*\d{1,3}(?::\d{1,3})?)?(?:\s*,\s*\d{1,3}(?::\d{1,3})?)*$', re.I)
_SCHEMES={
 'chapter-verse as source references; edition-specific alignment pending':'chapter_verse_edition_alignment_pending',
 'generic chapter and verse; edition alignment not verified':'chapter_verse_edition_unverified',
 'English NT chapter-verse, alignment not verified':'english_nt_chapter_verse_alignment_unverified',
 'Quran surah:ayah, Hafs numbering where applicable; edition alignment pending':'quran_hafs_numbering_alignment_pending',
 'Quran surah:ayah, version and text edition unresolved':'quran_numbering_edition_unresolved',
}
_CORPORA={'Bible':'Bible','bible':'Bible','Christian Bible':'Christian Bible',
          'Bible, New Testament':'Bible, New Testament','Quran':'Quran',
          'Book of Mormon':'Book of Mormon'}
_QURAN_REF = re.compile(r'^(?:(?:Quran|Qur.?an|꾸란|코란)\s*)?\d{1,3}:\d{1,3}(?:\s*[-–]\s*\d{1,3})?$',re.I)
_QURAN_PREFIX = re.compile(r'^(?:Quran|Qur.?an|꾸란|코란)\b',re.I)

class CandidateError(ValueError):
    """A deliberately path-free, raw-value-free startup error."""


def _code(value, default='unknown'):
    return value if isinstance(value,str) and _CODES.fullmatch(value) else default


def _method(value):
    return value if isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_ /-]{1,60}',value) else 'unknown'


def _date(value):
    if not isinstance(value,str) or len(value)<10 or not _DATE.fullmatch(value[:10]): return None
    candidate=value[:10]
    try: return candidate if datetime.date.fromisoformat(candidate).isoformat()==candidate else None
    except ValueError: return None


def _reference(value, corpus=None, scheme=None):
    """Accept only a recognized address paired with its declared corpus/scheme."""
    if not isinstance(value,str) or len(value)>80: return None
    if corpus not in _CORPORA or _scheme(scheme)=='unknown': return None
    if corpus=='Quran':
        return value if _scheme(scheme).startswith('quran_') and _QURAN_REF.fullmatch(value) else None
    if corpus=='Book of Mormon' or _scheme(scheme).startswith('quran_') or _QURAN_PREFIX.match(value): return None
    return value if _REF.fullmatch(value) else None


def _scheme(value):
    return _SCHEMES.get(value,'unknown') if isinstance(value,str) else 'unknown'


def _locator(value):
    if isinstance(value,str):
        text=value.strip()
        if len(text)<=50 and _LOCATOR.fullmatch(text): return text
    return None


def _doi(value):
    if not isinstance(value,str): return None
    text=value.strip()
    return text if len(text)<=120 and _DOI.fullmatch(text) else None


def _load_rows(z, name, errors):
    return prior._records(z,name,errors)


def _read_layers(d8, errors):
    """Read each incremental table exactly once; J1 has verified the baselines."""
    opened=[]
    try:
        d7=ZipFile(io.BytesIO(d8.read('baseline/SCRIPTURA_D7_RESEARCH.zip')));opened.append(d7)
        d6=ZipFile(io.BytesIO(d7.read('baseline/SCRIPTURA_D6_SCOPE_RESEARCH.zip')));opened.append(d6)
        d5=ZipFile(io.BytesIO(d6.read('baseline/SCRIPTURA_D5_AUTHORITY_RESEARCH.zip')));opened.append(d5)
        result={'base':{},'d5':{},'d6':{},'d7':{},'d8':{}}
        for t in prior.BASE_TABLES: result['base'][t]=_load_rows(d5,f'baseline/records/{t}.jsonl',errors)
        for n in d5.namelist():
            if n.startswith('d5/records/') and n.endswith('.jsonl'):
                result['d5'][n.rsplit('/',1)[-1][:-6]]=_load_rows(d5,n,errors)
        for t in prior.TABLES: result['d6'][t]=_load_rows(d6,f'd6/records/{t}.jsonl',errors)
        for t in baseline.TABLES: result['d7'][t]=_load_rows(d7,f'd7/records/{t}.jsonl',errors)
        for t in D8_TABLES: result['d8'][t]=_load_rows(d8,f'd8/records/{t}.jsonl',errors)
        aux={}
        for n in d8.namelist():
            if n.startswith('d8/reports/') and n.endswith('.jsonl'):
                aux[n.rsplit('/',1)[-1][:-6]]=_load_rows(d8,n,errors)
        return result,aux
    finally:
        for z in reversed(opened): z.close()


def _source_kind(source):
    return _code(source.get('kind') or source.get('bib_type') or source.get('source_type'))


def _build_projection(layers):
    """Derive browse records from allowed fields only. No hidden search index."""
    indexes={}; coordinates={}; summaries=[]
    for layer,tables in layers.items():
        for table,rows in tables.items():
            for entry in rows:
                value=entry['value'];ident=value.get('id')
                if isinstance(ident,str):
                    # Duplicate IDs are rejected by the validators, never merged.
                    indexes[ident]=(table,value)
                    coordinates[ident]=f'{layer}:{table}:{entry["line"]}'
    def lookup(ident,table):
        pair=indexes.get(ident);return pair[1] if pair and pair[0]==table else {}
    def source_from_locator(ident):
        loc=lookup(ident,'locators');ed=lookup(loc.get('edition_id'),'editions')
        src=lookup(ed.get('source_id') or loc.get('source_id'),'sources')
        return loc,ed,src
    def metadata(src):
        coordinate=coordinates.get(src.get('id'),'')
        candidate=coordinate.startswith('d8:sources:')
        try: row=int(coordinate.rsplit(':',1)[-1]) if candidate else 0
        except ValueError: row=0
        year=str(src.get('publication_year') or '')
        # Formatting checks do not establish authorization for titles/names.
        # DOI is displayed only for the two format-checked pinned coordinates,
        # without a link or any claim of publication rights.
        return {'source_title':None,
                'source_creator':None,
                'source_kind':_source_kind(src), 'source_doi':_doi(src.get('doi')) if row in {2,15} else None,
                'source_year':_date(src.get('publication_date') or src.get('published_at')) or (year if re.fullmatch(r'\d{4}',year) else None)}
    def rights(ed):
        decisions={a:[] for a in _ACTIONS}
        ident=ed.get('id')
        right_ids={}
        for layer in layers.values():
            for entry in layer.get('rights',[])+layer.get('rights_delta',[]):
                row=entry['value'];action=row.get('action');decision=row.get('decision')
                if row.get('edition_id')==ident and action in decisions:
                    decisions[action].append(_code(str(decision).lower()))
                    right_ids[row.get('id')]=action
        # Decisions are raw input evidence only; unknown/conditional never grant.
        status={k:(v[0] if len(v)==1 else ('not_recorded' if not v else 'conflicting')) for k,v in decisions.items()}
        overrides=[]
        for layer in layers.values():
            for entry in layer.get('rights_overrides',[]):
                row=entry['value'];action=row.get('action')
                if row.get('baseline_edition_id')==ident and right_ids.get(row.get('baseline_right_id'))==action:
                    overrides.append({'action':_code(action),'previous_decision':_code(row.get('previous_decision')),
                        'new_decision':_code(row.get('new_decision')),
                        'evidence':'recorded' if row.get('evidence_locator_id') else 'missing'})
        return status,overrides
    def passage_rows(row):
        ids=row.get('passage_ids') or []
        result=[]
        for ident in ids if isinstance(ids,list) else []:
            p=lookup(ident,'passages')
            if p:
                corpus=p.get('corpus');scheme=p.get('reference_scheme')
                result.append({'corpus':_CORPORA.get(corpus,'unknown'),'scheme':_scheme(scheme),
                    'reference':_reference(p.get('reference'),corpus,scheme),
                    'alignment_status':'pending'})
        return result
    def editions_for_source(source_id):
        if not source_id:return []
        result=[]
        for layer in layers.values():
            for entry in layer.get('editions',[]):
                edition=entry['value']
                if edition.get('source_id')==source_id:
                    observed,overrides=rights(edition)
                    result.append({'key':coordinates.get(edition.get('id')),'rights':observed,
                                   'rights_overrides':overrides,'effective_permissions':{a:False for a in _ACTIONS}})
        return result
    def relations(ident):
        result=[]
        for layer in layers.values():
            for entry in layer.get('relationships',[])+layer.get('relations',[]):
                row=entry['value'];subject=row.get('subject_id') or row.get('from_claim_id');target=row.get('object_id') or row.get('to_claim_id')
                if subject==ident or target==ident:
                    result.append({'kind':_code(row.get('predicate') or row.get('relation_type')),'status':_code(row.get('status') or row.get('review_status')),
                                   'direction':'outgoing' if subject==ident else 'incoming','target_key':coordinates.get(target if subject==ident else subject),
                                   'assessment':'pending_evidence_review'})
        return result
    def evidence(ident):
        result=[]
        for layer in layers.values():
            for entry in layer.get('evidence',[]):
                row=entry['value']
                if row.get('claim_id')==ident:
                    result.append({'kind':_code(row.get('kind') or row.get('evidence_kind') or row.get('role')),
                                   'status':_code(row.get('status') or row.get('verification_status') or row.get('review_status'))})
        return result
    audits={}
    for entry in layers['d5'].get('claim_scope_audits',[]):
        row=entry['value']; audits.setdefault(row.get('baseline_claim_id'),[]).append((entry,row))
    attestations={}
    for entry in layers['d5'].get('position_attestations',[]):
        row=entry['value'];attestations.setdefault(row.get('baseline_claim_id'),[]).append((entry,row))
    access={}
    for tables in layers.values():
        for entry in tables.get('source_access_events',[]):
            row=entry['value']; locator_id=row.get('source_locator_id') or row.get('locator_id')
            if locator_id: access.setdefault(locator_id,[]).append(row)
    for stage,tables in layers.items():
        for entry in tables.get('claims',[]):
            row=entry['value'];ident=row.get('id');loc,ed,src=source_from_locator(row.get('source_locator_id') or row.get('locator_id'))
            p=passage_rows(row);first=p[0] if p else {}
            original=_code(row.get('attribution_kind'))
            # The original label is not proof of formal adoption.
            attribution='unconfirmed_authority' if original=='official_doctrine' else original
            raw_role=str(row.get('community_id_role') or '').lower()
            # Only an explicit source role can identify the community as the
            # critic's target; attribution alone must not invent a role.
            is_target=('target' in raw_role or '비평 대상' in raw_role)
            role='target' if is_target else 'unspecified'
            checked=_code(row.get('verification_status') or row.get('review_status'))
            meta=metadata(src);right_status,right_overrides=rights(ed)
            audit_rows=audits.get(ident,[])
            if len(audit_rows)==1:
                audit_entry,audit=audit_rows[0]
                quotation=_code(audit.get('quotation_status'))
                argument=_code(audit.get('argument_status'))
                reported_review=_code(audit.get('independent_review_status'))
                audit_key=f'd5:claim_scope_audits:{audit_entry["line"]}'
            else:
                quotation='unknown';argument='not_assessed';reported_review=_code(row.get('independent_review_status'));audit_key=None
            explicit_no_review=(row.get('independent_human_review') is False or row.get('human_review')=='not_performed' or reported_review in ('none','not_done','independent_review_not_done'))
            human_status='independent_review_not_done' if explicit_no_review else 'pending'
            observation=[{'scope':_code(item.get('position_scope')),'verification_status':_code(item.get('verification_status')),
                          'as_of':_date(item.get('stance_as_of')),'summary':None}
                         for _,item in attestations.get(ident,[])]
            mapped={'id','attribution_kind','community_id_role','source_locator_id','locator_id','passage_ids','authority_status','document_authority','verification_status','review_status','checked_at','independent_review_status','independent_human_review','human_review'}
            speaker=None
            if p and any(x.get('reference') is None for x in p): mapped.discard('passage_ids')
            unmapped=sorted({_code(k,'unrecognized_field') for k in row if k not in mapped} | ({'source_title','source_creator'} if src else set()))
            events=access.get(row.get('source_locator_id') or row.get('locator_id'),[])
            events=[item for item in events if (not item.get('source_id') or item['source_id']==src.get('id'))
                    and (not item.get('edition_id') or item['edition_id']==ed.get('id'))]
            access_events=[{'method':_method(item.get('method')),'checked_at':_date(item.get('checked_at')),
                            'result':'redacted_rights_unresolved'} for item in events]
            access_value=loc.get('access_method') or loc.get('source_access_method') or (events[0].get('method') if len(events)==1 else None)
            record={'key':coordinates.get(ident),'stage':stage,'record_kind':'claim','attribution':attribution,'original_attribution':original,
                    'authority_status':'pending_authority','input_authority_status':_code(row.get('authority_status') or row.get('document_authority')),
                    'verification_status':checked,'quotation_status':quotation,'argument_status':argument,
                    'reported_independent_review_status':reported_review,'independent_review_status':human_status,'audit_observation_key':audit_key,
                    'rights_status':'unresolved','rights':right_status,'rights_overrides':right_overrides,'effective_permissions':{a:False for a in _ACTIONS},
                    'tradition':None,'community_reference':None,'community_role':role,
                    'evaluated_subject':None,'researcher':None,
                    'speaker':speaker,'speaker_type':'unknown',
                    'passage_corpus':first.get('corpus'),'passage_scheme':first.get('scheme'),'passage_reference':first.get('reference'),'passages':p,
                    **meta,'access_path':_method(access_value),'access_events':access_events,
                    'locator':_locator(loc.get('location')),'checked_at':_date(row.get('checked_at')),'as_of':None,'valid_from':None,'valid_until':None,
                    'summary':None,'evidence':evidence(ident),'relationships':relations(ident),
                    'attestation_observations':observation,
                    'display_status':'metadata_candidate','field_policy':{'source_metadata':'redacted_rights_unresolved','summary':'redacted_rights_unresolved','locator':'structured_identifier_only'},
                    'unmapped':unmapped}
            if not record['locator']: record['field_policy']['locator']='redacted_rights_unresolved'
            summaries.append(record)
        # Bibliographic records are distinct from claim records; they do not
        # create claims or merge similar works across research stages.
        for entry in tables.get('sources',[]):
            row=entry['value'];ident=row.get('id')
            meta=metadata(row)
            edition_rights=editions_for_source(ident)
            if len(edition_rights)==1:
                source_rights=edition_rights[0]['rights'];source_overrides=edition_rights[0]['rights_overrides'];source_rights_status='unresolved'
            elif edition_rights:
                # No per-action union: decisions belong to individual editions.
                source_rights={a:'unmapped' for a in _ACTIONS};source_overrides=[];source_rights_status='multiple_editions'
            else:
                source_rights={a:'not_recorded' for a in _ACTIONS};source_overrides=[];source_rights_status='not_recorded'
            mapped={'id','kind','bib_type','source_type','checked_at'}
            if meta['source_title'] is not None: mapped.add('title')
            if meta['source_creator'] is not None: mapped.add('creator')
            if meta['source_doi'] is not None: mapped.add('doi')
            if meta['source_year'] is not None: mapped.update(('publication_year','publication_date','published_at'))
            summaries.append({'key':coordinates.get(ident),'stage':stage,'record_kind':'source','attribution':'unknown','original_attribution':'unknown',
                'authority_status':'pending_authority','verification_status':'unknown','quotation_status':'unknown','argument_status':'not_assessed','independent_review_status':'pending',
                'rights_status':source_rights_status,'rights':source_rights,'rights_overrides':source_overrides,
                'edition_rights':edition_rights,'effective_permissions':{a:False for a in _ACTIONS},
                'tradition':None,'community_reference':None,'community_role':'unspecified','evaluated_subject':None,'researcher':meta['source_creator'],'speaker':None,
                'passage_corpus':None,'passage_scheme':None,'passage_reference':None,'passages':[],**meta,
                'access_path':'unknown','locator':None,'checked_at':_date(row.get('checked_at')),'as_of':None,'valid_from':None,'valid_until':None,
                'summary':None,'evidence':[],'relationships':[],'display_status':'metadata_candidate',
                'field_policy':{'source_metadata':'redacted_rights_unresolved','summary':'redacted_rights_unresolved','locator':'redacted_rights_unresolved'},
                'unmapped':sorted(_code(k,'unrecognized_field') for k in row if k not in mapped)})
    return summaries


def load_candidate_archive(path: Path | bytes) -> dict:
    """Load only the pinned user-selected D-8 archive; return safe fields.

    All research bytes live in memory only. Fail closed with a generic error;
    do not reveal source path, payload, record ID or validation exception.
    """
    archives=[]
    try:
        if isinstance(path,bytes):
            if len(path)>64*1024*1024: raise CandidateError('archive_invalid')
            read_input=lambda: path
        else:
            location=os.fspath(path)
            # UNC paths and URL schemes are remote destinations. This check
            # cannot detect a locally mounted remote share or mapped drive.
            if not isinstance(location,str) or location.startswith(('\\\\','//','\\/','/\\')) or re.match(r'^[A-Za-z][A-Za-z0-9+.-]+:',location):
                raise CandidateError('archive_not_local')
            read_input=lambda: prior._bounded_read(path)
        blob=read_input()
        if prior._sha(blob)!=D8_SHA: raise CandidateError('archive_not_recognized')
        errors=collections.Counter()
        z=prior._safe_archive(blob,errors)
        if z is None: raise CandidateError('archive_invalid')
        archives.append(z)
        n=prior._manifest(z,'SHA256SUMS.txt',errors)
        if n!=39 or errors: raise CandidateError('archive_invalid')
        d7blob=z.read('baseline/SCRIPTURA_D7_RESEARCH.zip')
        result=baseline.inspect_archive(d7blob,mode='validate')
        if result.get('status')!='pass': raise CandidateError('baseline_invalid')
        layers,aux=_read_layers(z,errors)
        if errors: raise CandidateError('archive_invalid')
        if any(len(layers['d8'][k])!=v for k,v in D8_COUNTS.items()): raise CandidateError('archive_invalid')
        from .d8_validation import validate_d8
        validation,metrics=validate_d8(layers['d8'],{k:layers[k] for k in ('base','d5','d6','d7')},aux)
        if validation: raise CandidateError('archive_invalid')
        records=_build_projection(layers)
        if prior._sha(read_input())!=D8_SHA: raise CandidateError('archive_changed')
        stage_counts={stage:{table:len(items) for table,items in tables.items()} for stage,tables in layers.items()}
        # Every input table appears here; partial means only selected safe
        # fields may contribute, not that its entire structure was mapped.
        partial_tables={'claims','sources','locators','editions','passages','rights','rights_delta','rights_overrides','evidence','relationships','relations','source_access_events','authority_registries','position_attestations','claim_scope_audits'}
        unmapped_summary={stage:{table:{'input_count':len(items),'mapping':'partial' if table in partial_tables else 'unmapped'}
                            for table,items in tables.items()} for stage,tables in layers.items()}
        return {'dataset':'D8','counts':{'d8':dict(D8_COUNTS),'by_stage':stage_counts,'display_records':len(records)},
            'unmapped_summary':unmapped_summary,'validation_metrics':metrics,
            'warnings':['비공개 연구 후보: 학술적 진실이나 공동체 공식 채택으로 확정하지 않았습니다.',
                        '제목·저자·발화자·공동체 이름은 표시권 및 개인정보 검토 전 가려지며, 이름 검색은 제공하지 않습니다.',
                        '출처 설명과 원문은 권리·표시 범위 검토 전 가립니다.'],
            'facets':{},'records':records}
    except CandidateError:
        raise
    except Exception:
        # No traceback, input path, archive bytes, or record values cross API.
        raise CandidateError('archive_invalid') from None
    finally:
        for z in archives:z.close()
