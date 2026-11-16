"""Synthetic coverage of the preserved Windows canonical launcher."""
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import c03_windows_launcher as launcher


def answers(*values):
    iterator = iter(values)
    return lambda _: next(iterator)


class CanonicalLauncherTest(unittest.TestCase):
    def run_launcher(self, *, prompts, models, local=True):
        calls = []
        output = StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            result = launcher.main(platform='win32', is_tty=True,
                chooser=lambda: 'C:/private/canonical.zip', ask=answers(*prompts),
                discover=lambda: models, local_path=lambda _: local,
                app=lambda args: calls.append(args) or 0)
        self.assertNotIn('C:/private/canonical.zip', output.getvalue())
        return result, calls, output.getvalue()

    def test_numeric_model_choice_is_passed_only_after_opt_in(self):
        code, calls, _ = self.run_launcher(prompts=('y', '2'), models={
            'status': 'ready', 'models': ['one', 'two']})
        self.assertEqual(code, 0)
        self.assertEqual(calls, [['--canonical', 'C:/private/canonical.zip', '--local-model', 'two']])

    def test_manual_model_choice_requires_installed_model(self):
        code, calls, _ = self.run_launcher(prompts=('y', 'm', 'one'), models={
            'status': 'ready', 'models': ['one']})
        self.assertEqual(code, 0)
        self.assertEqual(calls[0][-2:], ['--local-model', 'one'])
        code, calls, _ = self.run_launcher(prompts=('y', 'm', 'other'), models={
            'status': 'ready', 'models': ['one']})
        self.assertEqual(code, 0)
        self.assertEqual(calls[0], ['--canonical', 'C:/private/canonical.zip'])

    def test_unavailable_server_starts_without_a_model(self):
        code, calls, out = self.run_launcher(prompts=('y',), models={'status': 'unavailable'})
        self.assertEqual(code, 0)
        self.assertEqual(calls[0], ['--canonical', 'C:/private/canonical.zip'])
        self.assertIn('모델 없이', out)

    def test_explicit_no_model_never_discovers(self):
        calls = []
        code = launcher.main(platform='win32', is_tty=True,
            chooser=lambda: 'C:/private/canonical.zip', ask=answers('n'),
            discover=lambda: self.fail('unexpected discovery'), local_path=lambda _: True,
            app=lambda args: calls.append(args) or 0)
        self.assertEqual(code, 0)
        self.assertEqual(calls[0], ['--canonical', 'C:/private/canonical.zip'])

    def test_remote_archive_is_rejected_without_app(self):
        code, calls, _ = self.run_launcher(prompts=(), models={}, local=False)
        self.assertEqual(code, 1)
        self.assertEqual(calls, [])


if __name__ == '__main__':
    unittest.main()
