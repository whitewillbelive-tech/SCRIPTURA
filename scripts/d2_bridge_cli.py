#!/usr/bin/env python3
"""Read-only checks for the pinned D-2 snapshot; never prints source records."""
import argparse
import json
import sys
from pathlib import Path

from d2_bridge.validator import validate_archive


def main(argv=None):
    parser = argparse.ArgumentParser(description='Validate or plan the pinned D-2 snapshot without writing to a database.')
    parser.add_argument('command', choices=('validate', 'dry-run'))
    parser.add_argument('archive', type=Path, help='Path to the unmodified frozen D-2 ZIP')
    parser.add_argument('--output', type=Path, help='Write aggregate report to a new file; never overwrite an existing file')
    args = parser.parse_args(argv)
    report, _private_records = validate_archive(args.archive)
    report['mode'] = args.command
    report['database_write'] = False
    report['canonical_import_authorized'] = False
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + '\n'
    if args.output is not None:
        try:
            with args.output.open('x', encoding='utf-8') as destination:
                destination.write(encoded)
        except OSError:
            print('Unable to create report file; no existing file was overwritten.', file=sys.stderr)
            return 2
    else:
        sys.stdout.write(encoded)
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
