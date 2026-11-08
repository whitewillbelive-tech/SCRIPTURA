"""Synthetic local candidate API tests; never use a research archive."""
import json
import contextlib
import http.client
import io
import sys
import threading
import unittest
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from j2_private_preview import filter_records, PrivatePreviewServer
from k13_bridge.local_candidate import prepare_local_candidate_index
from k11_bridge.metadata import synthetic_index_for_tests


def dataset():
    return {'dataset': 'D10', 'records': [
        {'key': 'd8:sources:1', 'stage': 'd8', 'record_kind': 'source',
         'source_title': 'SYNTHETIC-UNSAFE-RAW', 'field_policy': {'source_metadata': 'candidate_visible_local'},
         'authority_status': 'pending_authority', 'independent_review_status': 'pending'},
        {'key': 'd8:claims:1', 'stage': 'd8', 'record_kind': 'claim',
         'source_key': 'd8:sources:1', 'edition_key': 'd8:editions:1',
         'authority_status': 'pending_authority', 'independent_review_status': 'pending'},
        {'key': 'd8:sources:2', 'stage': 'd8', 'record_kind': 'source',
         'source_title': 'SYNTHETIC-HIDDEN'}], 'counts': {}, 'warnings': []}


def layers():
    return {'d8': {'sources': [{'line': 1, 'value': {
        'id': 'synthetic:source', 'title': 'SYNTHETIC-TITLE',
        'creator': 'SYNTHETIC-AUTHOR', 'publisher': 'SYNTHETIC-PUBLISHER',
        'publication_year': 2099}}],
        'editions': [{'line': 1, 'value': {'id': 'synthetic:edition',
                     'source_id': 'synthetic:source'}}], 'claims': [], 'rights': []}}


def confirmed_title():
    item = {'key': 'd8:sources:1', 'field': 'source_title',
            'source_id': 'synthetic:source', 'edition_id': 'synthetic:edition',
            'reviewer': 'synthetic:reviewer', 'value': 'SYNTHETIC-TITLE',
            'source_confirmation': 'independently_confirmed', 'rights_review': 'independently_confirmed',
            'privacy_review': 'cleared', 'scope': 'private_local_display_and_search',
            'jurisdiction': 'synthetic:test', 'basis': 'public_domain', 'conflict': False,
            'source_evidence': 'https://example.invalid/source', 'rights_evidence': 'https://example.invalid/rights',
            'reviewed_at': '2026-01-01', 'valid_from': '2025-01-01', 'valid_until': '2027-01-01'}
    records = {'d8:sources:1': {'source_id': 'synthetic:source', 'edition_id': 'synthetic:edition',
                                'fields': {'source_title': 'SYNTHETIC-TITLE'}}}
    return synthetic_index_for_tests('D10', records, [item], today='2026-06-01')


class LocalCandidateApiTests(unittest.TestCase):
    def local(self):
        value = dataset()
        value['_local_candidate_index'] = prepare_local_candidate_index(value, layers())
        return value

    def test_recorded_fields_are_local_candidates_and_searchable(self):
        value = self.local()
        response = filter_records(value, {})
        self.assertEqual(response['metadata_projection'], 'k1.3-local-candidate')
        row = response['records'][0]
        self.assertEqual(row['candidate_metadata']['source_title']['value'], 'SYNTHETIC-TITLE')
        self.assertEqual(row['candidate_metadata']['source_title']['status'], 'recorded_unverified')
        self.assertEqual(row['authority_status'], 'pending_authority')
        self.assertEqual(row['independent_review_status'], 'pending')
        self.assertEqual(row['local_visibility'], 'private_local_candidate')
        self.assertEqual(row['publication_status'], 'not_granted')
        self.assertGreaterEqual(filter_records(value, {'q': ['synthetic-title']})['total'], 1)
        self.assertGreaterEqual(filter_records(value, {'researcher': ['synthetic-author']})['total'], 1)

    def test_untrusted_raw_records_and_forged_index_cannot_display_or_search(self):
        value = dataset()
        value['_local_candidate_index'] = {'d8:sources:1': {'source_title': 'SYNTHETIC-HIDDEN'}}
        response = filter_records(value, {})
        self.assertNotIn('SYNTHETIC-HIDDEN', json.dumps(response))
        self.assertNotIn('SYNTHETIC-UNSAFE-RAW', json.dumps(response))
        self.assertEqual(filter_records(value, {'q': ['SYNTHETIC-HIDDEN']})['total'], 0)
        self.assertEqual(filter_records(value, {'q': ['SYNTHETIC-UNSAFE-RAW']})['total'], 0)

    def test_local_scope_is_bound_to_dataset(self):
        value = self.local()
        value['dataset'] = 'D9'
        response = filter_records(value, {})
        self.assertNotIn('SYNTHETIC-TITLE', json.dumps(response))
        self.assertEqual(filter_records(value, {'q': ['SYNTHETIC-TITLE']})['total'], 0)

    def test_hidden_fields_are_not_searched(self):
        value = self.local()
        self.assertEqual(filter_records(value, {'community': ['SYNTHETIC-HIDDEN']})['total'], 0)
        self.assertEqual(filter_records(value, {'researcher': ['SYNTHETIC-HIDDEN']})['total'], 0)
        row = filter_records(value, {})['records'][0]
        self.assertIsNone(row.get('summary'))
        self.assertIsNone(row.get('source_doi'))
        self.assertIsNone(row.get('locator'))

    def test_source_confirmed_is_field_specific_and_does_not_confirm_claim(self):
        value = self.local()
        value['_verified_metadata_index'] = confirmed_title()
        row = filter_records(value, {})['records'][0]
        self.assertEqual(row['candidate_metadata']['source_title']['status'], 'source_confirmed')
        self.assertEqual(row['candidate_metadata']['source_creator']['status'], 'recorded_unverified')
        self.assertEqual(row['source_verification_status'], 'verified_fields_only')
        self.assertEqual(row['authority_status'], 'pending_authority')
        self.assertEqual(row['independent_review_status'], 'pending')
        counts = filter_records(value, {})['candidate_restriction_summary']['sources']['source_title']
        self.assertEqual(counts['source_confirmed'], 1)
        self.assertEqual(counts['recorded_unverified'], 0)

    def test_restricted_current_candidate_cannot_be_restored_by_previous_confirmation(self):
        value = dataset()
        original = layers()
        original['d8']['sources'][0]['value']['privacy'] = 'private'
        value['_local_candidate_index'] = prepare_local_candidate_index(value, original)
        value['_verified_metadata_index'] = confirmed_title()
        result = filter_records(value, {})
        field = result['records'][0]['candidate_metadata']['source_title']
        self.assertEqual(field['status'], 'restricted')
        self.assertIsNone(field['value'])
        self.assertEqual(result['records'][0]['verified_metadata'], {})
        self.assertEqual(filter_records(value, {'q': ['SYNTHETIC-TITLE']})['total'], 0)
        self.assertNotIn('SYNTHETIC-TITLE', json.dumps(result))

    def test_community_role_is_taken_only_from_the_linked_candidate(self):
        for original_role, attribution, expected in (
            ('target', 'external_critique', 'target'),
            ('self', 'self_explanation', 'self'),
        ):
            value, original = dataset(), layers()
            value['records'][1]['community_role'] = 'self' if expected == 'target' else 'target'
            original['d8']['claims'] = [{'line': 1, 'value': {
                'id': 'synthetic:claim', 'community_id': 'synthetic:community',
                'community_id_role': original_role, 'attribution_kind': attribution}}]
            original['d8']['communities'] = [{'line': 1, 'value': {
                'id': 'synthetic:community', 'canonical_name': 'SYNTHETIC-COMMUNITY'}}]
            value['_local_candidate_index'] = prepare_local_candidate_index(value, original)
            row = filter_records(value, {'key': ['d8:claims:1']})['records'][0]
            self.assertEqual(row['community_role'], expected)
            self.assertEqual(row['candidate_metadata']['community_name']['relationship_role'], expected)
            self.assertEqual(filter_records(value, {'community': ['synthetic-community']})['total'], 1)

    def test_unconfirmed_role_cannot_be_recovered_from_raw_projection(self):
        value, original = dataset(), layers()
        value['records'][1]['community_role'] = 'self'
        original['d8']['claims'] = [{'line': 1, 'value': {
            'id': 'synthetic:claim', 'community_id': 'synthetic:community',
            'community_id_role': 'unknown', 'attribution_kind': 'external_critique'}}]
        original['d8']['communities'] = [{'line': 1, 'value': {
            'id': 'synthetic:community', 'canonical_name': 'SYNTHETIC-COMMUNITY'}}]
        value['_local_candidate_index'] = prepare_local_candidate_index(value, original)
        row = filter_records(value, {'key': ['d8:claims:1']})['records'][0]
        self.assertEqual(row['community_role'], 'unspecified')
        self.assertIsNone(row['candidate_metadata']['community_name']['value'])
        self.assertEqual(filter_records(value, {'community': ['synthetic-community']})['total'], 0)

    def test_local_authenticated_http_search_suppresses_query_logs(self):
        secret = 'synthetic-session-secret-at-least-20-characters'
        server = PrivatePreviewServer(self.local(), secret)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        err = io.StringIO()
        try:
            with contextlib.redirect_stderr(err):
                connection = http.client.HTTPConnection('127.0.0.1', server.server_address[1], timeout=5)
                path = '/api/candidates?' + urlencode({'q': 'SYNTHETIC-TITLE'})
                connection.request('GET', path, headers={'Authorization': 'Bearer ' + secret})
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertIn('no-store', response.getheader('Cache-Control'))
                self.assertGreaterEqual(json.loads(response.read())['total'], 1)
                connection.close()
                connection = http.client.HTTPConnection('127.0.0.1', server.server_address[1], timeout=5)
                connection.request('GET', path, headers={'Authorization': 'Bearer ' + secret,
                                                        'Origin': 'https://example.invalid'})
                denied = connection.getresponse()
                self.assertEqual(denied.status, 403)
                denied.read()
                connection.close()
            self.assertNotIn('SYNTHETIC-TITLE', err.getvalue())
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == '__main__':
    unittest.main()
