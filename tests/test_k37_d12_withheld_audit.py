import json
import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from k37_bridge.d12_withheld_audit import audit_d12_withheld
from audit_d12_withheld import main as audit_main

SENTINEL = 'SYNTHETIC_SECRET_PRIVATE_VALUE'


def make(rows):
    layers = {'d12': {'claims': [{'line': i + 1, 'value': row} for i, row in enumerate(rows)]}}
    records = [{'key': f'd12:claims:{i + 1}', 'stage': 'd12', 'record_kind': 'claim'} for i in range(len(rows))]
    return layers, {'dataset': 'D12', 'records': records, '_k2_summary_index': object()}


class WithheldAuditTests(unittest.TestCase):
    def test_overlapping_reasons_and_per_card_explanation(self):
        layers, dataset = make([{}, {'verification_method': '자체 요약 인용 없이'},
                                {'verification_method': '자체 요약 인용 없이', 'original_text_stored': False}])
        with patch('k37_bridge.d12_withheld_audit.summary_for_record', return_value=None):
            audit = audit_d12_withheld(layers, dataset)
        self.assertEqual(audit.for_record('d12:claims:1'), ('self_or_nonquote_not_attested', 'original_storage_not_explicitly_false'))
        self.assertEqual(audit.for_record('d12:claims:2'), ('original_storage_not_explicitly_false',))
        self.assertEqual(audit.for_record('d12:claims:3'), ('other_safety_gate',))
        self.assertEqual(audit.summary()['withheld'], 3)

    def test_displayed_status_comes_only_from_existing_sealed_gate(self):
        layers, dataset = make([{'verification_method': '자체 요약 인용 없이', 'original_text_stored': False}])
        with patch('k37_bridge.d12_withheld_audit.summary_for_record', return_value=SENTINEL):
            audit = audit_d12_withheld(layers, dataset)
        self.assertEqual(audit.summary()['displayed'], 1)
        self.assertEqual(audit.for_record('d12:claims:1'), ())
        self.assertNotIn(SENTINEL, repr(audit) + json.dumps(audit.summary()))

    def test_invalid_and_duplicate_do_not_leak_values(self):
        layers, dataset = make([{'id': SENTINEL}])
        layers['d12']['claims'][0]['line'] = SENTINEL
        with self.assertRaises(ValueError) as error:
            audit_d12_withheld(layers, dataset)
        self.assertEqual(str(error.exception), 'd12_withheld_audit_unavailable')
        self.assertNotIn(SENTINEL, str(error.exception))
        layers, dataset = make([{}])
        layers['d12']['claims'].append(layers['d12']['claims'][0])
        with self.assertRaises(ValueError):
            audit_d12_withheld(layers, dataset)

    def test_untrusted_keys_are_not_accepted(self):
        layers, dataset = make([{}])
        with patch('k37_bridge.d12_withheld_audit.summary_for_record', return_value=None):
            audit = audit_d12_withheld(layers, dataset)
        self.assertEqual(audit.for_record(SENTINEL), ())
        self.assertEqual(audit.for_record('d12:claims:0'), ())

    def test_missing_projection_is_separately_counted(self):
        layers, dataset = make([{}])
        dataset['records'] = []
        with patch('k37_bridge.d12_withheld_audit.summary_for_record', return_value=None):
            audit = audit_d12_withheld(layers, dataset)
        self.assertEqual(audit.summary()['card_unmapped'], 1)
        self.assertEqual(audit.for_record('d12:claims:1'), ('card_unmapped',))

    def test_cli_errors_never_echo_paths_or_exception(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(audit_main([SENTINEL]), 1)
            self.assertEqual(audit_main(['https://example.invalid/' + SENTINEL]), 1)
        self.assertNotIn(SENTINEL, output.getvalue())
        self.assertEqual(output.getvalue().count('d12_withheld_audit_unavailable'), 2)

    def test_cli_produces_only_fixed_aggregate(self):
        layers, dataset = make([{}])
        output = io.StringIO()
        with patch('audit_d12_withheld._bounded_read', return_value=b'synthetic'), \
             patch('audit_d12_withheld._sha', return_value='synthetic'), \
             patch('audit_d12_withheld.D12_SHA', 'synthetic'), \
             patch('audit_d12_withheld.load_k2_archive', return_value=dataset), \
             patch('audit_d12_withheld._read_layers', return_value=(layers, b'')), \
             patch('k37_bridge.d12_withheld_audit.summary_for_record', return_value=None), \
             contextlib.redirect_stdout(output):
            self.assertEqual(audit_main(['synthetic.zip']), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result['withheld'], 1)
        self.assertTrue(result['archive_unchanged'])
        self.assertNotIn(SENTINEL, output.getvalue())

    def test_cli_accepts_windows_drive_path_and_rejects_unc(self):
        layers, dataset = make([{}])
        output = io.StringIO()
        with patch('audit_d12_withheld._bounded_read', return_value=b'synthetic'), \
             patch('audit_d12_withheld._sha', return_value='synthetic'), \
             patch('audit_d12_withheld.D12_SHA', 'synthetic'), \
             patch('audit_d12_withheld.load_k2_archive', return_value=dataset), \
             patch('audit_d12_withheld._read_layers', return_value=(layers, b'')), \
             patch('k37_bridge.d12_withheld_audit.summary_for_record', return_value=None), \
             contextlib.redirect_stdout(output):
            self.assertEqual(audit_main([r'C:\Private\synthetic.zip']), 0)
            self.assertEqual(audit_main([r'\\server\private\synthetic.zip']), 1)
        self.assertNotIn('Private', output.getvalue())
        self.assertNotIn('server', output.getvalue())

if __name__ == '__main__':
    unittest.main()
