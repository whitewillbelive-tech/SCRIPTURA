#!/usr/bin/env python3
"""Time a generated-only passage comparison; never accepts research input."""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from j2_private_preview import compare_passages


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--records', type=int, choices=(10000, 100000, 200000), required=True)
    size = parser.parse_args().records
    entries = [
        {'key': f'd12:claims:{n}', 'stage': 'd12', 'record_kind': 'claim',
         'passages': [{'corpus': 'Bible_1', 'scheme': 'd12_scheme_1', 'reference': 'John 1:1'}],
         'summary': 'SYNTHETIC-NOT-APPROVED', 'attribution': 'individual_opinion'}
        for n in range(1, size + 1)
    ]
    dataset = {'dataset': 'D12', 'records': entries, 'counts': {}, 'warnings': []}
    start = time.monotonic()
    response = compare_passages(dataset, {'stage': ['d12'], 'corpus': ['Bible_1'],
                                          'scheme': ['d12_scheme_1'], 'reference': ['John 1:1']})
    elapsed = time.monotonic() - start
    ok = (len(response['claims']) == size and len(response['passages']) == 1
          and response['passages'][0]['claim_count'] == size
          and all(row['summary'] is None for row in response['claims']))
    print(json.dumps({'dataset': 'synthetic_only', 'requested_records': size,
                      'returned_claims': len(response['claims']),
                      'unapproved_summaries_hidden': ok,
                      'seconds': round(elapsed, 3), 'status': 'pass' if ok else 'fail'},
                     sort_keys=True))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
