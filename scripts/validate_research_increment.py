"""Read-only opt-in validation of two separately trusted v1 research archives.

This command does not process the historical D-8 through D-13 ZIP format.
It provides the new generic contract only; trust-policy digests must be
authenticated out of band before use. No archive may supply its own trust.
Paths in command arguments can be visible in shell history/process listings.
"""
import argparse
import hashlib
import json
import re
import sys

from k3_bridge.pipeline import PipelineError, ResearchPipeline

_MAX_ZIP = 64 * 1024 * 1024
_MAX_POLICY = 16 * 1024
_KEYS = frozenset(('schema', 'baseline_archive_sha256', 'baseline_manifest_sha256',
                   'baseline_root_sha256', 'increment_archive_sha256', 'increment_manifest_sha256'))


class _PrivateParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default error includes user-supplied values and paths.
        raise ValueError('invalid_arguments')


def _read_local(path, limit):
    if (not isinstance(path, str) or not path or path.startswith(('\\\\', '//', '\\/', '/\\'))
            or re.match(r'^[A-Za-z][A-Za-z0-9+.-]*://', path)):
        raise ValueError('local_input_required')
    with open(path, 'rb') as stream:
        blob = stream.read(limit + 1)
    if len(blob) > limit:
        raise ValueError('input_too_large')
    return blob


def _pairs(pairs):
    output = {}
    for key, value in pairs:
        if key in output:
            raise ValueError('invalid_policy')
        output[key] = value
    return output


def main(argv=None):
    parser = _PrivateParser(description='Validate local v1 research archives without writing data.')
    parser.add_argument('--baseline', required=True)
    parser.add_argument('--increment', required=True)
    parser.add_argument('--trust-policy', required=True)
    try:
        args = parser.parse_args(argv)
        policy_blob = _read_local(args.trust_policy, _MAX_POLICY)
        policy = json.loads(policy_blob.decode('utf-8'), object_pairs_hook=_pairs)
        if not isinstance(policy, dict) or set(policy) != _KEYS or policy.get('schema') != 'scriptura.local-trust-policy.v1':
            raise ValueError('invalid_policy')
        baseline_blob = _read_local(args.baseline, _MAX_ZIP)
        increment_blob = _read_local(args.increment, _MAX_ZIP)
        pipeline = ResearchPipeline.bootstrap(
            baseline_blob, archive_sha256=policy['baseline_archive_sha256'],
            manifest_sha256=policy['baseline_manifest_sha256'], root_sha256=policy['baseline_root_sha256'])
        result = pipeline.advance(increment_blob, archive_sha256=policy['increment_archive_sha256'],
                                  manifest_sha256=policy['increment_manifest_sha256'])
        # Confirm all three local inputs remained byte-identical. No digest,
        # filename, source identifier or content is written to output.
        for path, original, limit in ((args.baseline, baseline_blob, _MAX_ZIP),
                                      (args.increment, increment_blob, _MAX_ZIP),
                                      (args.trust_policy, policy_blob, _MAX_POLICY)):
            if hashlib.sha256(_read_local(path, limit)).digest() != hashlib.sha256(original).digest():
                raise ValueError('input_changed')
        result_summary = result.summary()
        relation_summary = result.relation_index().summary()
        # The public report is fixed-key numeric aggregation only.
        output = {'baseline_preserved': True,
                  'increment_input_rows': result_summary['last_input_rows'],
                  'increment_accepted_rows': result_summary['last_accepted_rows'],
                  'increment_quarantined_rows': result_summary['last_quarantined_rows'],
                  'cumulative_claims': result_summary['claims'],
                  'cumulative_sources': result_summary['sources'],
                  'relation_claims': relation_summary['claims'],
                  'relation_citations_linked': relation_summary['citation_linked'],
                  'independent_scholarly_approvals': 0}
        print(json.dumps(output, sort_keys=True, separators=(',', ':')))
        return 0
    except (Exception, SystemExit) as exc:
        if isinstance(exc, SystemExit) and exc.code == 0:
            return 0
        print('validation_unavailable', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
