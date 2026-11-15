"""Regression: Windows stat(path) and fstat(fd) can disagree on ctime.

The actual D13/D14 archives remain private and are never used by GitHub CI.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import k37_work_archive_compat as audit
import j3_windows_launcher as launcher


class WindowsArchiveStatTests(unittest.TestCase):
    def test_stat_fstat_unequal_ctime_accepts_unchanged_file(self):
        with tempfile.TemporaryDirectory() as home:
            name = str(Path(home) / "synthetic-data.zip")
            data = b"SYNTHETIC-NOT-RESEARCH-DATA"
            Path(name).write_bytes(data)
            original = os.stat
            def windows_stat(path, *args, **kwargs):
                result = original(path, *args, **kwargs)
                if os.fspath(path) != name:
                    return result
                # Only path-based stat differs, like some Windows Python builds.
                fields = {key: getattr(result, key) for key in
                          ("st_mode", "st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")}
                fields["st_ctime_ns"] += 10_000_000_000
                return SimpleNamespace(**fields)
            with patch.object(audit.os, "stat", side_effect=windows_stat):
                self.assertEqual(audit.read_local_unchanged(name), data)

    def test_same_handle_changed_mtime_is_still_rejected(self):
        with tempfile.TemporaryDirectory() as home:
            name = str(Path(home) / "synthetic-data.zip")
            Path(name).write_bytes(b"SYNTHETIC")
            original = os.fstat
            calls = [0]
            def changed_fstat(fd):
                calls[0] += 1
                result = original(fd)
                if calls[0] == 2:
                    fields = {key: getattr(result, key) for key in
                              ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")}
                    fields["st_mtime_ns"] += 1
                    return SimpleNamespace(**fields)
                return result
            with patch.object(audit.os, "fstat", side_effect=changed_fstat):
                with self.assertRaises(audit.AuditError):
                    audit.read_local_unchanged(name)

    def test_d13_named_bad_hash_reports_distinct_error(self):
        import contextlib
        import io
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            status = launcher.main(platform="win32", version=(3, 12), is_tty=True,
                chooser=lambda: "D13.zip", is_d13=lambda _: False,
                runner=lambda args: self.fail("must reject mismatched D13"))
        self.assertEqual(status, 1)
        self.assertIn("D-13", output.getvalue())
        self.assertNotIn("SYNTHETIC-NOT-RESEARCH-DATA", output.getvalue())


if __name__ == "__main__":
    unittest.main()
