"""Synthetic tests for two-archive in-process Windows launch."""
import contextlib
import io
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import j3_windows_launcher as launcher


class TwoArchiveLauncherTests(unittest.TestCase):
    def invoke(self, **kwargs):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            result = launcher.main(platform='win32', version=(3,12), is_tty=True, **kwargs)
        return result, out.getvalue() + err.getvalue()

    def test_two_archives_passed_in_process_without_paths_in_output(self):
        a, b = 'SYNTHETIC_PRIVATE_BASE.zip', 'SYNTHETIC_PRIVATE_INCREMENT.zip'
        seen = []
        result, output = self.invoke(chooser=lambda:a, is_d13=lambda _:True,
                                     increment_chooser=lambda:b, runner=lambda args:seen.append(args) or 0)
        self.assertEqual(result, 0)
        self.assertEqual(seen, [['--archive',a,'--increment',b]])
        self.assertNotIn(a, output); self.assertNotIn(b, output)

    def test_cancel_increment_never_starts_server(self):
        seen = []
        result, _ = self.invoke(chooser=lambda:'synthetic.zip', is_d13=lambda _:True,
                                increment_chooser=lambda:'', runner=lambda args:seen.append(args))
        self.assertEqual(result, 0); self.assertEqual(seen, [])

    def test_old_single_archive_does_not_open_increment_picker(self):
        seen = []
        result, _ = self.invoke(chooser=lambda:'synthetic.zip', is_d13=lambda _:False,
                                increment_chooser=lambda:self.fail('must not open'),
                                runner=lambda args:seen.append(args) or 0)
        self.assertEqual(result, 0); self.assertEqual(seen, [['--archive','synthetic.zip']])

    def test_picker_exception_does_not_disclose_private_value(self):
        def bad(): raise RuntimeError('SYNTHETIC_PRIVATE_PATH')
        result, output = self.invoke(chooser=lambda:'synthetic.zip', is_d13=lambda _:True,
                                     increment_chooser=bad, runner=lambda args:self.fail('must not run'))
        self.assertEqual(result, 1); self.assertNotIn('SYNTHETIC_PRIVATE_PATH', output)


if __name__ == '__main__': unittest.main()
