#!/usr/bin/env python3
"""Read-only D7 validation; no database connection, write or promotion."""
import argparse
import json
import sys
from pathlib import Path
from j1_bridge.d7 import inspect_archive

def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('mode',choices=('validate','dry-run','mapping-preview'))
 p.add_argument('archive',type=Path)
 p.add_argument('--output',type=Path,help='Create a new safe coordinate-only report; never overwrite')
 a=p.parse_args(argv)
 result=inspect_archive(a.archive,mode=a.mode)
 payload=json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+'\n'
 if a.output:
  try:
   with a.output.open('x',encoding='utf8') as stream:stream.write(payload)
  except OSError:
   print('Cannot create a new report; no existing file was overwritten.',file=sys.stderr);return 2
 else:sys.stdout.write(payload)
 return 0 if result['status']=='pass' else 1
if __name__=='__main__':raise SystemExit(main())
