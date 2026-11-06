"""Sensitive in-memory data guards; never log or stringify input structures."""
from collections import Counter
from j2_bridge import candidate_readonly as base

class PrivateLayers:
 """Named, deliberately opaque carrier of private layers and auxiliary rows."""
 __slots__=('layers','auxiliary','error_count')
 def __init__(self,layers,auxiliary,error_count):
  if not isinstance(layers,dict) or not isinstance(auxiliary,dict) or not isinstance(error_count,int) or isinstance(error_count,bool):
   raise ValueError('private_layer_shape_invalid')
  self.layers=layers;self.auxiliary=auxiliary;self.error_count=error_count
 def __repr__(self):return '<PrivateLayers redacted>'

def safe_error_count(counter):
 """Accept a Counter only and return a number, never input keys or data."""
 if type(counter) is not Counter:raise ValueError('invalid_error_counter')
 if any(k not in {'record_file_missing','blank_jsonl_line','invalid_jsonl'} for k in counter):raise ValueError('invalid_error_counter')
 if any(not isinstance(v,int) or isinstance(v,bool) or v<0 for v in counter.values()):raise ValueError('invalid_error_counter')
 return sum(counter.values())

def read_checked_d8_layers(archive):
 errors=Counter()
 try:
  result=base._read_layers(archive,errors)
  if not isinstance(result,tuple) or len(result)!=2:raise ValueError('private_layer_shape_invalid')
  layers,auxiliary=result
  return PrivateLayers(layers,auxiliary,safe_error_count(errors))
 except Exception:
  raise ValueError('private_layer_read_failed') from None
