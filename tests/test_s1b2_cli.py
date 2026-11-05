"""Public entry points cannot unpin a research snapshot or load external ZIPs."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from s1b2_synthetic_factory import write_archive


class BridgeCliTests(unittest.TestCase):
    def test_synthetic_zip_cannot_bypass_production_pin(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / 'synthetic.zip'
            write_archive(archive)
            run = subprocess.run([sys.executable, 'scripts/d2_bridge_cli.py', 'dry-run', str(archive)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(run.returncode, 1)
            report = json.loads(run.stdout)
            self.assertEqual(report['status'], 'fail')
            self.assertIn('archive_sha256_mismatch', report['errors'])
            self.assertFalse(report['database_write'])

    def test_report_will_not_overwrite_existing_file(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / 'synthetic.zip'
            write_archive(archive)
            output = Path(temp) / 'report.json'
            output.write_text('preserve', encoding='utf-8')
            run = subprocess.run([sys.executable, 'scripts/d2_bridge_cli.py', 'validate', str(archive), '--output', str(output)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(run.returncode, 2)
            self.assertEqual(output.read_text(encoding='utf-8'), 'preserve')

    def test_staging_requires_explicit_test_opt_in_and_no_external_path(self):
        env = os.environ.copy()
        env.pop('SCRIPTURA_STAGING_APPROVED', None)
        run = subprocess.run([sys.executable, 'scripts/stage_synthetic.py'], cwd=ROOT, env=env, capture_output=True, text=True)
        self.assertEqual(run.returncode, 1)
        self.assertEqual(json.loads(run.stderr)['reason'], 'synthetic_staging_not_explicitly_approved')
        run = subprocess.run([sys.executable, 'scripts/stage_synthetic.py', 'external.zip'], cwd=ROOT, env=env, capture_output=True, text=True)
        self.assertEqual(run.returncode, 2)


if __name__ == '__main__':
    unittest.main()
