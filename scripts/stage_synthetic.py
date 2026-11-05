#!/usr/bin/env python3
"""Stage an internally generated synthetic fixture, never an external ZIP."""
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

from d2_bridge.staging import StagingError, stage_synthetic


def main():
    if len(sys.argv) != 1:
        print('No input paths or options are accepted.', file=sys.stderr)
        return 2
    fixture_path = Path(__file__).resolve().parents[1] / 'tests' / 's1b2_synthetic_factory.py'
    spec = importlib.util.spec_from_file_location('s1b2_synthetic_factory', fixture_path)
    factory = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(factory)
    with tempfile.TemporaryDirectory(prefix='scriptura-synthetic-cli-') as directory:
        path = Path(directory) / 'synthetic.zip'
        sha, counts = factory.write_archive(path)
        try:
            report = stage_synthetic(path, expected_sha256=sha, expected_counts=counts, expected_snapshot=factory.SNAPSHOT)
        except StagingError as exc:
            print(json.dumps({'status': 'fail', 'reason': str(exc)}), file=sys.stderr)
            return 1
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
