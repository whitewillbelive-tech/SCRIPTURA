"""Synthetic coverage for the authenticated C-02 evidence dossier route."""
import http.client
import json
import sys
import threading
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import j2_private_preview as api

SECRET = 'synthetic-only-secret-for-tests'
QUERY = '/api/research-dossier?corpus=synthetic&scheme=synthetic&reference=one'


class DossierHTTPTests(unittest.TestCase):
    def setUp(self):
        self.server = api.PrivatePreviewServer({'dataset': 'D16', 'records': []}, SECRET)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join()

    def request(self, path=QUERY, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_address[1], timeout=5)
        try:
            conn.request('GET', path, headers={'Host': self.server.expected_host, **(headers or {})})
            resp = conn.getresponse()
            return resp.status, dict(resp.getheaders()), resp.read()
        finally:
            conn.close()

    def authorized(self):
        return {'Authorization': 'Bearer ' + SECRET, 'Origin': self.server.expected_origin}

    def test_requires_session_and_loopback_origin(self):
        self.assertEqual(self.request()[0], 401)
        self.assertEqual(self.request(headers={**self.authorized(), 'Origin': 'http://attacker.invalid'})[0], 403)
        self.assertEqual(self.request(headers={**self.authorized(), 'Sec-Fetch-Site': 'cross-site'})[0], 403)
        self.assertEqual(self.request(headers={**self.authorized(), 'Host': 'attacker.invalid'})[0], 403)

    def test_only_exact_address_is_permitted(self):
        cases = ('/api/research-dossier',
                 '/api/research-dossier?corpus=synthetic&scheme=synthetic',
                 QUERY + '&reference=two', QUERY + '&projection=verified',
                 '/api/research-dossier?corpus=&scheme=synthetic&reference=one',
                 '/api/research-dossier?' + 'x' * 4097)
        fake = types.ModuleType('c02_dossier')
        fake.build_dossier = lambda *args, **kwargs: self.fail('invalid request reached the builder')
        with patch.dict(sys.modules, {'c02_dossier': fake}):
            for path in cases:
                with self.subTest(path=path[:45]):
                    self.assertEqual(self.request(path, self.authorized())[0], 400)

    def test_comparison_is_server_derived_and_no_store(self):
        projection = {'dataset': 'D16', 'selected': None, 'claims': []}
        sentinel = {'status': 'evidence_only', 'model_status': 'model_unavailable', 'entries': []}
        fake = types.ModuleType('c02_dossier')
        received = []
        def build(value, *, source_refs):
            received.append((value, source_refs))
            return sentinel
        fake.build_dossier = build
        sources = {'records': [{'key': 'd13:sources:1', 'record_kind': 'source'},
                               {'key': 'not-a-safe-coordinate', 'record_kind': 'source'},
                               {'key': 'd13:sources:2', 'record_kind': 'claim'}]}
        with patch.dict(sys.modules, {'c02_dossier': fake}), patch.object(api, 'compare_passages', return_value=projection) as compare, patch.object(api, 'filter_records', return_value=sources) as source_filter:
            status, headers, body = self.request(headers=self.authorized())
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), sentinel)
        self.assertEqual(received, [(projection, frozenset({'d13:sources:1'}))])
        compare.assert_called_once_with(self.server.dataset, {'corpus': ['synthetic'], 'scheme': ['synthetic'], 'reference': ['one']})
        source_filter.assert_called_once_with(self.server.dataset, {'record_kind': ['source']}, _internal_all=True)
        self.assertIn('no-store', headers['Cache-Control'])
        self.assertIn("default-src 'none'", headers['Content-Security-Policy'])
        self.assertNotIn('Access-Control-Allow-Origin', headers)

    def test_real_builder_empty_comparison_preserves_unavailable_model(self):
        status, _, body = self.request(headers=self.authorized())
        self.assertEqual(status, 200)
        result = json.loads(body)
        self.assertEqual(result['status'], 'evidence_only')
        self.assertEqual(result['model_status'], 'model_unavailable')
        self.assertEqual(result['entries'], [])

    def test_real_builder_shows_only_linked_safe_projection(self):
        from test_c02_dossier import projection
        safe = projection()
        sources = {'records': [{'key': 'd14:sources:1', 'record_kind': 'source'}]}
        with patch.object(api, 'compare_passages', return_value=safe), patch.object(api, 'filter_records', return_value=sources):
            status, _, body = self.request(headers=self.authorized())
        self.assertEqual(status, 200)
        result = json.loads(body)
        self.assertEqual(result['model_status'], 'model_unavailable')
        item = result['entries'][0]
        self.assertEqual(item['source']['ref'], 'd14:sources:1')
        self.assertEqual(item['source']['title']['value'], 'SYNTHETIC TITLE')
        self.assertEqual(item['summary']['status'], 'local_input_candidate')
        self.assertEqual(item['statuses']['authority_status'], 'unconfirmed')


if __name__ == '__main__':
    unittest.main()
