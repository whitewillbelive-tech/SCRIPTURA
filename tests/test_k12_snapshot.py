"""Synthetic-only public snapshot trust and local projection tests."""
import copy
import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from j2_private_preview import attach_local_public_snapshot, filter_records
from k11_bridge.metadata import prepare_private_candidates
from k12_bridge.snapshot import AuthenticatedPublicSnapshot, load_authenticated_snapshot

KEY = 'd8:sources:1'
TITLE = 'SYNTHETIC-TITLE'
AUTHOR = 'SYNTHETIC-AUTHOR'
SNAPSHOT = json.dumps({'records': [{'doi': '10.55555/synthetic-doi', 'fields': {
    'source_title': TITLE, 'source_creator': AUTHOR, 'source_year': '2099'}}]}).encode()


def synthetic_privacy(row, field, value):
    return (row.get('source_id') == 'synthetic:source' and row.get('edition_id') == 'synthetic:edition'
            and field in ('source_title', 'source_creator', 'source_year')
            and (value.startswith('SYNTHETIC-') or value == '2099'))


POLICY = {'sha256': hashlib.sha256(SNAPSHOT).hexdigest(), 'source_verified': True,
          'rights_verified': True, 'privacy_verified': True,
          'privacy_verifier': synthetic_privacy,
          'scope': 'private_local_display_and_search', 'basis': 'public_domain',
          'allowed_fields': ('source_title', 'source_creator', 'source_year'),
          'source_reference': 'https://example.invalid/source',
          'rights_reference': 'https://example.invalid/rights',
          'jurisdiction': 'synthetic:test', 'reviewer': 'synthetic:reviewer',
          'valid_from': '2025-01-01', 'valid_until': '2027-01-01',
          'reviewed_at': '2026-01-01', 'synthetic_only': True}


def dataset():
    return {'dataset': 'D10', 'records': [{'key': KEY, 'stage': 'd8',
            'record_kind': 'source'}], 'counts': {}, 'warnings': []}


def candidates(source_id='synthetic:source'):
    layers = {'d8': {'sources': [{'line': 1, 'value': {'id': source_id,
              'title': TITLE, 'creator': AUTHOR, 'doi': '10.55555/synthetic-doi',
              'publication_year': 2099}}], 'editions': [{'line': 1, 'value': {
              'id': 'synthetic:edition', 'source_id': source_id}}]}}
    return prepare_private_candidates(dataset(), layers)


class SnapshotTests(unittest.TestCase):
    def test_no_production_sources_are_registered(self):
        with self.assertRaisesRegex(ValueError, '^public_snapshot_untrusted$'):
            load_authenticated_snapshot('not-registered', SNAPSHOT, today='2026-06-01')

    def test_forged_objects_and_invalid_content_fail_without_values_in_errors(self):
        with self.assertRaisesRegex(ValueError, '^public_snapshot_untrusted$'):
            AuthenticatedPublicSnapshot(None, [], {})
        with patch('k12_bridge.snapshot._TRUSTED_POLICIES', {'synthetic': POLICY}):
            with self.assertRaisesRegex(ValueError, '^public_snapshot_untrusted$'):
                load_authenticated_snapshot('synthetic', b'SYNTHETIC-SECRET', today='2026-06-01')

    def test_pinned_synthetic_snapshot_can_enable_only_individually_matched_fields(self):
        with patch('k12_bridge.snapshot._TRUSTED_POLICIES', {'synthetic': POLICY}):
            snapshot = load_authenticated_snapshot('synthetic', SNAPSHOT, today='2026-06-01')
        self.assertNotIn(TITLE, repr(snapshot))
        result = candidates().attach_public_snapshot(dataset(), snapshot)
        response = filter_records(result, {})
        self.assertEqual(response['records'][0]['verified_metadata'], {
            'source_title': TITLE, 'source_creator': AUTHOR, 'source_year': '2099'})
        self.assertEqual(filter_records(result, {'q': ['SYNTHETIC-TITLE']})['total'], 1)
        self.assertEqual(filter_records(result, {'q': ['10.55555/synthetic-doi']})['total'], 0)

    def test_synthetic_snapshot_cannot_approve_non_synthetic_source(self):
        with patch('k12_bridge.snapshot._TRUSTED_POLICIES', {'synthetic': POLICY}):
            snapshot = load_authenticated_snapshot('synthetic', SNAPSHOT, today='2026-06-01')
        response = filter_records(candidates('private:source').attach_public_snapshot(dataset(), snapshot), {})
        self.assertEqual(response['records'][0]['verified_metadata'], {})

    def test_each_policy_review_is_required_and_untrusted_inputs_remain_hidden(self):
        changes = {'source_verified': False, 'rights_verified': False, 'privacy_verified': False,
                   'privacy_verifier': None,
                   'scope': 'public', 'basis': 'public_web', 'source_reference': None,
                   'rights_reference': 'http://example.invalid/rights', 'allowed_fields': ('community_name',),
                   'valid_until': '2025-01-01'}
        for name, value in changes.items():
            invalid = copy.deepcopy(POLICY)
            invalid[name] = value
            with self.subTest(field=name), patch('k12_bridge.snapshot._TRUSTED_POLICIES', {'synthetic': invalid}):
                with self.assertRaisesRegex(ValueError, '^public_snapshot_untrusted$'):
                    load_authenticated_snapshot('synthetic', SNAPSHOT, today='2026-06-01')

    def test_forged_snapshot_cannot_be_used_to_attach_metadata(self):
        with self.assertRaisesRegex(ValueError, '^public_snapshot_untrusted$'):
            candidates().attach_public_snapshot(dataset(), {'records': []})

    def test_privacy_is_individually_verified_for_each_field(self):
        policy = copy.deepcopy(POLICY)
        policy['privacy_verifier'] = lambda row, field, value: field == 'source_title'
        with patch('k12_bridge.snapshot._TRUSTED_POLICIES', {'synthetic': policy}):
            snapshot = load_authenticated_snapshot('synthetic', SNAPSHOT, today='2026-06-01')
        response = filter_records(candidates().attach_public_snapshot(dataset(), snapshot), {})
        self.assertEqual(response['records'][0]['verified_metadata'], {'source_title': TITLE})

    def test_privacy_callback_failure_and_prints_are_suppressed(self):
        sentinel = 'SYNTHETIC-PRIVATE-PRINT'
        def broken(row, field, value):
            print(sentinel, row, value)
            print(sentinel, file=sys.stderr)
            raise RuntimeError(sentinel)
        policy = copy.deepcopy(POLICY)
        policy['privacy_verifier'] = broken
        with patch('k12_bridge.snapshot._TRUSTED_POLICIES', {'synthetic': policy}):
            snapshot = load_authenticated_snapshot('synthetic', SNAPSHOT, today='2026-06-01')
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            response = filter_records(candidates().attach_public_snapshot(dataset(), snapshot), {})
        self.assertEqual(response['records'][0]['verified_metadata'], {})
        self.assertNotIn(sentinel, out.getvalue() + err.getvalue())

    def test_local_snapshot_integration_is_offline_and_bound_to_the_fixed_policy(self):
        initial = dataset()
        initial['_private_metadata_candidates'] = candidates()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic.json'
            path.write_bytes(SNAPSHOT)
            with patch('socket.create_connection', side_effect=AssertionError('unexpected network')):
                with self.assertRaisesRegex(ValueError, '^public_snapshot_untrusted$'):
                    attach_local_public_snapshot(initial, 'unknown', str(path), today='2026-06-01')
                with patch('k12_bridge.snapshot._TRUSTED_POLICIES', {'synthetic': POLICY}):
                    result = attach_local_public_snapshot(initial, 'synthetic', str(path), today='2026-06-01')
                    self.assertEqual(filter_records(result, {'q': ['SYNTHETIC-TITLE']})['total'], 1)
                    path.write_bytes(b'SYNTHETIC-INVALID')
                    with self.assertRaisesRegex(ValueError, '^public_snapshot_untrusted$'):
                        attach_local_public_snapshot(initial, 'synthetic', str(path), today='2026-06-01')

    def test_local_snapshot_rejects_network_paths_and_forged_candidate_objects(self):
        initial = dataset()
        initial['_private_metadata_candidates'] = candidates()
        with self.assertRaisesRegex(ValueError, '^public_snapshot_untrusted$'):
            attach_local_public_snapshot(initial, 'synthetic', 'https://example.invalid/file', today='2026-06-01')
        initial['_private_metadata_candidates'] = {'forged': True}
        with self.assertRaisesRegex(ValueError, '^public_snapshot_untrusted$'):
            attach_local_public_snapshot(initial, 'synthetic', 'SYNTHETIC-PATH', today='2026-06-01')


if __name__ == '__main__':
    unittest.main()
