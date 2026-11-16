#!/usr/bin/env python3
"""Measure the evidence dossier with generated records only."""
import argparse
import time
from j2_private_preview import research_dossier


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--records', type=int, choices=(10000, 100000, 200000), required=True)
    size = parser.parse_args().records
    rows = [{'key': f'd12:claims:{n}', 'stage': 'd12', 'record_kind': 'claim',
             'passages': [{'corpus': 'Bible_1', 'scheme': 'd12_scheme_1', 'reference': 'John 1:1'}],
             'summary': 'SYNTHETIC-NOT-APPROVED'} for n in range(1, size + 1)]
    dataset = {'dataset': 'D12', 'records': rows, 'counts': {}, 'warnings': []}
    started = time.monotonic()
    result = research_dossier(dataset, {'corpus': ['Bible_1'], 'scheme': ['d12_scheme_1'], 'reference': ['John 1:1']})
    ok = (len(result['entries']) == 100 and result['truncated'] is True
          and result['model_status'] == 'model_unavailable'
          and all(not row['summary']['value'] for row in result['entries']))
    print(f'synthetic_records={size} returned={len(result["entries"])} '
          f'elapsed_seconds={time.monotonic() - started:.3f} withheld_ok={ok} '
          f'status={"PASS" if ok else "FAIL"}')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
