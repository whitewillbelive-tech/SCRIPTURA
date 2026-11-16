"""Synthetic-only tests: real research and QA data never enter CI."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from c03_canonical_local import CanonicalError
import c04_benchmark as bench

ANCHOR = 'a' * 64


def make_qa(path, *, binding=ANCHOR, gate='W11', n=50, method='comparison'):
    rows = [{'id': f'SYN-{i}', 'question': '이사야 7:14 해석은?', 'method': method,
             'oracle': 'DO_NOT_FORWARD_ORACLE'} for i in range(n)]
    with ZipFile(path, 'w') as archive:
        archive.writestr('MANIFEST.json', json.dumps({'gate': gate, 'canonical_sha256': binding}))
        archive.writestr('benchmark/questions.jsonl', ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows))
        archive.writestr('benchmark/answer_key.json', 'DO_NOT_READ_ORACLE')
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FakeIndex:
    def __init__(self, path, *, expected_sha256):
        self.mode = 'none'
    def find(self, ref, limit=30):
        return [{'id': 'SYN-PASSAGE', 'reference': ref, 'corpus':'SYNTH', 'scheme':'SYNTH'}]
    def model_notes(self, passage_id):
        return []


class C04BenchmarkTests(unittest.TestCase):
    def test_only_manifest_and_questions_are_read(self):
        with tempfile.TemporaryDirectory() as folder:
            qa = Path(folder) / 'qa.zip'; digest = make_qa(qa)
            original = ZipFile.read
            reads = []
            def track(z, name, *args, **kwargs):
                reads.append(getattr(name, 'filename', name))
                return original(z, name, *args, **kwargs)
            with patch.object(ZipFile, 'read', track):
                rows = bench._read_questions(qa, expected_sha256=digest, canonical_sha256=ANCHOR)
            self.assertEqual(len(rows), 50)
            self.assertEqual(set(reads), {'MANIFEST.json', 'benchmark/questions.jsonl'})
            self.assertNotIn('oracle', rows[0])

    def test_reject_hash_mismatch_binding_mismatch_and_duplicate_ids(self):
        with tempfile.TemporaryDirectory() as folder:
            qa = Path(folder) / 'qa.zip'; digest = make_qa(qa, binding='b' * 64)
            with self.assertRaisesRegex(CanonicalError, 'qa_canonical_binding_unverified'):
                bench._read_questions(qa, expected_sha256=digest, canonical_sha256=ANCHOR)
            with self.assertRaisesRegex(CanonicalError, 'qa_digest_mismatch'):
                bench._read_questions(qa, expected_sha256='0' * 64, canonical_sha256=ANCHOR)
            digest = make_qa(qa, n=49)
            with self.assertRaisesRegex(CanonicalError, 'questions_invalid'):
                bench._read_questions(qa, expected_sha256=digest, canonical_sha256=ANCHOR)

    def test_no_model_is_fifty_not_run_and_never_reads_oracle(self):
        with tempfile.TemporaryDirectory() as folder:
            qa = Path(folder) / 'qa.zip'; digest = make_qa(qa)
            progress = []
            with patch.object(bench, 'CanonicalIndex', FakeIndex), patch.object(bench, 'analyze_local') as call:
                summary = bench.replay('synthetic.zip', qa, qa_expected_sha256=digest,
                                       canonical_expected_sha256=ANCHOR, progress=progress.append)
            self.assertEqual((summary['questions'], summary['not_run'], summary['model_attempted'], summary['model_responded']), (50, 50, 0, 0))
            self.assertEqual(summary['independent_scores'], 'NOT_SCORED')
            self.assertEqual(progress[-1], {'completed': 50, 'total': 50})
            call.assert_not_called()

    def test_no_permitted_evidence_is_not_a_model_call(self):
        with tempfile.TemporaryDirectory() as folder:
            qa = Path(folder) / 'qa.zip'; digest = make_qa(qa); output = Path(folder) / 'result.jsonl'
            with patch.object(bench, 'CanonicalIndex', FakeIndex), patch.object(bench, 'analyze_local') as call:
                summary = bench.replay('synthetic.zip', qa, model='local-model', output=output,
                                       qa_expected_sha256=digest, canonical_expected_sha256=ANCHOR)
            self.assertEqual((summary['not_run'], summary['model_called']), (50, 0))
            self.assertFalse(any('DO_NOT_FORWARD_ORACLE' in line for line in output.read_text(encoding='utf8').splitlines()))
            # Python's Windows st_mode does not represent NTFS ACLs. Only
            # assert POSIX file permissions on platforms that implement them;
            # the Windows acceptance guide separately requires a private
            # user-controlled directory and does not claim ACL verification.
            if os.name == 'posix':
                self.assertEqual(os.stat(output).st_mode & 0o077, 0)
            call.assert_not_called()

    def test_actual_callback_counts_attempts_not_automatic_grades(self):
        class Allowed(FakeIndex):
            def model_notes(self, passage_id): return ['SYNTHETIC-SEALED']
        def synthetic_answer(question, mode, notes, model, *, on_model_call):
            self.assertNotIn('DO_NOT_FORWARD_ORACLE', question)
            on_model_call()
            return {'status': 'analysis_unverified', 'analyses': [{'text': 'SYNTHETIC', 'citations': ['SYN-C1']}]}
        with tempfile.TemporaryDirectory() as folder:
            qa = Path(folder) / 'qa.zip'; digest = make_qa(qa); output = Path(folder) / 'result.jsonl'
            with patch.object(bench, 'CanonicalIndex', Allowed), patch.object(bench, 'analyze_local', synthetic_answer):
                summary = bench.replay('synthetic.zip', qa, model='local-model', output=output,
                                       qa_expected_sha256=digest, canonical_expected_sha256=ANCHOR)
            self.assertEqual((summary['model_attempted'], summary['model_responded'], summary['not_run']), (50, 50, 0))
            self.assertEqual(summary['independent_scores'], 'NOT_SCORED')
            self.assertEqual(summary['call_count_meaning'], 'HTTP_ATTEMPT_NOT_EXECUTION_PROOF')

    def test_network_attempt_failure_and_preflight_rejection_are_distinct(self):
        class Allowed(FakeIndex):
            def model_notes(self, passage_id): return ['SYNTHETIC-SEALED']
        def rejected(question, mode, notes, model, *, on_model_call):
            raise CanonicalError('model_input_not_permitted')
        def failed(question, mode, notes, model, *, on_model_call):
            on_model_call()
            raise CanonicalError('local_model_unavailable_or_invalid')
        with tempfile.TemporaryDirectory() as folder:
            qa = Path(folder) / 'qa.zip'; digest = make_qa(qa)
            with patch.object(bench, 'CanonicalIndex', Allowed), patch.object(bench, 'analyze_local', rejected):
                blocked = bench.replay('synthetic.zip', qa, model='local', output=Path(folder) / 'blocked',
                                       qa_expected_sha256=digest, canonical_expected_sha256=ANCHOR)
            with patch.object(bench, 'CanonicalIndex', Allowed), patch.object(bench, 'analyze_local', failed):
                attempted = bench.replay('synthetic.zip', qa, model='local', output=Path(folder) / 'attempted',
                                         qa_expected_sha256=digest, canonical_expected_sha256=ANCHOR)
            self.assertEqual((blocked['not_run'], blocked['model_attempted']), (50, 0))
            self.assertEqual((attempted['model_errors'], attempted['model_attempted'], attempted['model_responded']), (50, 50, 0))

    def test_ambiguous_address_never_calls_model(self):
        class Ambiguous(FakeIndex):
            def find(self, ref, limit=30): return [{'id': 'S1', 'reference': ref}, {'id': 'S2', 'reference': ref}]
        with tempfile.TemporaryDirectory() as folder:
            qa = Path(folder) / 'qa.zip'; digest = make_qa(qa)
            with patch.object(bench, 'CanonicalIndex', Ambiguous), patch.object(bench, 'analyze_local') as call:
                summary = bench.replay('synthetic.zip', qa, model='local', output=Path(folder) / 'result',
                                       qa_expected_sha256=digest, canonical_expected_sha256=ANCHOR)
            self.assertEqual(summary['not_run'], 50)
            self.assertEqual(summary['model_attempted'], 0)
            call.assert_not_called()

    def test_missing_address_system_never_calls_model(self):
        class MissingScheme(FakeIndex):
            def find(self, ref, limit=30): return [{'id': 'S1', 'reference': ref, 'corpus': 'SYNTH'}]
        with tempfile.TemporaryDirectory() as folder:
            qa = Path(folder) / 'qa.zip'; digest = make_qa(qa); output = Path(folder) / 'results.jsonl'
            with patch.object(bench, 'CanonicalIndex', MissingScheme), patch.object(bench, 'analyze_local') as call:
                summary = bench.replay('synthetic.zip', qa, model='local', output=output,
                                       qa_expected_sha256=digest, canonical_expected_sha256=ANCHOR)
            self.assertEqual((summary['not_run'], summary['model_attempted']), (50, 0))
            self.assertEqual(json.loads(output.read_text(encoding='utf8').splitlines()[1])['status'], 'NOT_RUN_ADDRESS_SYSTEM_UNCONFIRMED')
            call.assert_not_called()

    def test_local_only_output_no_overwrite(self):
        self.assertFalse(bench._windows_drive_allowed('Z:\\', lambda _: 4))
        self.assertFalse(bench._windows_drive_allowed('Z:\\', lambda _: 0))
        self.assertTrue(bench._windows_drive_allowed('C:\\', lambda _: 3))
        with self.assertRaises(CanonicalError): bench._local_file('\\\\server\\shared\\out')
        with self.assertRaises(CanonicalError): bench._local_file('https://example.invalid/out')
        with self.assertRaisesRegex(CanonicalError, 'output_inside_checkout'):
            bench._private_output_path(Path(__file__).resolve().parents[1] / 'results.jsonl')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'present'; path.write_text('UNCHANGED', encoding='utf8')
            with self.assertRaises(CanonicalError): bench._private_output_path(path)
            self.assertEqual(path.read_text(encoding='utf8'), 'UNCHANGED')

    def test_human_scores_only_and_no_unrun_credit(self):
        rows = [{'id': 'S1', 'status': 'AWAITING_INDEPENDENT_REVIEW'}, {'id': 'S2', 'status': 'NOT_RUN_NO_MODEL'}]
        score = {'id': 'S1', 'source_accuracy': 3, 'theological_fidelity': 4, 'method_uncertainty': 2, 'critical_error': False}
        self.assertEqual(bench.summarize_independent_reviews(rows, [score]),
                         {'reviewed': 1, 'points': 9, 'max_points': 10, 'critical_errors': 0, 'not_reviewed': 1})
        with self.assertRaises(ValueError): bench.summarize_independent_reviews(rows, [dict(score, id='S2')])
        with self.assertRaises(ValueError): bench.summarize_independent_reviews(rows, [dict(score, source_accuracy=5)])

    def test_separate_review_files_never_execute_model(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); result = root / 'results.jsonl'; review = root / 'review.json'
            data = [{'record': 'run_metadata'}] + [{'id': f'S{i}', 'status': 'AWAITING_INDEPENDENT_REVIEW' if i == 0 else 'NOT_RUN_NO_MODEL'} for i in range(50)]
            result.write_text(''.join(json.dumps(row) + '\n' for row in data), encoding='utf8')
            review.write_text(json.dumps([{'id': 'S0', 'source_accuracy': 4, 'theological_fidelity': 3,
                                           'method_uncertainty': 2, 'critical_error': True}]), encoding='utf8')
            with patch.object(bench, 'analyze_local') as model:
                summary = bench.score_private_files(result, review)
            self.assertEqual((summary['reviewed'], summary['points'], summary['critical_errors'], summary['not_reviewed']), (1, 9, 1, 49))
            model.assert_not_called()


if __name__ == '__main__':
    unittest.main()
