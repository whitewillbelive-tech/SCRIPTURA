"""Synthetic-only checks for the local C-01 analysis HTTP boundary."""
import http.client
import json
import socket
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import j2_private_preview as api

SECRET = 'synthetic-only-secret-for-tests'
PAYLOAD = {'question': 'Synthetic question?', 'mode': 'comparison',
           'corpus': '', 'scheme': '', 'reference': ''}


class AnalysisHTTPTests(unittest.TestCase):
    def setUp(self):
        self.server = api.PrivatePreviewServer({'dataset': 'D16', 'records': []}, SECRET)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join()

    def request(self, body=None, headers=None, method='POST', path='/api/research-analysis'):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_address[1], timeout=5)
        try:
            conn.request(method, path, body=body, headers={'Host': self.server.expected_host, **(headers or {})})
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            conn.close()

    def authorized(self):
        return {'Authorization': 'Bearer ' + SECRET, 'Content-Type': 'application/json',
                'Origin': self.server.expected_origin}

    def test_session_and_origin_are_required(self):
        body = json.dumps(PAYLOAD)
        self.assertEqual(self.request(body, {'Content-Type': 'application/json'})[0], 401)
        self.assertEqual(self.request(body, {**self.authorized(), 'Origin': 'http://attacker.invalid'})[0], 403)
        self.assertEqual(self.request(body, {**self.authorized(), 'Sec-Fetch-Site': 'cross-site'})[0], 403)

    def test_unavailable_model_is_explicit_and_no_cache(self):
        status, headers, data = self.request(json.dumps(PAYLOAD), self.authorized())
        self.assertEqual(status, 200)
        result = json.loads(data)
        self.assertEqual(result['status'], 'model_unavailable')
        self.assertEqual(result['sections'], [])
        self.assertEqual(result['evidence'], [])
        self.assertIn('no-store', headers['Cache-Control'])
        self.assertNotIn('Access-Control-Allow-Origin', headers)

    def test_input_rejects_extra_records_invalid_json_and_oversized(self):
        self.assertEqual(self.request(json.dumps({**PAYLOAD, 'evidence': []}), self.authorized())[0], 400)
        self.assertEqual(self.request('{"question":"x","question":"y"}', self.authorized())[0], 400)
        self.assertEqual(self.request('x' * 8193, self.authorized())[0], 413)
        self.assertEqual(self.request(json.dumps(PAYLOAD), {**self.authorized(), 'Content-Type': 'text/plain'})[0], 400)

    def test_other_methods_remain_disabled(self):
        for method in ('PUT', 'PATCH', 'DELETE', 'OPTIONS'):
            self.assertEqual(self.request('', self.authorized(), method=method)[0], 405)
        self.assertEqual(self.request('', self.authorized(), path='/unexpected')[0], 405)

    def test_evidence_comes_only_from_safe_exact_comparison(self):
        request = {**PAYLOAD, 'corpus': 'bible', 'scheme': 'synthetic', 'reference': 'one'}
        self.server.dataset['records'].append({'key': 'd14:sources:1', 'record_kind': 'source'})
        projected = {'claims': [{'key': 'd13:claims:1', 'source_key': 'd14:sources:1', 'summary': 'PRIVATE SYNTHETIC TEXT'},
                                {'key': 'external-unsanitized-id', 'source_key': 'd14:sources:999'}]}
        with patch.object(api, 'compare_passages', return_value=projected) as compare:
            status, _, body = self.request(json.dumps(request), self.authorized())
        self.assertEqual(status, 200)
        compare.assert_called_once()
        result = json.loads(body)
        self.assertEqual([e['ref'] for e in result['evidence']], ['d13:claims:1', 'd14:sources:1'])
        self.assertEqual([e['kind'] for e in result['evidence']], ['claim', 'source'])
        self.assertNotIn('PRIVATE SYNTHETIC TEXT', body.decode('utf-8'))
        self.assertEqual(result['status'], 'model_unavailable')

    def test_incomplete_body_has_bounded_worker_time(self):
        with socket.create_connection(('127.0.0.1', self.server.server_address[1]), timeout=5) as conn:
            request = ('POST /api/research-analysis HTTP/1.1\r\n'
                       f'Host: {self.server.expected_host}\r\n'
                       f'Authorization: Bearer {SECRET}\r\n'
                       'Content-Type: application/json\r\nContent-Length: 100\r\n\r\nx')
            conn.sendall(request.encode('ascii'))
            self.assertIn(b' 408 ', conn.recv(512))

    def test_trickled_body_cannot_extend_total_deadline(self):
        with socket.create_connection(('127.0.0.1', self.server.server_address[1]), timeout=5) as conn:
            request = ('POST /api/research-analysis HTTP/1.1\r\n'
                       f'Host: {self.server.expected_host}\r\n'
                       f'Authorization: Bearer {SECRET}\r\n'
                       'Content-Type: application/json\r\nContent-Length: 100\r\n\r\nx')
            conn.sendall(request.encode('ascii'))
            stop = threading.Event()
            def trickle():
                while not stop.wait(0.25):
                    try:
                        conn.sendall(b'x')
                    except OSError:
                        return
            sender = threading.Thread(target=trickle, daemon=True)
            sender.start()
            start = time.monotonic()
            try:
                self.assertIn(b' 408 ', conn.recv(512))
                self.assertLess(time.monotonic() - start, 4.5)
            finally:
                stop.set()
                sender.join()

    def test_graph_is_authenticated_exact_and_pending(self):
        path = '/api/research-graph?corpus=bible&scheme=synthetic&reference=one'
        self.assertEqual(self.request(None, method='GET', path=path)[0], 401)
        projected = {'selected': {'corpus': 'bible', 'scheme': 'synthetic', 'reference': 'one'},
                     'claims': [{'key': 'd13:claims:1', 'summary': 'PRIVATE SYNTHETIC TEXT'},
                                {'key': 'raw-private-id'}, {'key': 'd13:claims:1'}]}
        with patch.object(api, 'compare_passages', return_value=projected):
            status, headers, body = self.request(None, self.authorized(), method='GET', path=path)
        self.assertEqual(status, 200)
        self.assertIn('no-store', headers['Cache-Control'])
        result = json.loads(body)
        self.assertEqual(len(result['edges']), 1)
        self.assertEqual(result['edges'][0]['status'], 'pending')
        self.assertEqual(result['edges'][0]['kind'], 'relation_candidate')
        self.assertEqual(result['edges'][0]['asserted_kind'], 'about_passage')
        self.assertNotIn('PRIVATE SYNTHETIC TEXT', body.decode('utf-8'))
        self.assertNotIn('raw-private-id', body.decode('utf-8'))
        self.assertEqual(self.request(None, self.authorized(), method='GET',
                        path='/api/research-graph?corpus=bible&scheme=synthetic')[0], 400)


if __name__ == '__main__':
    unittest.main()
