"""Synthetic-only tests for K-1 private-data output boundaries."""
import contextlib
import io
import json
import sys
import traceback
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from j2_bridge.candidate_readonly import CandidateError
from j3_bridge.candidate_archive import load_versioned_archive
from j3_bridge.private_io import PrivateLayers, read_checked_d8_layers, safe_diagnostic

SENTINEL='SYNTHETIC_PRIVATE_SENTINEL_7cfa'

class PrivateBoundaryTests(unittest.TestCase):
 def test_both_private_maps_refuse_string_and_generic_json(self):
  snapshot=PrivateLayers({'nested':{'secret':SENTINEL}},{'row':SENTINEL},0)
  for value in (snapshot,snapshot.layers,snapshot.auxiliary):
   self.assertNotIn(SENTINEL,repr(value))
   self.assertNotIn(SENTINEL,str(value))
   with self.assertRaises(TypeError) as caught:json.dumps(value)
   self.assertNotIn(SENTINEL,str(caught.exception))

 def test_intentional_nested_access_remains_available(self):
  snapshot=PrivateLayers({'a':{'b':SENTINEL}},{'row':SENTINEL},0)
  self.assertEqual(snapshot.layers['a']['b'],SENTINEL)
  snapshot.layers['next']={'value':1}
  self.assertEqual(snapshot.layers['next']['value'],1)
  self.assertEqual(snapshot.auxiliary['row'],SENTINEL)

 def test_missing_key_never_enters_exception_or_traceback(self):
  data=PrivateLayers({}, {}, 0).layers
  with self.assertRaises(KeyError) as caught:data[SENTINEL]
  self.assertNotIn(SENTINEL,''.join(traceback.format_exception(caught.exception)))

 def test_printed_reader_values_are_discarded(self):
  def noisy_reader(_archive,_errors):
   print(SENTINEL);print(SENTINEL,file=sys.stderr)
   return ({'row':SENTINEL},{'row':SENTINEL})
  out=io.StringIO();err=io.StringIO()
  with patch('j3_bridge.private_io.base._read_layers',side_effect=noisy_reader),contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
   snapshot=read_checked_d8_layers(None)
  self.assertEqual(snapshot.error_count,0)
  self.assertNotIn(SENTINEL,out.getvalue()+err.getvalue())

 def test_reader_failure_is_generic_even_in_traceback(self):
  out=io.StringIO();err=io.StringIO()
  with patch('j3_bridge.private_io.base._read_layers',side_effect=RuntimeError(SENTINEL)),contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
   with self.assertRaises(ValueError) as caught:read_checked_d8_layers(None)
  self.assertNotIn(SENTINEL,''.join(traceback.format_exception(caught.exception))+out.getvalue()+err.getvalue())

 def test_archive_exceptions_are_whitelisted(self):
  with patch('j3_bridge.candidate_archive.prior._bounded_read',side_effect=CandidateError(SENTINEL)):
   with self.assertRaises(CandidateError) as caught:load_versioned_archive('synthetic.zip')
  self.assertEqual(str(caught.exception),'archive_invalid')
  self.assertNotIn(SENTINEL,''.join(traceback.format_exception(caught.exception)))
  with patch('j3_bridge.candidate_archive.prior._bounded_read',side_effect=CandidateError('archive_changed')):
   with self.assertRaises(CandidateError) as caught:load_versioned_archive('synthetic.zip')
  self.assertEqual(str(caught.exception),'archive_changed')

 def test_diagnostics_allow_only_fixed_keys_bounded_counts_and_booleans(self):
  result=safe_diagnostic({'records_total':528,'boundary_pass':True})
  self.assertEqual(json.loads(result),{'records_total':528,'boundary_pass':True})
  for invalid in ({SENTINEL:1},{'records_total':SENTINEL},{'boundary_pass':1},
                  {'records_total':True},{'records_total':-1},{'records_total':1000001},
                  {'unknown':SENTINEL},[SENTINEL]):
   with self.subTest(kind=type(invalid).__name__):
    with self.assertRaises(ValueError) as caught:safe_diagnostic(invalid)
    self.assertEqual(str(caught.exception),'invalid_private_diagnostic')
    self.assertNotIn(SENTINEL,''.join(traceback.format_exception(caught.exception)))

if __name__=='__main__':unittest.main()
