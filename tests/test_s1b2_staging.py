import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from d2_bridge.staging import StagingError, _connection, action_allowed, ACTIONS, EXPECTED_SHA256, stage_synthetic


class StagingGuardTests(unittest.TestCase):
    def setUp(self):
        self.good = {'SCRIPTURA_STAGING_APPROVED':'synthetic-test-only', 'SCRIPTURA_STAGING_DATABASE_URL':'postgresql://writer@127.0.0.1:55439/scriptura_staging_test'}

    def test_explicit_acknowledgement_and_loopback_are_required(self):
        for patch in ({'SCRIPTURA_STAGING_APPROVED':''}, {'SCRIPTURA_STAGING_DATABASE_URL':'postgresql://writer@example.com/scriptura_staging_test'}, {'SCRIPTURA_STAGING_DATABASE_URL':'postgresql://writer@127.0.0.1/production'}, {'SCRIPTURA_STAGING_DATABASE_URL':'postgresql://writer@127.0.0.1/scriptura_staging_test?host=evil.invalid'}):
            with self.subTest(patch=patch),self.assertRaises(StagingError): _connection(self.good | patch)

    def test_existing_database_aliases_and_user_changes_do_not_bypass(self):
        for key in ('DATABASE_URL','SCRIPTURA_PRODUCTION_DATABASE_URL','SCRIPTURA_REVIEW_DATABASE_URL'):
            with self.subTest(key=key),self.assertRaises(StagingError):
                _connection(self.good | {key:'postgresql://other@localhost:55439/scriptura_staging_test'})
        self.assertEqual(_connection(self.good | {'DATABASE_URL':'postgresql://owner@127.0.0.1:55439/scriptura_other'})['database'],'scriptura_staging_test')

    def test_production_digest_and_non_synthetic_snapshot_fail_before_connect(self):
        with self.assertRaises(StagingError):
            stage_synthetic('/not/read.zip',expected_sha256=EXPECTED_SHA256,expected_counts={},expected_snapshot='TEST-SYNTHETIC-ONLY-v1',env=self.good)
        with self.assertRaises(StagingError):
            stage_synthetic('/not/read.zip',expected_sha256='a'*64,expected_counts={},expected_snapshot='SCRIPTURA-D11-D2-20261105-v1',env=self.good)

    def test_rights_are_default_denied_for_every_action_and_cross_edition(self):
        for action in ACTIONS:
            for decision in ('allowed','conditional','unknown','denied'):
                with self.subTest(action=action,decision=decision):
                    self.assertFalse(action_allowed([{'edition_id':'other-edition','action':action,'decision':decision}],action))
        self.assertFalse(action_allowed([], 'invented'))

    def test_malformed_url_is_fail_closed(self):
        for value in ('', 'postgresql:///scriptura_staging_test', 'postgresql://user@127.0.0.1:bogus/scriptura_staging_test', 'postgresql://user@127.0.0.1/scriptura_staging_test#foo'):
            with self.subTest(value=value),self.assertRaises(StagingError): _connection(self.good | {'SCRIPTURA_STAGING_DATABASE_URL':value})

if __name__ == '__main__': unittest.main()
