"""Synthetic end-to-end coverage for independently anchored increments."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from k3_bridge.pipeline import PipelineError, ResearchPipeline


def pack(version, baseline_digest, tables):
    files, members = [], {}
    for table, rows in tables.items():
        name = 'records/' + table + '.jsonl'
        data = b''.join((json.dumps(row, ensure_ascii=True) + '\n').encode() for row in rows)
        members[name] = data
        files.append({'path': name, 'table': table, 'sha256': hashlib.sha256(data).hexdigest(), 'count': len(rows)})
    manifest = json.dumps({'schema': 'scriptura.research-archive.v1', 'version': version,
                           'baseline_sha256': baseline_digest, 'files': files}, sort_keys=True).encode()
    stream = io.BytesIO()
    with ZipFile(stream, 'w') as archive:
        archive.writestr('manifest.json', manifest)
        for name, data in members.items():
            archive.writestr(name, data)
    blob = stream.getvalue()
    return blob, hashlib.sha256(blob).hexdigest(), hashlib.sha256(manifest).hexdigest()


ROOT = '0' * 64


def base():
    tables = {'sources': [{'id': 'synthetic-source', 'title': 'SYNTHETIC TITLE'}],
              'editions': [{'id': 'synthetic-edition', 'source_id': 'synthetic-source'}],
              'locators': [{'id': 'synthetic-locator', 'source_id': 'synthetic-source', 'edition_id': 'synthetic-edition'}],
              'passages': [{'id': 'synthetic-passage', 'corpus': 'Bible', 'scheme': 'synthetic', 'reference': 'synthetic'}],
              'agents': [{'id': 'synthetic-agent', 'name': 'SYNTHETIC NAME'}]}
    blob, digest, manifest = pack('D1', ROOT, tables)
    return ResearchPipeline.bootstrap(blob, archive_sha256=digest, manifest_sha256=manifest, root_sha256=ROOT), digest


def delta(previous, extra=()):
    tables = {'claims': [{'id': 'synthetic-claim', 'source_locator_id': 'synthetic-locator', 'passage_ids': ['synthetic-passage'],
                           'speaker_id': 'synthetic-agent', 'attribution_kind': 'individual_opinion',
                           'statement_ko': 'SYNTHETIC CLAIM', 'reasoning_ko': 'SYNTHETIC REASON'}, *extra],
              'evidence': [{'id': 'synthetic-evidence', 'claim_id': 'synthetic-claim', 'locator_id': 'synthetic-locator'}]}
    return pack('D2', previous, tables)


class PipelineTests(unittest.TestCase):
    def test_validated_baseline_and_increment_feed_both_indexes(self):
        baseline, prior = base()
        blob, digest, manifest = delta(prior)
        result = baseline.advance(blob, archive_sha256=digest, manifest_sha256=manifest)
        self.assertEqual(baseline.summary()['claims'], 0)
        self.assertEqual(result.summary()['claims'], 1)
        relation = result.relation_index().for_claim('k4:claims:1')
        self.assertEqual(relation['kind'], 'individual_opinion')
        self.assertEqual(relation['speaker']['status'], 'recorded_unverified')
        self.assertEqual(relation['effective_official_status'], 'pending')
        review = {'claim_id': 'synthetic-claim', 'field': 'statement_ko',
                  'source_id': 'synthetic-source', 'edition_id': 'synthetic-edition',
                  'locator_id': 'synthetic-locator', 'evidence_id': 'synthetic-evidence',
                  'scope': 'private_local_display', 'self_authored': True, 'nonquotation': True,
                  'privacy_cleared': True, 'rights_cleared': True}
        approved = result.comparison_index([review], verifier=lambda *args: True)
        self.assertEqual(approved.for_claim('synthetic-claim')['statement_ko']['status'], 'recorded_unverified')
        self.assertNotIn('reasoning_ko', approved.for_claim('synthetic-claim'))
        denied = result.comparison_index([review], verifier=lambda *args: False)
        self.assertEqual(denied.for_claim('synthetic-claim'), {})
        self.assertNotIn('synthetic', repr(result))

    def test_bad_increment_leaves_prior_unchanged(self):
        baseline, prior = base()
        blob, _, manifest = delta(prior)
        with self.assertRaises(PipelineError):
            baseline.advance(blob, archive_sha256='f' * 64, manifest_sha256=manifest)
        self.assertEqual(baseline.summary()['sources'], 1)
        self.assertEqual(baseline.summary()['claims'], 0)

    def test_quarantine_bad_delta_and_preserve_baseline(self):
        baseline, prior = base()
        blob, digest, manifest = delta(prior, [{'id': 'synthetic-source'}])
        result = baseline.advance(blob, archive_sha256=digest, manifest_sha256=manifest)
        self.assertEqual(result.summary()['sources'], 1)
        self.assertEqual(result.summary()['claims'], 1)
        self.assertEqual(result.summary()['last_quarantined_rows'], 1)

    def test_wrong_baseline_link_is_rejected(self):
        baseline, _ = base()
        blob, digest, manifest = delta('a' * 64)
        with self.assertRaises(PipelineError):
            baseline.advance(blob, archive_sha256=digest, manifest_sha256=manifest)
        self.assertEqual(baseline.summary()['increments'], 0)

    def test_quarantined_root_is_not_a_trusted_baseline(self):
        blob, digest, manifest = pack('D1', ROOT, {'sources': [{'id': 'same', 'title': 'SYNTHETIC'}, {'id': 'same', 'title': 'SYNTHETIC'}]})
        with self.assertRaises(PipelineError):
            ResearchPipeline.bootstrap(blob, archive_sha256=digest, manifest_sha256=manifest, root_sha256=ROOT)

    def test_replayed_or_malformed_version_rejected(self):
        baseline, prior = base()
        for version in ('D1', 'D0', 'DX'):
            blob, digest, manifest = pack(version, prior, {'sources': [{'id': 'new', 'title': 'SYNTHETIC'}]})
            with self.subTest(version=version), self.assertRaises(PipelineError):
                baseline.advance(blob, archive_sha256=digest, manifest_sha256=manifest)

    def test_cross_baseline_semantic_conflicts_quarantine_dependants(self):
        baseline, prior = base()
        tables = {'sources': [{'id': 'second-source', 'title': 'SYNTHETIC SECOND'}],
                  'locators': [{'id': 'bad-locator', 'source_id': 'second-source', 'edition_id': 'synthetic-edition'}],
                  'claims': [{'id': 'bad-claim', 'source_locator_id': 'bad-locator', 'passage_ids': ['synthetic-passage']}],
                  'evidence': [{'id': 'bad-evidence', 'claim_id': 'bad-claim', 'locator_id': 'bad-locator'}]}
        blob, digest, manifest = pack('D2', prior, tables)
        result = baseline.advance(blob, archive_sha256=digest, manifest_sha256=manifest)
        self.assertEqual(result.summary()['sources'], 2)
        self.assertEqual(result.summary()['last_quarantined_semantic'], 3)
        self.assertEqual(result.summary()['claims'], 0)
        self.assertEqual(baseline.summary()['sources'], 1)

    def test_other_source_evidence_is_accepted(self):
        baseline, prior = base()
        tables = {'sources': [{'id': 'second-source', 'title': 'SYNTHETIC SECOND'}],
                  'editions': [{'id': 'second-edition', 'source_id': 'second-source'}],
                  'locators': [{'id': 'second-locator', 'source_id': 'second-source', 'edition_id': 'second-edition'}],
                  'claims': [{'id': 'claim', 'source_locator_id': 'synthetic-locator', 'passage_ids': ['synthetic-passage']}],
                  'evidence': [{'id': 'evidence', 'claim_id': 'claim', 'locator_id': 'second-locator'}]}
        blob, digest, manifest = pack('D2', prior, tables)
        result = baseline.advance(blob, archive_sha256=digest, manifest_sha256=manifest)
        self.assertEqual(result.summary()['claims'], 1)
        self.assertEqual(result.summary()['evidence'], 1)
        self.assertEqual(result.summary()['last_quarantined_semantic'], 0)

    def test_bootstrap_rejects_semantically_conflicting_claim(self):
        tables = {'sources': [{'id': 's', 'title': 'SYNTHETIC A'}, {'id': 'other', 'title': 'SYNTHETIC B'}],
                  'editions': [{'id': 'e', 'source_id': 's'}],
                  'locators': [{'id': 'l', 'source_id': 's', 'edition_id': 'e'}],
                  'passages': [{'id': 'p', 'corpus': 'Bible', 'scheme': 'synthetic', 'reference': 'synthetic'}],
                  'claims': [{'id': 'c', 'source_locator_id': 'l', 'source_id': 'other', 'passage_ids': ['p']}]}
        blob, digest, manifest = pack('D1', ROOT, tables)
        with self.assertRaises(PipelineError):
            ResearchPipeline.bootstrap(blob, archive_sha256=digest, manifest_sha256=manifest, root_sha256=ROOT)

    def test_duplicate_metadata_is_counted_not_merged(self):
        blob, digest, manifest = pack('D1', ROOT, {'sources': [{'id': 's1', 'title': 'SYNTHETIC TITLE', 'creator': 'SYNTHETIC PERSON', 'doi': '10.9999/synthetic'}]})
        baseline = ResearchPipeline.bootstrap(blob, archive_sha256=digest, manifest_sha256=manifest, root_sha256=ROOT)
        next_blob, next_digest, next_manifest = pack('D2', digest, {'sources': [{'id': 's2', 'title': 'Synthetic Title', 'creator': 'Synthetic Person', 'doi': '10.9999/synthetic'}]})
        result = baseline.advance(next_blob, archive_sha256=next_digest, manifest_sha256=next_manifest)
        self.assertEqual(result.summary()['sources'], 2)
        self.assertEqual(result.summary()['last_duplicate_doi_candidates'], 1)
        self.assertEqual(result.summary()['last_duplicate_title_creator_candidates'], 1)

    def test_explicit_relation_alias_requires_evidence_and_verifier(self):
        baseline, prior = base()
        claims = [{'id': ident, 'source_locator_id': 'synthetic-locator',
                   'passage_ids': ['synthetic-passage']} for ident in ('claim-one', 'claim-two')]
        relation = {'id': 'relation', 'from_claim_id': 'claim-one', 'to_claim_id': 'claim-two',
                    'relation_type': 'direct_rebuttal', 'source_locator_id': 'synthetic-locator'}
        blob, digest, manifest = pack('D2', prior, {'claims': claims, 'relationships': [relation]})
        result = baseline.advance(blob, archive_sha256=digest, manifest_sha256=manifest)
        self.assertEqual(result.summary()['relationships'], 1)
        pending = result.comparison_index([], verifier=lambda *args: False).relations_for('claim-one')
        self.assertEqual(pending[0]['kind'], 'unconfirmed_relation')
        self.assertEqual(pending[0]['status'], 'pending_evidence_review')
        confirmed = result.comparison_index([], verifier=lambda *args: True).relations_for('claim-one')
        self.assertEqual(confirmed[0]['kind'], 'rebuts')
        relation.pop('source_locator_id')
        blob2, digest2, manifest2 = pack('D2', prior, {'claims': claims, 'relationships': [relation]})
        without_evidence = baseline.advance(blob2, archive_sha256=digest2, manifest_sha256=manifest2)
        self.assertEqual(without_evidence.comparison_index([], verifier=lambda *args: True).relations_for('claim-one'), [])

    def test_cli_executes_local_trusted_pipeline_without_disclosing_inputs(self):
        tables = {'sources': [{'id': 's', 'title': 'SYNTHETIC PRIVATE SENTINEL'}],
                  'editions': [{'id': 'e', 'source_id': 's'}],
                  'locators': [{'id': 'l', 'source_id': 's', 'edition_id': 'e'}],
                  'passages': [{'id': 'p', 'corpus': 'Bible', 'scheme': 'synthetic', 'reference': 'synthetic'}]}
        first, first_hash, first_manifest = pack('D1', ROOT, tables)
        second, second_hash, second_manifest = pack('D2', first_hash, {'claims': [{'id': 'c', 'source_locator_id': 'l', 'passage_ids': ['p']}]})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'a.zip').write_bytes(first)
            (root / 'b.zip').write_bytes(second)
            policy = {'schema': 'scriptura.local-trust-policy.v1', 'baseline_archive_sha256': first_hash,
                      'baseline_manifest_sha256': first_manifest, 'baseline_root_sha256': ROOT,
                      'increment_archive_sha256': second_hash, 'increment_manifest_sha256': second_manifest}
            (root / 'trust.json').write_text(json.dumps(policy), encoding='utf-8')
            script = Path(__file__).resolve().parents[1] / 'scripts' / 'validate_research_increment.py'
            proc = subprocess.run([sys.executable, str(script), '--baseline', str(root / 'a.zip'), '--increment', str(root / 'b.zip'), '--trust-policy', str(root / 'trust.json')], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0)
            self.assertNotIn('SYNTHETIC PRIVATE SENTINEL', proc.stdout + proc.stderr)
            self.assertNotIn(directory, proc.stdout + proc.stderr)
            self.assertNotIn(first_hash, proc.stdout + proc.stderr)
            self.assertEqual(json.loads(proc.stdout)['cumulative_claims'], 1)
            bad = subprocess.run([sys.executable, str(script), '--baseline', str(root / 'a.zip'),
                                  '--unexpected-private-argument', 'SYNTHETIC-PRIVATE-PATH'],
                                 capture_output=True, text=True)
            self.assertNotEqual(bad.returncode, 0)
            self.assertNotIn('SYNTHETIC-PRIVATE-PATH', bad.stdout + bad.stderr)
            self.assertNotIn(directory, bad.stdout + bad.stderr)


if __name__ == '__main__':
    unittest.main()
