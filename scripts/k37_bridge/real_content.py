"""In-memory D13/D14 candidate labels and independently gated content.

The archive supplies no authority to publish. Missing field-level attestations
remain pending; this module does not infer theology or a person's affiliation.
"""
from collections.abc import Mapping
import re
import unicodedata
from k13_bridge.local_candidate import LocalCandidateIndex, _field, _flags, _display_restriction

_DENY = frozenset(('denied','deny','prohibited','restricted','blocked','conditional',
                   'not_allowed','not_permitted','not_granted','disallowed','disallow',
                   'forbidden','rejected','private','confidential','sensitive','personal',
                   'do_not_display','non_public'))
_TOKEN = object()

def _code(value):
    return re.sub(r'[\s-]+','_',value.strip().casefold())

class RealContentIndex:
    __slots__ = ('__values',)
    def __init__(self, token, values):
        if token is not _TOKEN: raise ValueError('content_index_untrusted')
        self.__values = values
    def __repr__(self): return '<RealContentIndex redacted>'
    def get(self, key): return dict(self.__values.get(key, {}))


def content_for_record(index, dataset, key):
    """Only return values vetted by this module; no raw ID is ever returned."""
    if type(index) is not RealContentIndex or dataset != 'D16' or not isinstance(key,str):
        return {}
    return index.get(key)


def _records(layers, table):
    for tables in layers.values():
        if not isinstance(tables, dict): continue
        for entry in tables.get(table, []):
            obj=entry.get('value') if isinstance(entry,dict) else None
            if isinstance(obj,dict): yield obj


def _unique_index(layers, table):
    found={}; conflicts=set()
    for obj in _records(layers,table):
        ident=obj.get('id')
        if not isinstance(ident,str) or not ident: continue
        if ident in found and found[ident] != obj: conflicts.add(ident)
        else: found[ident]=obj
    for ident in conflicts: found.pop(ident,None)
    return found


def _restricted(objects, aliases):
    for obj in objects:
        if _flags(obj): return True
        for name in ('restricted_fields','private_fields','personal_fields','sensitive_fields'):
            members=obj.get(name)
            if isinstance(members,(list,tuple,set)) and any(x in members for x in aliases):return True
        rules=obj.get('field_restrictions')
        if isinstance(rules,dict):
            for name in aliases:
                value=rules.get(name)
                if value is True or (isinstance(value,str) and _code(value) in _DENY):return True
    return False


def _prohibited(rights, actions):
    if _display_restriction(rights): return True
    guarded = set(actions) | {'browse','display_metadata','metadata_display','local_display','private_display','display'}
    for item in rights:
        action=_code(str(item.get('action','')))
        if action in guarded:
            for key in ('decision','new_decision','permission'):
                value=item.get(key)
                if value is not None and (not isinstance(value,str) or _code(value) in _DENY):return True
    return False


def _text_safe(value, protected, maxlen):
    if not isinstance(value,str) or not value.strip() or len(value)>maxlen:return False
    if any(x in value for x in ('“','”','"','「','」','\n','\r')):return False
    if _field(value,'source_title').get('status')!='recorded_unverified':return False
    candidate = unicodedata.normalize('NFKC', value).casefold()
    return not any(unicodedata.normalize('NFKC', name).casefold() in candidate for name in protected)


def _attested(method, stored):
    # Match the existing K2 independently defined self-authored/non-quotation
    # gate. A general archive note or ambiguous status is never sufficient.
    return (isinstance(method,str) and all(x in method for x in ('자체 요약','인용 없이'))
            and not any(x in method for x in ('아님','금지','불가','아니','미확인'))
            and stored is False)


def apply_k2_review_restrictions(layers, records, summary_index, tradition_index):
    """Apply newly validated restrictions to previously sealed D12 values.

    This derives new sealed indices without mutating the baseline indices. It
    can only remove already eligible values; it cannot authorize new content.
    """
    from k2_bridge.receipt import (_SummaryIndex, _TraditionIndex,
                                  summary_for_record, tradition_for_record)
    if not isinstance(layers, Mapping) or not isinstance(records, list):
        raise ValueError('content_index_unavailable')
    d12 = layers.get('d12', {})
    if not isinstance(d12, Mapping):
        raise ValueError('content_index_unavailable')
    claims = {f'd12:claims:{entry["line"]}': entry['value']
              for entry in d12.get('claims', []) if isinstance(entry, dict)
              and type(entry.get('line')) is int and isinstance(entry.get('value'), dict)}
    # The prior K2 projection is scoped to the D12 layer. Older snapshots may
    # legitimately contain a different historical version of the same ID.
    d12_only = {'d12': d12}
    locators = _unique_index(d12_only, 'locators')
    editions = _unique_index(d12_only, 'editions')
    sources = _unique_index(d12_only, 'sources')
    d16 = layers.get('d16', {})
    entries = d16.get('rights_actions', []) if isinstance(d16, Mapping) else []
    rights = [entry['value'] for entry in entries if isinstance(entry, dict)
              and isinstance(entry.get('value'), dict)]
    summaries, traditions = {}, {}
    for record in records:
        if not isinstance(record, dict):
            continue
        key = record.get('key')
        claim = claims.get(key)
        if not isinstance(claim, dict):
            continue
        locator = locators.get(claim.get('source_locator_id') or claim.get('locator_id'))
        edition = editions.get(locator.get('edition_id')) if isinstance(locator, dict) else None
        source = sources.get(locator.get('source_id')) if isinstance(locator, dict) else None
        if not isinstance(edition, dict) or not isinstance(source, dict) or edition.get('source_id') != source.get('id'):
            continue
        related = [right for right in rights
                   if right.get('source_id') == source.get('id') and right.get('edition_id') == edition.get('id')]
        summary = summary_for_record(summary_index, 'D12', key)
        summary_aliases = ('statement_ko', 'summary', 'summary_ko', 'own_summary')
        if (isinstance(summary, str) and not _restricted(related, summary_aliases)
                and not _prohibited(related, summary_aliases + ('display_summary', 'local_summary'))):
            summaries[key] = summary
        tradition = tradition_for_record(tradition_index, 'D12', key)
        tradition_aliases = ('tradition', 'community_name')
        if (isinstance(tradition, str) and not _restricted(related, tradition_aliases)
                and not _prohibited(related, tradition_aliases + ('display_tradition',))):
            traditions[key] = tradition
    return _SummaryIndex(summaries), _TraditionIndex(traditions)


def build_content_index(layers, additions, candidate_index):
    """Build a sealed D16 projection; actual content is never logged or saved.

    Each statement/reasoning requires a validated source chain and individual
    restriction checks. With a missing self-authorship attestation, short
    candidate input is available only as 'local_input_candidate': not a verified
    paraphrase, rights grant, official position or scholarly review. An
    attested self-summary remains separately 'recorded_unverified'.
    Recorded tradition is a label, never a verified speaker or doctrine.
    """
    if not isinstance(layers,Mapping) or not isinstance(additions,list) or type(candidate_index) is not LocalCandidateIndex:
        raise ValueError('content_index_unavailable')
    sources=_unique_index(layers,'sources'); editions=_unique_index(layers,'editions'); locators=_unique_index(layers,'locators')
    rights=list(_records(layers,'rights'))+list(_records(layers,'rights_actions'))+list(_records(layers,'rights_overrides'))
    evidence=list(_records(layers,'evidence'))
    protected=[]
    for table,field in (('agents','name'),('communities','canonical_name')):
        for row in _records(layers,table):
            value=row.get(field)
            if _flags(row) and isinstance(value,str) and value.strip():protected.append(value.strip().casefold())
    claims={}
    for stage in ('d12','d13','d14'):
        tables=layers.get(stage,{})
        for entry in tables.get('claims',[]) if isinstance(tables,dict) else ():
            if isinstance(entry,dict) and type(entry.get('line')) is int and isinstance(entry.get('value'),dict):
                claims[f'{stage}:claims:{entry["line"]}']=entry['value']
    out={}
    for record in additions:
        if not isinstance(record,dict):continue
        key=record.get('key'); row=claims.get(key)
        if not isinstance(key,str) or not isinstance(row,dict):continue
        locid=row.get('source_locator_id') or row.get('locator_id'); loc=locators.get(locid)
        if not isinstance(loc,dict):continue
        edition=editions.get(loc.get('edition_id'));source=sources.get(loc.get('source_id'))
        if not isinstance(edition,dict) or not isinstance(source,dict) or edition.get('source_id')!=source.get('id'):continue
        if row.get('source_id') and row['source_id']!=source.get('id'):continue
        if row.get('edition_id') and row['edition_id']!=edition.get('id'):continue
        objects=(row,source,edition,loc)
        related=[]
        for x in rights:
            right_edition=x.get('edition_id') or x.get('baseline_edition_id')
            right_source=x.get('source_id') or x.get('baseline_source_id')
            right_locator=x.get('source_locator_id') or x.get('locator_id')
            # A source-wide rule applies to all editions. More specific rules
            # must match every supplied part of the source/edition/locator.
            if (not (right_edition or right_source or right_locator)
                    or (right_edition and right_edition!=edition.get('id'))
                    or (right_source and right_source!=source.get('id'))
                    or (right_locator and right_locator!=locid)):
                continue
            related.append(x)
        # Field-level privacy/restriction declarations in linked rights rows
        # apply just like declarations on the claim, edition and locator.
        objects += tuple(related)
        title=candidate_index.for_record('D16',key).get('source_title',{})
        if title.get('status') not in ('recorded_unverified','source_confirmed'):continue
        result={'summary':None,'summary_status':'pending_review','reasoning':None,'reasoning_status':'pending_review',
                'subject':None,'subject_status':'pending','reported_speaker':None,'reported_speaker_status':'pending',
                'tradition':None,'tradition_status':'pending'}
        # A recorded speaker string is explicitly labelled as a source claim;
        # it does not establish a verified speaker, membership or adoption.
        speaker=row.get('speaker')
        if (_text_safe(speaker,protected,120) and not _restricted(objects,('speaker','speaker_name','claim_speaker'))
                and not _prohibited(related,('speaker','speaker_name','claim_speaker','display_speaker'))):
            result['reported_speaker']=speaker.strip();result['reported_speaker_status']='recorded_unverified'
        # Recorded labels may be searched locally but never represent verified
        # speaker, affiliation, or community doctrine.
        tradition=row.get('tradition')
        if (_text_safe(tradition,protected,120) and not _restricted(objects,('tradition','community_name'))
                and not _prohibited(related,('tradition','community_name','display_tradition'))):
            result['tradition']=tradition.strip();result['tradition_status']='recorded_unverified'
        matches=[e for e in evidence if e.get('claim_id')==row.get('id') and (e.get('locator_id') or e.get('source_locator_id'))==locid]
        if len(matches)==1:
            fields=(('summary','statement_ko','verification_method','original_text_stored','statement_original_quote',('statement_ko','summary','summary_ko','own_summary')),
                    ('reasoning','reasoning_ko','reasoning_verification_method','reasoning_original_text_stored','reasoning_original_quote',('reasoning_ko','reasoning','argument','own_reasoning')))
            for target,raw,method,stored,quote,aliases in fields:
                value=row.get(raw)
                # There are two distinct *private-local* states. A row with
                # field-level provenance is a recorded self-summary candidate;
                # a short input note missing those attestations is readable
                # only as an UNREVIEWED INPUT NOTE. This is never a rights
                # grant, verified attribution, scholarly conclusion or quote
                # clearance. Explicit original-text storage/quote flags and
                # all linked field-level restrictions continue to deny display.
                if (not row.get(quote) and row.get(stored) is not True
                    and row.get('original_text_stored') is not True
                    and _text_safe(value,protected,500)
                    and not _restricted(objects,aliases)
                    and not _prohibited(related,tuple(aliases)+('display_'+target,'local_'+target))):
                    result[target]=value.strip()
                    result[target+'_status']=('recorded_unverified'
                        if _attested(row.get(method),row.get(stored))
                        else 'local_input_candidate')
        out[key]=result
    return RealContentIndex(_TOKEN,out)
