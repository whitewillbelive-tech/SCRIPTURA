#!/usr/bin/env python3
"""Only synthetic data, solely for local browser integration tests."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from j2_private_preview import PrivatePreviewServer


def sample_data():
    return {
        'dataset': 'synthetic',
        'counts': {'d8': {'sources': 2, 'claims': 2}},
        'warnings': ['합성 시험 자료 / 실제 연구 데이터 아님'],
        'facets': {},
        'unmapped_summary': {'d8': {'claims': {'input_count': 2, 'mapping': 'partial'}, 'conflicts': {'input_count': 1, 'mapping': 'unmapped'}}},
        'records': [
            {'key': 'synthetic:claim:1', 'stage': 'D8', 'record_kind': 'claim',
             'tradition': '가상 전통 A', 'researcher': '가상 연구자', 'speaker': '가상 발화자',
             'source_title': '가상 문헌 A', 'source_creator': '가상 저자', 'source_kind': 'article',
             'source_doi': None, 'source_year': 2020, 'passage_corpus': '가상 코퍼스',
             'passage_scheme': '가상 체계', 'passage_reference': '가상 1:1',
             'passages': [{'corpus': '가상 코퍼스', 'scheme': '가상 체계', 'reference': '가상 1:1'}],
             'attribution': 'individual_opinion', 'authority_status': 'unknown',
             'verification_status': 'source_checked', 'independent_review_status': 'not_done',
             'rights_status': 'unresolved', 'rights': {'browse': 'unknown', 'store_excerpt': 'conditional'},
             'rights_overrides': [{'action': 'browse', 'previous_decision': 'unknown', 'new_decision': 'conditional', 'evidence': 'recorded'}], 'access_path': 'search_only',
             'locator': None, 'summary': None, 'evidence': [{'kind': 'support', 'status': 'pending'}],
             'relationships': [{'kind': 'contrast', 'status': 'pending', 'target_key': 'synthetic:claim:2'}],
             'unmapped': ['authority']},
            {'key': 'synthetic:claim:2', 'stage': 'D8', 'record_kind': 'claim',
             'tradition': '가상 전통 B', 'researcher': '다른 연구자', 'speaker': '다른 발화자',
             'source_title': '가상 문헌 B', 'source_creator': '다른 저자', 'source_kind': 'book',
             'source_doi': None, 'source_year': 1951, 'passage_corpus': '다른 코퍼스',
             'passage_scheme': '다른 체계', 'passage_reference': '가상 2:1',
             'passages': [{'corpus': '다른 코퍼스', 'scheme': '다른 체계', 'reference': '가상 2:1'}],
             'attribution': 'external_critique', 'authority_status': 'unknown',
             'verification_status': 'pending', 'independent_review_status': 'not_done',
             'rights_status': 'unresolved', 'rights': {'browse': 'unknown', 'store_excerpt': 'unknown'}, 'rights_overrides': [], 'access_path': 'secondary',
             'locator': None, 'summary': None, 'evidence': [], 'relationships': [], 'unmapped': []},
        ],
    }

if __name__ == '__main__':
    # Explicitly test-only secret is supplied by the test process; never real data.
    secret = os.environ.get('SCRIPTURA_TEST_SECRET', '')
    server = PrivatePreviewServer(sample_data(), secret)
    print('READY http://' + server.expected_host, flush=True)
    try:
        server.serve_forever(poll_interval=0.1)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
