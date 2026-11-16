"""Synthetic Windows acceptance checks; no private ZIPs or real models."""
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import c04_windows_acceptance as acceptance


def answers(*values):
    it = iter(values)
    return lambda _: next(it)


class WindowsAcceptanceTest(unittest.TestCase):
    def test_wrong_platform_is_not_windows_acceptance(self):
        self.assertEqual(acceptance.main(platform='linux', is_tty=True), 2)

    def test_cancellation_does_not_run_or_assume_a_model(self):
        with patch.object(acceptance, 'local_model_available', side_effect=AssertionError):
            self.assertEqual(acceptance.main(platform='win32', is_tty=True,
                                             choose=lambda _: ''), 0)

    def test_unavailable_model_does_not_run_inference(self):
        calls = []
        def replay(canonical, audit, **kwargs):
            calls.append(kwargs)
            return {'questions': 50, 'model_called': 0, 'model_responded': 0, 'not_run': 50}
        selections = iter(['C:/private/canonical.zip', 'C:/private/qa.zip'])
        out = StringIO()
        with redirect_stdout(out):
            code = acceptance.main(platform='win32', is_tty=True,
                ask=answers('y', 'model', 'y', 'n'), choose=lambda _: next(selections),
                load=lambda _: None, probe=lambda _: False, replay=replay)
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 1)
        self.assertIsNone(calls[0]['model'])
        self.assertIsNone(calls[0]['output'])
        self.assertTrue(callable(calls[0]['progress']))
        self.assertIn('HTTP 호출 시도: 0', out.getvalue())
        self.assertIn('미실행: 50', out.getvalue())
        self.assertNotIn('C:/private', out.getvalue())

    def test_actual_run_requires_explicit_choice_and_private_output(self):
        with TemporaryDirectory() as folder:
            outpath = str(Path(folder) / 'result.jsonl')
            calls = []
            def replay(canonical, audit, **kwargs):
                calls.append(kwargs)
                return {'questions': 50, 'model_called': 1, 'model_responded': 1, 'not_run': 49}
            selections = iter(['C:/private/canonical.zip', 'C:/private/qa.zip'])
            output = StringIO()
            with redirect_stdout(output):
                code = acceptance.main(platform='win32', is_tty=True,
                    ask=answers('y', 'localmodel', 'y', 'y', 'n'),
                    choose=lambda _: next(selections), save=lambda: outpath,
                    load=lambda _: None, probe=lambda _: True, replay=replay)
            self.assertEqual(code, 0)
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0]['model'], 'localmodel')
            self.assertEqual(calls[0]['output'], outpath)
            self.assertTrue(callable(calls[0]['progress']))
            self.assertIn('HTTP 호출 시도: 1', output.getvalue())
            self.assertNotIn(outpath, output.getvalue())
            self.assertIn('독립 학술 채점: NOT_RUN', output.getvalue())

    def test_output_must_not_be_existing_repo_or_network(self):
        with TemporaryDirectory() as folder:
            repo = Path(folder) / 'repo'
            repo.mkdir()
            existing = Path(folder) / 'existing.jsonl'
            existing.touch()
            self.assertFalse(acceptance._private_output(str(existing), repo=repo))
            self.assertFalse(acceptance._private_output(str(repo / 'results.jsonl'), repo=repo))
            self.assertFalse(acceptance._private_output('\\\\server\\results.jsonl', repo=repo))
            self.assertTrue(acceptance._private_output(str(Path(folder) / 'new.jsonl'), repo=repo))

    def test_windows_drive_type_fails_closed_for_network_and_unknown(self):
        path = 'Z:\\private\\output.jsonl'
        self.assertFalse(acceptance._resolved_windows_path_allowed(path, lambda _: 4))
        self.assertFalse(acceptance._resolved_windows_path_allowed(path, lambda _: 0))
        self.assertTrue(acceptance._resolved_windows_path_allowed(path, lambda _: 3))
        self.assertFalse(acceptance._resolved_windows_path_allowed('\\\\server\\share\\out.jsonl', lambda _: 3))

    def test_malformed_benchmark_summary_never_claims_pass(self):
        selections = iter(['C:/private/canonical.zip', 'C:/private/qa.zip'])
        out = StringIO()
        with redirect_stdout(out):
            code = acceptance.main(platform='win32', is_tty=True,
                ask=answers('n', 'y'), choose=lambda _: next(selections),
                load=lambda _: None, replay=lambda *args, **kwargs: {
                    'questions': 50, 'model_called': 51, 'model_responded': 51, 'not_run': 0})
        self.assertEqual(code, 1)
        self.assertNotIn('HTTP 호출 시도: 51', out.getvalue())
        self.assertIn('NOT_RUN', out.getvalue())

    def test_failure_does_not_print_private_exception(self):
        output = StringIO()
        def fail(_):
            raise ValueError('PRIVATE SECRET')
        with redirect_stdout(output):
            code = acceptance.main(platform='win32', is_tty=True,
                                   choose=lambda _: 'C:/private/canonical.zip', load=fail)
        self.assertEqual(code, 1)
        self.assertNotIn('PRIVATE SECRET', output.getvalue())
        self.assertNotIn('C:/private', output.getvalue())
        self.assertIn('NOT_RUN', output.getvalue())

    def test_probe_uses_only_shared_local_model_discovery(self):
        with patch('c04_ollama.list_local_models', return_value={
                'status': 'ready', 'models': ['model:one'], 'unsupported_count': 0}):
            self.assertTrue(acceptance.local_model_available('model:one'))
            self.assertFalse(acceptance.local_model_available('other'))
            self.assertFalse(acceptance.local_model_available('http://example.invalid'))


if __name__ == '__main__':
    unittest.main()
