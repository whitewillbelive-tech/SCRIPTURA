"""Future display-evidence contract exercised with synthetic fixtures only.

No server/CLI uses this function to unmask actual data. The example.invalid
origin and synthetic identifiers prohibit treating an arbitrary asserted JSON
record as authenticated Work evidence. A future real adapter needs its own
provenance/authentication gate and review.
"""
from datetime import date
from urllib.parse import urlsplit

_REQUIRED=('entity_id','field_group','display_field','transformation','edition_id','locator_id',
 'direct_evidence_url','rights_basis','action','purpose','jurisdiction','reviewed_at','reviewer',
 'limitations','source_verification_method','decision','valid_from','valid_until','rights_decision')
_ALLOWED_FIELDS={'source_title','source_creator','researcher','speaker','community_name'}

def _day(v):
 try:
  if not isinstance(v,str) or len(v)!=10:return None
  parsed=date.fromisoformat(v)
  return parsed if parsed.isoformat()==v else None
 except (TypeError,ValueError):return None

def synthetic_field_is_eligible(record, request, *, today):
 """Return a boolean only; no evidence URL, text, ID, or record is emitted."""
 if not isinstance(record,dict) or not isinstance(request,dict):return False
 if any(not isinstance(record.get(k),str) or not record[k].strip() for k in _REQUIRED):return False
 # This gate is intentionally not a real Work approval mechanism.
 if any(not record[k].startswith('synthetic:') for k in ('entity_id','edition_id','locator_id','reviewer')):return False
 try:
  u=urlsplit(record['direct_evidence_url'])
  if u.scheme!='https' or u.hostname!='example.invalid' or u.username or u.password or u.port not in (None,443) or not u.path or u.path=='/':return False
 except ValueError:return False
 if record['field_group']!='bibliography' or record['display_field'] not in _ALLOWED_FIELDS:return False
 if record['transformation']!='identity' or record['action']!='browse' or record['rights_decision']!='allowed':return False
 if record['purpose']!='private_local_candidate_review_only' or record['decision']!='candidate_visible_local':return False
 if record['source_verification_method'] not in ('direct_checked','translation_checked'):return False
 if record['jurisdiction'] in ('unknown','unverified','pending'):return False
 if record['rights_basis'] in ('unknown','unverified','pending') or record['limitations'] in ('unknown','unverified','pending'):return False
 if any(request.get(k)!=record[k] for k in ('entity_id','field_group','display_field','transformation','edition_id','locator_id','action','purpose','jurisdiction')):return False
 start,end,reviewed,requested=_day(record['valid_from']),_day(record['valid_until']),_day(record['reviewed_at']),_day(today)
 return bool(start and end and reviewed and requested and start<=reviewed<=requested and start<=requested<=end)
