"""Synthetic tests for Windows launcher flow; no actual Windows is claimed."""
import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import j3_windows_launcher as launcher


class WindowsLauncherFlowTests(unittest.TestCase):
    def invoke(self, **kwargs):
        stdout, stderr = io.StringIO(), io.StringIO()
        options = {'platform': 'win32', 'version': (3, 11), 'is_tty': True}
        options.update(kwargs)
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = launcher.main(**options)
        return result, stdout.getvalue(), stderr.getvalue()

    def test_selected_file_is_passed_in_process_without_printing(self):
        path = r'C:\private\SYNTHETIC-PRIVATE-PATH.zip'
        seen = []
        result, output, error = self.invoke(chooser=lambda: path, runner=lambda args: seen.append(args) or 0)
        self.assertEqual(result, 0)
        self.assertEqual(seen, [['--archive', path]])
        self.assertNotIn(path, output + error)

    def test_cancel_does_not_start_server(self):
        started = []
        result, _, _ = self.invoke(chooser=lambda: '', runner=lambda args: started.append(args))
        self.assertEqual(result, 0)
        self.assertEqual(started, [])

    def test_dialog_failure_does_not_expose_exception(self):
        def bad():
            raise RuntimeError('SYNTHETIC-PRIVATE-PATH')
        result, output, error = self.invoke(chooser=bad)
        self.assertEqual(result, 1)
        self.assertNotIn('SYNTHETIC-PRIVATE-PATH', output + error)

    def test_nonwindows_old_python_and_noninteractive_are_rejected(self):
        for options in ({'platform':'linux'}, {'version':(3,9)}, {'is_tty':False}):
            with self.subTest(options=options):
                result, _, _ = self.invoke(chooser=lambda: self.fail('must not open picker'), **options)
                self.assertEqual(result, 2)

    def test_server_status_is_preserved(self):
        result, _, _ = self.invoke(chooser=lambda:'synthetic.zip', runner=lambda args: 1)
        self.assertEqual(result, 1)

    def test_runner_exception_does_not_expose_selected_path(self):
        path = r'C:\private\SYNTHETIC-PRIVATE-PATH.zip'
        def bad(args):
            raise ValueError(args[-1])
        result, output, error = self.invoke(chooser=lambda:path, runner=bad)
        self.assertEqual(result, 1)
        self.assertNotIn(path, output + error)

    def test_remote_path_fails_before_any_archive_read(self):
        import j2_private_preview
        for path in (r'\\server\share\synthetic.zip', 'https://example.invalid/a.zip'):
            with self.subTest(path=path), patch.object(j2_private_preview, 'load_versioned_archive') as load:
                result, output, error = self.invoke(chooser=lambda:path, runner=j2_private_preview.main)
                self.assertEqual(result, 1)
                self.assertNotIn(path, output + error)
                load.assert_not_called()

    def test_unavailable_archive_never_starts_synthetic_fallback(self):
        import j2_private_preview
        path = r'C:\private\SYNTHETIC-MISSING.zip'
        with patch.object(j2_private_preview, 'load_versioned_archive', side_effect=OSError(path)), \
             patch.object(j2_private_preview, 'PrivatePreviewServer') as server:
            result, output, error = self.invoke(chooser=lambda:path, runner=j2_private_preview.main)
        self.assertEqual(result, 1)
        self.assertNotIn(path, output + error)
        server.assert_not_called()


if __name__ == '__main__':
    unittest.main()
