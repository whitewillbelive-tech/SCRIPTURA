#!/usr/bin/env python3
"""Measure generated synthetic archives only; never accepts external datasets."""
from __future__ import annotations
import argparse
import json
import multiprocessing as mp
import os
import platform
import queue
import resource
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
sys.path.insert(0, str(ROOT / 'scripts'))
from s1b2_synthetic_factory import SNAPSHOT, synthetic_rows, write_archive
from d2_bridge.validator import validate_archive


def _generation(n, path, q):
    try:
        start = time.monotonic()
        rows = synthetic_rows(source_count=n)
        checksum, counts = write_archive(path, rows)
        q.put({'status':'pass', 'source_count':n, 'merged_records':sum(counts.values()),
               'archive_bytes':Path(path).stat().st_size, 'sha256':checksum,
               'counts':counts, 'elapsed_seconds':round(time.monotonic()-start, 3),
               'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss})
    except BaseException as exc:
        q.put({'status':'fail', 'error_type':type(exc).__name__})


def _validation(path, generation, q):
    try:
        start=time.monotonic()
        report, records=validate_archive(path, expected_sha256=generation['sha256'],
            expected_snapshot=SNAPSHOT, expected_counts=generation['counts'], allow_synthetic=True)
        elapsed=round(time.monotonic()-start, 3)
        count=sum(len(x) for x in records.values())
        good=(report.get('status')=='pass' and count==generation['merged_records'] and
              report.get('dispositions',{}).get('quarantined')==count)
        q.put({'status':'pass' if good else 'fail', 'validated_records':count,
               'elapsed_seconds':elapsed,
               'records_per_second':round(count/elapsed,1) if elapsed else None,
               'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
               'error_counts':report.get('errors',{}),
               'dispositions':report.get('dispositions',{})})
    except BaseException as exc:
        q.put({'status':'fail', 'error_type':type(exc).__name__})


def _run(ctx, fn, *args):
    q=ctx.Queue()
    p=ctx.Process(target=fn, args=(*args,q))
    p.start(); p.join(600)
    if p.is_alive():
        p.terminate(); p.join()
        return {'status':'fail','error_type':'Timeout'}
    if p.exitcode!=0:
        return {'status':'fail','error_type':'WorkerFailed','exit_code':p.exitcode}
    try:
        result=q.get(timeout=5)
    except queue.Empty:
        result={'status':'fail','error_type':'WorkerProducedNoResult'}
    finally:
        q.close()
    return result


def main():
    parser=argparse.ArgumentParser(description='Synthetic-only D-2 archive generation and validation benchmark')
    parser.add_argument('--sources', type=int, choices=(10000,100000), required=True)
    args=parser.parse_args()
    ctx=mp.get_context('spawn')
    with tempfile.TemporaryDirectory(prefix='scriptura-synthetic-benchmark-') as tmp:
        path=str(Path(tmp)/'synthetic.zip')
        generation=_run(ctx,_generation,args.sources,path)
        validation=_run(ctx,_validation,path,generation) if generation.get('status')=='pass' else {'status':'skipped','reason':'generation_failed'}
    result={'kind':'synthetic_test_only','platform':platform.platform(), 'python':platform.python_version(),
            'cpu_count':os.cpu_count(), 'measurement':'separate processes; RSS is per-process maximum; source count plus small linked fixtures',
            'generation':generation, 'validation':validation,
            'status':'pass' if generation.get('status')=='pass' and validation.get('status')=='pass' else 'fail'}
    print(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True))
    return 0 if result['status']=='pass' else 1

if __name__=='__main__':
    sys.exit(main())
