"""Read-only, aggregate-only diagnostic for D-12 withheld candidate summaries.

Usage: python scripts/audit_d12_withheld.py <local-D12-research-zip>
The path may appear in shell history or operating-system process listings.
The diagnostic never writes the archive or outputs research values or paths.
"""
import contextlib
import io
import json
import os
import re
import sys

from i3_bridge.d6 import _bounded_read, _sha
from k2_bridge.receipt import D12_SHA, _read_layers, load_k2_archive
from k37_bridge.d12_withheld_audit import audit_d12_withheld


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print('invalid_arguments')
        return 2
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            path = os.fspath(args[0])
            if (not isinstance(path, str) or path.startswith(('\\\\', '//', '\\/', '/\\'))
                    or re.match(r'^(?![A-Za-z]:[\\/])[A-Za-z][A-Za-z0-9+.-]*:', path)):
                raise ValueError('invalid')
            blob = _bounded_read(path)
            if _sha(blob) != D12_SHA:
                raise ValueError('invalid')
            dataset = load_k2_archive(blob)
            layers, _ = _read_layers(blob)
            result = audit_d12_withheld(layers, dataset).summary()
            result['archive_unchanged'] = _sha(_bounded_read(path)) == D12_SHA
            if result['archive_unchanged'] is not True:
                raise ValueError('changed')
        print(json.dumps(result, sort_keys=True, separators=(',', ':')))
        return 0
    except Exception:
        print('d12_withheld_audit_unavailable')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
