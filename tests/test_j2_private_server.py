"""Synthetic-only loopback authorization, search, and projection tests."""
import contextlib
import copy
import http.client
import io
import json
import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))
from j2_private_preview import PrivatePreviewServer, filter_records, local_archive_path
from j2_preview_test_server import sample_data

# This is a clearly labeled synthetic test fixture, not a real credential.
FAKE_SECRET = 'SYNTHETIC-ONLY-SECRET-0123456789'

class SearchTests(unittest.TestCase):
    def setUp(self):
        self.data = sample_data()
    def run_filter(self, **params):
        return filter_records(self.data, {k: [v] for k, v in params.items()})
    def test_researcher_matches_speaker_and_creator(self):
        self.assertEqual(self.run_filter(researcher='가상 발화자')['records'][0]['key'], 'synthetic:claim:1')
        self.assertEqual(self.run_filter(researcher='가상 저자')['records'][0]['key'], 'synthetic:claim:1')
        self.assertEqual(self.run_filter(researcher='absent')['total'], 0)
    def test_multiple_passage_predicates_must_match_same_address(self):
        row = self.data['records'][0]
        row['passages'] = [{'corpus':'bible','scheme':'alpha','reference':'1:1'}, {'corpus':'quran','scheme':'beta','reference':'2:2'}]
        self.assertEqual(self.run_filter(corpus='bible', scheme='beta')['total'], 0)
        self.assertEqual(self.run_filter(corpus='bible', scheme='alpha', reference='1:1')['total'], 1)
        self.assertEqual(self.run_filter(corpus='quran')['total'], 1)
        self.assertEqual(self.run_filter(q='quran')['total'], 1)
    def test_flat_passage_fallback_when_list_absent(self):
        self.data['records'][0].pop('passages')
        self.assertEqual(self.run_filter(corpus='가상 코퍼스', scheme='가상 체계')['total'], 1)
    def test_community_subject_does_not_create_attribution(self):
        row = self.data['records'][1]
        row.update(tradition=None, community_reference='가상 전통 A', community_role='target', evaluated_subject='가상 전통 A')
        result = self.run_filter(community='가상 전통 A', attribution='external_critique')
        self.assertEqual(result['total'], 1)
        self.assertIsNone(result['records'][0]['tradition'])
        self.assertEqual(result['records'][0]['community_role'], 'target')
        self.assertEqual(self.run_filter(community='가상 전통 A', attribution='official_doctrine')['total'], 0)
    def test_evidence_and_relation_are_separately_searchable(self):
        self.assertEqual(self.run_filter(evidence_kind='support', evidence_status='pending')['total'], 1)
        self.assertEqual(self.run_filter(relation_kind='contrast', relation_status='pending')['total'], 1)
        self.assertEqual(self.run_filter(relation_kind='rebuts')['total'], 0)
        self.assertEqual(self.run_filter(relation_kind='contrast', relation_status='verified')['total'], 0)
    def test_rights_action_and_decision_match_same_recorded_action(self):
        conditional = self.run_filter(rights_action='store_excerpt', rights_decision='conditional')
        self.assertEqual(conditional['total'], 1)
        self.assertEqual(conditional['records'][0]['rights']['store_excerpt'], 'conditional')
        self.assertEqual(self.run_filter(rights_action='store_excerpt', rights_decision='unknown')['total'], 1)
        self.assertEqual(self.run_filter(rights_action='store_raw', rights_decision='conditional')['total'], 0)
        self.assertTrue(all(v is False for v in conditional['records'][0]['effective_permissions'].values()))
    def test_rights_override_is_separate_from_original(self):
        r = self.run_filter(rights_action='browse', rights_decision='conditional')
        self.assertEqual(r['total'], 1)
        self.assertEqual(r['records'][0]['rights']['browse'], 'unknown')
        self.assertEqual(r['records'][0]['rights_overrides'][0]['new_decision'], 'conditional')
        self.assertFalse(r['records'][0]['effective_permissions']['browse'])
    def test_source_multiple_editions_preserve_separate_action_decisions(self):
        row = self.data['records'][0]
        row.update(record_kind='source', rights_status='multiple_editions', rights={'browse':'unmapped'}, rights_overrides=[],
                   edition_rights=[{'key':'d8:editions:1', 'rights':{'browse':'unknown', 'store_excerpt':'conditional'}, 'rights_overrides':[]},
                                   {'key':'d8:editions:2', 'rights':{'browse':'prohibited', 'store_excerpt':'unknown'}, 'rights_overrides':[]}])
        a = self.run_filter(key=row['key'], rights_action='browse', rights_decision='unknown')
        b = self.run_filter(key=row['key'], rights_action='store_excerpt', rights_decision='conditional')
        c = self.run_filter(key=row['key'], rights_action='store_raw', rights_decision='conditional')
        self.assertEqual((a['total'], b['total'], c['total']), (1, 1, 0))
        self.assertEqual(self.run_filter(key=row['key'], rights_action='browse', rights_decision='conditional')['total'], 0)
        out = a['records'][0]
        self.assertEqual(out['rights_status'], 'multiple_editions')
        self.assertEqual(out['edition_rights'][0]['rights']['browse'], 'unknown')
        self.assertEqual(out['edition_rights'][1]['rights']['browse'], 'prohibited')
        self.assertTrue(all(not value for ed in out['edition_rights'] for value in ed['effective_permissions'].values()))
    def test_enum_matching_is_exact(self):
        self.data['records'][0]['verification_status'] = 'unverified'
        self.assertEqual(self.run_filter(verification_status='verified')['total'], 0)
        self.assertEqual(self.run_filter(verification_status='unverified')['total'], 1)
    def test_stage_key_and_pagination(self):
        row = self.data['records'][0]
        self.data['records'] = [dict(row, key='synthetic:'+str(i)) for i in range(101)]
        self.assertEqual(self.run_filter(stage='D8')['total'], 101)
        self.assertEqual(len(self.run_filter(stage='D8')['records']), 100)
        self.assertEqual(len(self.run_filter(stage='D8', offset='100')['records']), 1)
        self.assertEqual(self.run_filter(key='synthetic:100')['records'][0]['key'], 'synthetic:100')
        self.assertEqual(self.run_filter(key='synthetic:10')['total'], 1)
    def test_claim_source_link_uses_typed_coordinates_not_raw_ids(self):
        claim = self.data['records'][0]
        claim.update(source_key='d8:sources:2', edition_key='d8:editions:3', locator_key='d8:locators:4')
        source = dict(self.data['records'][1], key='d8:sources:2', record_kind='source')
        self.data['records'].append(source)
        claim_out = self.run_filter(key=claim['key'])['records'][0]
        self.assertEqual((claim_out['source_key'], claim_out['edition_key'], claim_out['locator_key']), ('d8:sources:2', 'd8:editions:3', 'd8:locators:4'))
        self.assertEqual(self.run_filter(key=claim_out['source_key'])['records'][0]['record_kind'], 'source')
        for field, bad in (('source_key','private-source-id'), ('edition_key','d8:sources:3'), ('locator_key','https://example.invalid/private')):
            original = claim[field]
            claim[field] = bad
            out = self.run_filter(key=claim['key'])['records'][0]
            self.assertIsNone(out[field])
            claim[field] = original
    def test_unknown_date_scope_is_pending(self):
        r = self.run_filter(as_of='2025-01-01')
        self.assertEqual(r['total'], 2)
        self.assertTrue(all(x['date_filter_status'] == 'pending' for x in r['records']))
    def test_known_dates_filter_only_explicit_intervals(self):
        self.data['records'][0].update(valid_from='2020-01-01', valid_until='2030-12-31')
        r = self.run_filter(as_of='2040-01-01')
        self.assertEqual(r['total'], 1)
        self.assertEqual(r['records'][0]['date_filter_status'], 'pending')
    def test_unapproved_free_text_is_never_returned_or_searchable(self):
        self.data['records'][0]['summary'] = 'PRIVATE-SYNTHETIC-QUOTE'
        self.data['records'][0]['raw_text'] = 'PRIVATE-SYNTHETIC-QUOTE'
        self.data['records'][0]['access_events'] = [{'method':'search_only', 'result':'redacted_rights_unresolved', 'checked_at':'2025-01-01', 'note':'PRIVATE-SYNTHETIC-QUOTE'}]
        self.assertEqual(self.run_filter(q='PRIVATE-SYNTHETIC-QUOTE')['total'], 0)
        output = json.dumps(self.run_filter(), ensure_ascii=False)
        self.assertNotIn('PRIVATE-SYNTHETIC-QUOTE', output)
        self.assertIsNone(self.run_filter()['records'][0]['summary'])
        self.assertEqual(self.run_filter()['records'][0]['access_events'][0]['method'], 'search_only')
    def test_unreviewed_research_names_and_titles_are_not_returned_or_searchable(self):
        self.data['dataset'] = 'D8'
        row = self.data['records'][0]
        row.update(key='d8:claims:1', source_title='SYNTHETIC-UNREVIEWED-TITLE', source_creator='SYNTHETIC-UNREVIEWED-NAME', researcher='SYNTHETIC-UNREVIEWED-NAME', speaker='SYNTHETIC-UNREVIEWED-NAME', tradition='SYNTHETIC-UNREVIEWED-GROUP', community_reference='SYNTHETIC-UNREVIEWED-GROUP', evaluated_subject='SYNTHETIC-UNREVIEWED-GROUP', community_role='target')
        result = self.run_filter(key=row['key'])
        for field in ('source_title', 'source_creator', 'researcher', 'speaker', 'tradition', 'community_reference', 'evaluated_subject'):
            self.assertIsNone(result['records'][0][field])
        self.assertEqual(self.run_filter(q='SYNTHETIC-UNREVIEWED-TITLE')['total'], 0)
        self.assertEqual(self.run_filter(researcher='SYNTHETIC-UNREVIEWED-NAME')['total'], 0)
        self.assertEqual(self.run_filter(community='SYNTHETIC-UNREVIEWED-GROUP')['total'], 0)
        self.assertEqual(result['records'][0]['community_role'], 'target')
    def test_research_record_key_cannot_be_a_raw_identifier(self):
        self.data['dataset'] = 'D8'
        self.data['records'][0]['key'] = 'private-source-identifier'
        output = self.run_filter()
        self.assertIsNone(output['records'][0]['key'])
        self.assertNotIn('private-source-identifier', json.dumps(output))
        self.assertEqual(self.run_filter(key='private-source-identifier')['total'], 0)
    def test_unknown_filter_or_invalid_date_fails_closed(self):
        for bad in ({'hidden_text':['x']}, {'as_of':['2025-02-31']}, {'offset':['-1']}, {'stage':['D8','D7']}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                filter_records(self.data, bad)
    def test_unmapped_summary_rejects_arbitrary_fields(self):
        self.data['unmapped_summary'] = {'d8': {'claims': {'input_count': 2, 'mapping': 'partial', 'note': 'SECRET'}, 'RAW-SECRET': {'input_count': 1, 'mapping': 'partial'}, 'conflicts': {'input_count': 3, 'mapping': 'unmapped'}}, 'external': {'claims': {'input_count': 1, 'mapping': 'partial'}}}
        summary = self.run_filter()['unmapped_summary']
        self.assertEqual(summary, {'d8': {'claims': {'input_count': 2, 'mapping': 'partial'}, 'conflicts': {'input_count': 3, 'mapping': 'unmapped'}}})
    def test_obvious_remote_archive_path_rejected_before_open(self):
        for path in (r'\\server\share\input.zip', '//server/share/input.zip', 'https://example.invalid/input.zip', 'file://server/share/input.zip'):
            with self.subTest(path=path), self.assertRaises(ValueError): local_archive_path(path)
        self.assertEqual(str(local_archive_path('/tmp/input.zip')), '/tmp/input.zip')
        self.assertTrue(str(local_archive_path(r'C:\input.zip')).endswith(r'C:\input.zip'))

class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = PrivatePreviewServer(sample_data(), FAKE_SECRET)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join()
    def setUp(self):
        with self.server._attempt_lock:
            self.server._failed_attempts = 0
            self.server._retry_after = 0
    def req(self, path='/', headers=None, method='GET'):
        c = http.client.HTTPConnection('127.0.0.1', self.server.server_address[1], timeout=3)
        try:
            c.request(method, path, headers=headers or {})
            r = c.getresponse(); body = r.read(); return r.status, dict(r.getheaders()), body
        finally:
            c.close()
    def auth(self): return {'Authorization': 'Bearer ' + FAKE_SECRET}
    def test_server_binds_ipv4_loopback_only(self):
        self.assertEqual(self.server.server_address[0], '127.0.0.1')
    def test_missing_and_bad_password_rejected_no_data(self):
        for headers in ({}, {'Authorization': 'Bearer bad'}):
            status, _, body = self.req('/api/candidates', headers)
            self.assertEqual(status, 401); self.assertNotIn('가상 문헌'.encode(), body)
    def test_correct_session_can_access_synthetic_candidate(self):
        status, headers, body = self.req('/api/candidates', self.auth())
        self.assertEqual(status, 200); self.assertEqual(json.loads(body)['dataset'], 'synthetic')
        self.assertEqual(headers['Cache-Control'], 'no-store, max-age=0')
        self.assertNotIn('Access-Control-Allow-Origin', headers)
    def test_wrong_host_and_cross_origin_are_rejected(self):
        for h in ({'Host':'evil.example'}, {'Origin':'https://evil.example'}, {'Sec-Fetch-Site':'cross-site'}):
            self.assertEqual(self.req('/api/candidates', dict(self.auth(), **h))[0], 403)
    def test_exact_local_origin_is_allowed(self):
        self.assertEqual(self.req('/api/candidates', dict(self.auth(), Origin=self.server.expected_origin))[0], 200)
    def test_static_policy_and_no_directory_browsing(self):
        status, headers, _ = self.req('/')
        self.assertEqual(status, 200); self.assertIn("default-src 'none'", headers['Content-Security-Policy'])
        self.assertEqual(headers['X-Frame-Options'], 'DENY')
        self.assertEqual(self.req('/../../README.md')[0], 404)
        self.assertEqual(self.req('/%2e%2e/README.md')[0], 404)
    def test_options_post_do_not_enable_cors_or_selection(self):
        for method in ('POST', 'OPTIONS'):
            status, headers, _ = self.req('/api/candidates', {'Origin':'https://evil.example'}, method)
            self.assertEqual(status, 405); self.assertNotIn('Access-Control-Allow-Origin', headers)
    def test_bad_query_never_reflects_input_or_password(self):
        status, _, body = self.req('/api/candidates?' + urlencode({'path':'SYNTHETIC-PRIVATE-PATH'}), self.auth())
        self.assertEqual(status, 400); self.assertNotIn(b'SYNTHETIC-PRIVATE-PATH', body); self.assertNotIn(FAKE_SECRET.encode(), body)
    def test_authentication_lock_and_recovery(self):
        for _ in range(5): self.assertEqual(self.req('/api/candidates', {'Authorization':'Bearer wrong'})[0], 401)
        self.assertEqual(self.req('/api/candidates', self.auth())[0], 401)
        with self.server._attempt_lock: self.server._retry_after = 0
        self.assertEqual(self.req('/api/candidates', self.auth())[0], 200)
    def test_success_resets_failed_attempts(self):
        for _ in range(4): self.assertEqual(self.req('/api/candidates', {'Authorization':'Bearer wrong'})[0], 401)
        self.assertEqual(self.req('/api/candidates', self.auth())[0], 200)
        self.assertEqual(self.req('/api/candidates', {'Authorization':'Bearer wrong'})[0], 401)
        self.assertEqual(self.req('/api/candidates', self.auth())[0], 200)
    def test_parallel_bad_attempts_lock_shared_server(self):
        def bad(_): return self.req('/api/candidates', {'Authorization':'Bearer wrong'})[0]
        with ThreadPoolExecutor(max_workers=5) as pool:
            self.assertEqual(list(pool.map(bad, range(5))), [401] * 5)
        self.assertEqual(self.req('/api/candidates', self.auth())[0], 401)
        with self.server._attempt_lock: self.server._retry_after = 0
        self.assertEqual(self.req('/api/candidates', self.auth())[0], 200)
    def test_request_access_is_not_logged(self):
        out = io.StringIO()
        with contextlib.redirect_stderr(out):
            self.req('/api/candidates?' + urlencode({'q':'SYNTHETIC-SENSITIVE'}), self.auth())
        self.assertEqual(out.getvalue(), '')

if __name__ == '__main__': unittest.main()
