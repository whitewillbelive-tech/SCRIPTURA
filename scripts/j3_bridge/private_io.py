"""Sensitive in-memory data guards; never log or stringify input structures."""
from collections import Counter
from collections.abc import MutableMapping
from contextlib import redirect_stderr, redirect_stdout
import json
from threading import RLock
from j2_bridge import candidate_readonly as base

class _DiscardText:
 def write(self,value):return len(value)
 def flush(self):pass
 def isatty(self):return False

_PRIVATE_READ_LOCK=RLock()
_DISCARD=_DiscardText()

class PrivateMapping(MutableMapping):
 """Opaque top-level data carrier; explicit reads remain private.

 This prevents accidental stringification and generic JSON serialization of
 an entire layer mapping. It is not a sandbox: accessed nested values remain
 sensitive and must never be printed, logged, or included in exceptions.
 """
 __slots__=('__data',)
 def __init__(self,data):
  if type(data) is not dict:raise ValueError('private_mapping_shape_invalid')
  self.__data=data
 def __getitem__(self,key):
  try:return self.__data[key]
  except Exception:raise KeyError('private_mapping_key_missing') from None
 def __setitem__(self,key,value):self.__data[key]=value
 def __delitem__(self,key):
  try:del self.__data[key]
  except Exception:raise KeyError('private_mapping_key_missing') from None
 def __iter__(self):return iter(self.__data)
 def __len__(self):return len(self.__data)
 def __repr__(self):return '<PrivateMapping redacted>'
 __str__=__repr__

class PrivateLayers:
 """Named, deliberately opaque carrier of private layers and auxiliary rows."""
 __slots__=('layers','auxiliary','error_count')
 def __init__(self,layers,auxiliary,error_count):
  if not isinstance(layers,dict) or not isinstance(auxiliary,dict) or not isinstance(error_count,int) or isinstance(error_count,bool):
   raise ValueError('private_layer_shape_invalid')
  self.layers=PrivateMapping(layers);self.auxiliary=PrivateMapping(auxiliary);self.error_count=error_count
 def __repr__(self):return '<PrivateLayers redacted>'

# Output values must be generated independently from the input. Neither
# caller-chosen labels nor strings are permitted in a diagnostic record.
_COUNT_FIELDS=frozenset(('records_total','claims_total','sources_total','validation_errors','eligibility_total','candidate_fields','approved_fields'))
_CHECK_FIELDS=frozenset(('archive_valid','input_unchanged','references_valid','duplicate_free','boundary_pass'))

def safe_diagnostic(values):
 """Render a bounded aggregate with fixed labels, integers and booleans only.

 Never pass source strings, paths, identifiers, exceptions, or records. This
 function validates shape without including rejected values in its error.
 """
 if type(values) is not dict:raise ValueError('invalid_private_diagnostic')
 if any(type(key) is not str or key not in _COUNT_FIELDS|_CHECK_FIELDS for key in values):
  raise ValueError('invalid_private_diagnostic')
 for key,value in values.items():
  if key in _COUNT_FIELDS:
   if type(value) is not int or not 0<=value<=1000000:raise ValueError('invalid_private_diagnostic')
  elif type(value) is not bool:raise ValueError('invalid_private_diagnostic')
 return json.dumps(values,sort_keys=True,separators=(',',':'),ensure_ascii=True)

def safe_error_count(counter):
 """Accept a Counter only and return a number, never input keys or data."""
 if type(counter) is not Counter:raise ValueError('invalid_error_counter')
 if any(k not in {'record_file_missing','blank_jsonl_line','invalid_jsonl'} for k in counter):raise ValueError('invalid_error_counter')
 if any(not isinstance(v,int) or isinstance(v,bool) or v<0 for v in counter.values()):raise ValueError('invalid_error_counter')
 return sum(counter.values())

def read_checked_d8_layers(archive):
 errors=Counter()
 try:
  # Defensive suppression for accidental Python-level print calls in the
  # reader. Redirection is process-wide; callers must avoid concurrent console
  # use. Native fd writes, nested values and external tools are not sandboxed.
  with _PRIVATE_READ_LOCK,redirect_stdout(_DISCARD),redirect_stderr(_DISCARD):
   result=base._read_layers(archive,errors)
  if not isinstance(result,tuple) or len(result)!=2:raise ValueError('private_layer_shape_invalid')
  layers,auxiliary=result
  return PrivateLayers(layers,auxiliary,safe_error_count(errors))
 except Exception:
  raise ValueError('private_layer_read_failed') from None
