"""D3 research must remain read-only even with an explicit synthetic test pin."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from d2_bridge.staging import (D3_RESEARCH_SHA256, EXPECTED_SHA256, StagingError,
                               _safe_data, action_allowed, stage_synthetic)


class I1ResearchStagingGuards(unittest.TestCase):
    def setUp(self):
        self.env = {
            'SCRIPTURA_STAGING_APPROVED': 'synthetic-test-only',
            'SCRIPTURA_STAGING_DATABASE_URL': 'postgresql://test_writer@127.0.0.1:55439/scriptura_staging_i1',
        }

    def test_both_frozen_research_hashes_rejected_before_file_or_database_access(self):
        for digest in (D3_RESEARCH_SHA256, EXPECTED_SHA256):
            with self.subTest(research_digest=digest), self.assertRaisesRegex(StagingError, 'synthetic_archive_required'):
                stage_synthetic('/not-opened.zip', expected_sha256=digest,
                                expected_counts={}, expected_snapshot='TEST-SYNTHETIC-X', env=self.env)

    def test_defense_in_depth_rejects_d3_hash_even_in_forged_passing_report(self):
        report = {'status': 'pass', 'snapshot': 'TEST-SYNTHETIC-X', 'archive_sha256': D3_RESEARCH_SHA256}
        with self.assertRaisesRegex(StagingError, 'synthetic_archive_required'):
            _safe_data(report, {}, 'synthetic.zip', {})

    def test_evidence_of_browse_permission_never_authorizes_other_actions(self):
        for action in ('store_raw', 'store_excerpt', 'index_fulltext', 'embed',
                       'send_to_model', 'redistribute', 'public_link'):
            with self.subTest(action=action):
                self.assertFalse(action_allowed([{'action': 'browse', 'decision': 'allowed'}], action))


if __name__ == '__main__':
    unittest.main()
