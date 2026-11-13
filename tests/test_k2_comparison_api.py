"""Synthetic-only exact-address comparison and loopback API tests."""
import contextlib
import http.client
import io
import sys
import threading
import unittest
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from j2_private_preview import compare_passages, PrivatePreviewServer
from k2_bridge.receipt import _TraditionIndex

SCHEME = 'd12_scheme_1'

def synthetic_dataset():
    def claim(n, reference, *, stage='d12', scheme=SCHEME):
        return {'key': f'{stage}:claims:{n}', 'stage': stage, 'record_kind': 'claim',
                'passages': [{'corpus': 'Bible_1' if stage == 'd12' else 'Bible', 'scheme': scheme, 'reference': reference}],
                'summary': 'SYNTHETIC-PRIVATE-TEXT', 'attribution': 'individual_opinion',
                'verification_status': 'source_checked', 'independent_review_status': 'pending'}
    return {'dataset': 'D12', 'records': [claim(1, 'John 1:1'), claim(2, 'John 1:1'),
                                           claim(3, 'John 1:2'), claim(1, 'John 1:1', stage='d9', scheme='chapter_verse_edition_alignment_pending')],
            'counts': {}, 'warnings': []}

class ComparisonApiTests(unittest.TestCase):
    def test_exact_address_group_never_infers_rebuttal(self):
        data = synthetic_dataset()
        result = compare_passages(data, {'stage': ['d12'], 'corpus': ['Bible_1'],
                                         'scheme': [SCHEME], 'reference': ['John 1:1']})
        self.assertEqual(len(result['claims']), 2)
        self.assertEqual(result['passages'][0]['claim_count'], 2)
        for claim in result['claims']:
            self.assertIsNone(claim['summary'])
            self.assertEqual(claim['summary_status'], 'pending_review')
            self.assertEqual(claim['relationships'], [])
            self.assertEqual(claim['authority_status'], 'pending_authority')
            self.assertEqual(claim['independent_review_status'], 'pending')

    def test_exact_reference_and_stage_scope(self):
        data = synthetic_dataset()
        selected = {'corpus': ['Bible_1'], 'scheme': [SCHEME], 'reference': ['John 1:1']}
        self.assertEqual(len(compare_passages(data, selected)['claims']), 2)
        self.assertEqual(len(compare_passages(data, {**selected, 'stage': ['d12']})['claims']), 2)
        self.assertEqual(compare_passages(data, {**selected, 'reference': ['John 1:']})['claims'], [])
        with self.assertRaises(ValueError): compare_passages(data, {'reference': ['John 1:1']})
        with self.assertRaises(ValueError): compare_passages(data, {'stage': ['d13']})

    def test_forged_input_summary_cannot_authorize_display(self):
        data = synthetic_dataset()
        data['_k2_summary_index'] = {'d12:claims:1': 'SYNTHETIC-FORGED-SUMMARY'}
        selected = {'stage': ['d12'], 'corpus': ['Bible_1'], 'scheme': [SCHEME], 'reference': ['John 1:1']}
        result = compare_passages(data, selected)
        self.assertTrue(all(row['summary'] is None and row['summary_status'] == 'pending_review' for row in result['claims']))

    def test_unlinked_passage_is_visible_but_has_no_invented_claim(self):
        data = synthetic_dataset()
        data['_k2_passages'] = [{'corpus': 'Bible_1', 'scheme': SCHEME, 'reference': 'John 1:3'}]
        selected = {'stage': ['d12'], 'corpus': ['Bible_1'], 'scheme': [SCHEME], 'reference': ['John 1:3']}
        result = compare_passages(data, selected)
        self.assertEqual(result['selected']['reference'], 'John 1:3')
        self.assertEqual(result['claims'], [])
        self.assertEqual(next(p['claim_count'] for p in result['passages'] if p['reference'] == 'John 1:3'), 0)

    def test_tradition_filter_only_uses_local_sealed_label(self):
        data = synthetic_dataset()
        query = {'stage': ['d12'], 'corpus': ['Bible_1'], 'scheme': [SCHEME],
                 'reference': ['John 1:1'], 'tradition': ['SYNTHETIC-TRADITION']}
        data['_k2_tradition_index'] = {'d12:claims:1': 'SYNTHETIC-TRADITION'}
        self.assertEqual(compare_passages(data, query)['claims'], [])
        data['_k2_tradition_index'] = _TraditionIndex({'d12:claims:1': 'SYNTHETIC-TRADITION'})
        result = compare_passages(data, query)
        self.assertEqual(len(result['claims']), 1)
        self.assertEqual(result['claims'][0]['tradition_candidate']['status'], 'recorded_unverified')
        self.assertEqual(result['claims'][0]['authority_status'], 'pending_authority')
        self.assertIsNone(result['claims'][0]['speaker'])

    def test_comparison_reads_all_pages_and_deduplicates_addresses(self):
        data = synthetic_dataset(); template = data['records'][0]
        data['records'] = [dict(template, key=f'd12:claims:{n}', passages=template['passages'] * 2)
                           for n in range(1, 132)]
        result = compare_passages(data, {'stage': ['d12'], 'corpus': ['Bible_1'],
                                         'scheme': [SCHEME], 'reference': ['John 1:1']})
        self.assertEqual(len(result['claims']), 131)
        self.assertEqual(result['passages'][0]['claim_count'], 131)

    def test_loopback_authentication_and_no_store(self):
        secret = 'synthetic-session-secret-at-least-20-characters'
        server = PrivatePreviewServer(synthetic_dataset(), secret)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        error = io.StringIO()
        try:
            with contextlib.redirect_stderr(error):
                conn = http.client.HTTPConnection('127.0.0.1', server.server_address[1], timeout=5)
                conn.request('GET', '/api/comparison'); response = conn.getresponse()
                self.assertEqual(response.status, 401); response.read(); conn.close()
                conn = http.client.HTTPConnection('127.0.0.1', server.server_address[1], timeout=5)
                conn.request('GET', '/api/comparison?' + urlencode({'stage': 'd12'}),
                             headers={'Authorization': 'Bearer ' + secret})
                response = conn.getresponse(); self.assertEqual(response.status, 200)
                self.assertIn('no-store', response.getheader('Cache-Control'))
                self.assertNotIn(b'SYNTHETIC-PRIVATE-TEXT', response.read()); conn.close()
                conn = http.client.HTTPConnection('127.0.0.1', server.server_address[1], timeout=5)
                conn.request('GET', '/api/comparison', headers={'Origin': 'https://example.invalid'})
                response = conn.getresponse(); self.assertEqual(response.status, 403); response.read(); conn.close()
            self.assertNotIn('John 1:1', error.getvalue())
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=5)

if __name__ == '__main__': unittest.main()
