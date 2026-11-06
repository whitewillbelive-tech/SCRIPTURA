#!/usr/bin/env python3
"""Inspect the pinned research archive without write or promotion capabilities."""
import argparse
import json
import sys
from pathlib import Path
from i3_bridge.d6 import inspect_archive


def main(argv=None):
 p=argparse.ArgumentParser(description='I-3 read-only pinned D6 receipt; no database connection or promotion.')
 p.add_argument('mode',choices=('validate','dry-run','mapping-preview'))
 p.add_argument('archive',type=Path)
 p.add_argument('--output',type=Path,help='Create a new public hash-only report; existing paths are never overwritten')
 a=p.parse_args(argv); result=inspect_archive(a.archive,mode=a.mode)
 payload=json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+'\n'
 if a.output:
  try:
   with a.output.open('x',encoding='utf8') as f:f.write(payload)
  except OSError:
   print('Cannot create a new report; no existing file was overwritten.',file=sys.stderr);return 2
 else:sys.stdout.write(payload)
 return 0 if result['status']=='pass' else 1

if __name__=='__main__':raise SystemExit(main())
