#!/usr/bin/env python3
"""Read-only authority-gap analysis of the pinned D4 archive."""
import argparse
import json
import sys
from pathlib import Path
from i2_bridge.d4 import inspect_archive


def main(argv=None):
    parser=argparse.ArgumentParser(description='Inspect the fixed D4 research ZIP without database writes or status promotion.')
    parser.add_argument('archive',type=Path)
    parser.add_argument('--output',type=Path,help='Create a new aggregate/hash-only report; existing files are never overwritten')
    args=parser.parse_args(argv)
    result=inspect_archive(args.archive)
    data=json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+'\n'
    if args.output:
        try:
            with args.output.open('x',encoding='utf-8') as f:f.write(data)
        except OSError:
            print('Cannot create report; no existing file was overwritten.',file=sys.stderr)
            return 2
    else:sys.stdout.write(data)
    return 0 if result['status']=='pass' else 1


if __name__=='__main__':raise SystemExit(main())
