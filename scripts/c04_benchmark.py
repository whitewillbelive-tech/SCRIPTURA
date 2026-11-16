"""Private local W-11 replay with no oracle access or automatic grading.

The W-11 member names follow the C-03 adapter; actual W-11 compatibility is
not established until that archive is available and independently checked.
Only the manifest and questions member are read. Never log question text,
identifiers, answers, source data, archive paths, or model output.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
from zipfile import BadZipFile, ZipFile

from c03_canonical_local import CanonicalError, CanonicalIndex, MODES, W10R_SHA256, analyze_local, safe
from c03_benchmark import search_from_question

W11_SHA256 = '99015866410558c963fefff6373c94aaab043b7a51bf639b28aa4733a6fabc4a'
_HASH = re.compile(r'[a-f0-9]{64}\Z')
_ID = re.compile(r'[A-Za-z0-9_-]{1,80}\Z')
_MAX_QA_BYTES = 32 * 1024 * 1024
_MAX_MEMBERS_BYTES = 128 * 1024 * 1024


def _windows_drive_allowed(anchor, get_drive_type):
    try:
        return bool(anchor) and get_drive_type(anchor) in (2, 3)
    except Exception:
        return False


def _local_file(path):
    try:
        value = os.fspath(path)
    except TypeError:
        raise CanonicalError('private_local_path_required') from None
    if not isinstance(value, str) or not value or value.startswith(('\\\\', '//')) or re.search(r'://', value):
        raise CanonicalError('private_local_path_required')
    p = Path(value)
    if os.name == 'nt':
        # A drive letter may be an SMB mapping. Resolve reparse points first,
        # then fail closed for remote, unknown and unavailable drive types.
        try:
            import ctypes
            anchor = p.resolve(strict=False).anchor
            if not _windows_drive_allowed(anchor, ctypes.windll.kernel32.GetDriveTypeW):
                raise CanonicalError('private_local_path_required')
        except (OSError, AttributeError, ValueError):
            raise CanonicalError('private_local_path_required') from None
    return p


def _read_questions(path, *, expected_sha256, canonical_sha256):
    """Read only trusted QA's manifest/questions, without opening the oracle."""
    if not isinstance(expected_sha256, str) or not _HASH.fullmatch(expected_sha256):
        raise CanonicalError('qa_anchor_invalid')
    if not isinstance(canonical_sha256, str) or not _HASH.fullmatch(canonical_sha256):
        raise CanonicalError('canonical_anchor_invalid')
    p = _local_file(path)
    try:
        if not p.is_file() or not 0 < p.stat().st_size <= _MAX_QA_BYTES:
            raise CanonicalError('qa_file_unavailable')
        with p.open('rb') as stream:
            blob = stream.read(_MAX_QA_BYTES + 1)
        if not blob or len(blob) > _MAX_QA_BYTES:
            raise CanonicalError('qa_file_unavailable')
        if hashlib.sha256(blob).hexdigest() != expected_sha256:
            raise CanonicalError('qa_digest_mismatch')
        # Keep validation and the data read on the exact same authenticated
        # bytes, avoiding a path replacement between hash and opening.
        from io import BytesIO
        with ZipFile(BytesIO(blob)) as z:
            infos = z.infolist()
            if (len(infos) > 512 or len({i.filename for i in infos}) != len(infos)
                    or sum(i.file_size for i in infos) > _MAX_MEMBERS_BYTES
                    or any(i.flag_bits & 1 or i.filename.startswith('/')
                           or '..' in i.filename.split('/') or '\\' in i.filename
                           or (i.external_attr >> 16) & 0o170000 == 0o120000 for i in infos)):
                raise CanonicalError('qa_archive_invalid')
            manifest_info = z.getinfo('MANIFEST.json')
            questions_info = z.getinfo('benchmark/questions.jsonl')
            if manifest_info.file_size > 65536 or questions_info.file_size > 2 * 1024 * 1024:
                raise CanonicalError('qa_archive_invalid')
            manifest = json.loads(z.read(manifest_info).decode('utf-8'))
            if not isinstance(manifest, dict) or manifest.get('gate') not in ('W11', 'W11R'):
                raise CanonicalError('qa_schema_unsupported')
            # The independent QA must explicitly name the canonical bytes it
            # evaluated. An archive's self-description is not its trust anchor.
            if manifest.get('canonical_sha256') != canonical_sha256:
                raise CanonicalError('qa_canonical_binding_unverified')
            questions_data = z.read(questions_info).decode('utf-8')
    except CanonicalError:
        raise
    except (OSError, BadZipFile, KeyError, UnicodeError, ValueError, RuntimeError):
        raise CanonicalError('qa_read_failed') from None
    try:
        parsed = [json.loads(line) for line in questions_data.splitlines() if line.strip()]
    except (ValueError, RecursionError):
        raise CanonicalError('questions_invalid') from None
    if len(parsed) != 50 or any(not isinstance(x, dict) for x in parsed):
        raise CanonicalError('questions_invalid')
    ids = [x.get('id') for x in parsed]
    if any(not isinstance(x, str) or not _ID.fullmatch(x) for x in ids) or len(set(ids)) != 50:
        raise CanonicalError('questions_invalid')
    # Project only the question and method. Any answer-key-like or other
    # fields in the archive are not forwarded to retrieval or the model.
    return [{'id': x['id'], 'question': x.get('question'),
             'method': x.get('method', 'comparison')} for x in parsed]


def _private_output_path(output):
    p = _local_file(output)
    # Refuse a result file within the source checkout so an accidental git add
    # cannot publish private questions, answers or model identifiers.
    checkout = Path(__file__).resolve().parent.parent
    try:
        resolved = p.resolve(strict=False)
        resolved.relative_to(checkout)
    except ValueError:
        pass
    except OSError:
        raise CanonicalError('output_unavailable') from None
    else:
        raise CanonicalError('output_inside_checkout')
    if p.exists() or p.is_symlink() or not p.parent.is_dir():
        raise CanonicalError('output_unavailable')
    return p


def _write_private(path, records):
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
        fd = os.open(os.fspath(path), flags, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            for item in records:
                stream.write(json.dumps(item, ensure_ascii=False, separators=(',', ':')) + '\n')
    except OSError:
        raise CanonicalError('private_output_failed') from None


def replay(canonical, audit, *, model=None, output=None, progress=None,
           qa_expected_sha256=W11_SHA256, canonical_expected_sha256=W10R_SHA256):
    """Run each question locally; a model response is never a correct answer."""
    if model is not None and (not isinstance(model, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,70}', model)):
        raise CanonicalError('invalid_model')
    target = _private_output_path(output) if output is not None else None
    if model is not None and target is None:
        # Per-question model outcomes must not silently disappear; no raw
        # question or model answer is ever sent to stdout or CI logs.
        raise CanonicalError('private_output_required')
    questions = _read_questions(audit, expected_sha256=qa_expected_sha256,
                                canonical_sha256=canonical_expected_sha256)
    index = CanonicalIndex(_local_file(canonical), expected_sha256=canonical_expected_sha256)
    records = []
    for item in questions:
        result = {'id': item['id'], 'method': item['method'], 'status': 'NOT_RUN',
                  'model_called': False, 'citation_integrity': 'NOT_CHECKED',
                  'independent_evaluation': 'NOT_REVIEWED', 'analyses': []}
        question, method = item['question'], item['method']
        if not isinstance(method, str) or method not in MODES:
            result['status'] = 'NOT_RUN_UNSUPPORTED_METHOD'
        elif not safe(question, 600):
            result['status'] = 'NOT_RUN_UNSAFE_QUESTION'
        elif model is None:
            result['status'] = 'NOT_RUN_NO_MODEL'
        else:
            matched, _ = search_from_question(question, index)
            if not matched:
                result['status'] = 'NOT_RUN_NO_LINKED_PASSAGE'
            elif len(matched) != 1:
                result['status'] = 'NOT_RUN_AMBIGUOUS_PASSAGE'
            elif (not isinstance(matched[0].get('corpus'), str) or not matched[0]['corpus'].strip()
                  or not isinstance(matched[0].get('scheme'), str) or not matched[0]['scheme'].strip()):
                # An exact-looking number is not enough to establish corpus
                # or versification. Do not send evidence when either is absent.
                result['status'] = 'NOT_RUN_ADDRESS_SYSTEM_UNCONFIRMED'
            else:
                try:
                    # This must be the index's sealed, policy-filtered model
                    # evidence, never ordinary viewer notes or the QA oracle.
                    evidence = index.model_notes(matched[0]['id'])
                    if len(evidence) == 0:
                        raise CanonicalError('model_input_not_permitted')
                    def on_model_call():
                        result['model_called'] = True
                    answer = analyze_local(question, method, evidence, model,
                                           on_model_call=on_model_call)
                    if answer.get('status') != 'analysis_unverified':
                        result.update(status='MODEL_ERROR', error_code='invalid_model_response')
                    else:
                        result.update(status='AWAITING_INDEPENDENT_REVIEW',
                                      citation_integrity='ID_CHECKED_NOT_ENTAILMENT',
                                      analyses=answer.get('analyses', []))
                except CanonicalError as exc:
                    code = str(exc)
                    if not result['model_called'] and code in ('model_input_not_permitted', 'insufficient_evidence', 'no_permitted_evidence'):
                        result.update(status='NOT_RUN_RIGHTS_OR_EVIDENCE', model_called=False)
                    else:
                        result.update(status='MODEL_ERROR', error_code='model_execution_failed')
                except (AttributeError, TypeError, ValueError):
                    # No sealed model-evidence interface means no call at all.
                    if result['model_called']:
                        result.update(status='MODEL_ERROR', error_code='model_execution_failed')
                    else:
                        result.update(status='NOT_RUN_POLICY_UNAVAILABLE', model_called=False)
        records.append(result)
        if progress is not None:
            progress({'completed': len(records), 'total': 50})
    attempted = sum(r['model_called'] for r in records)
    responded = sum(r['status'] == 'AWAITING_INDEPENDENT_REVIEW' for r in records)
    summary = {'questions': 50, 'model_called': attempted, 'model_attempted': attempted,
               'model_responded': responded, 'call_count_meaning': 'HTTP_ATTEMPT_NOT_EXECUTION_PROOF',
               'awaiting_review': responded,
               'model_errors': sum(r['status'] == 'MODEL_ERROR' for r in records),
               'not_run': sum(r['status'].startswith('NOT_RUN') for r in records),
               'independent_scores': 'NOT_SCORED', 'critical_errors': 'NOT_ASSESSED',
               'actual_archive_compatibility': 'UNVERIFIED_UNTIL_PRIVATE_ACCEPTANCE'}
    if target is not None:
        # This opt-in local file is sensitive and never belongs in git or CI.
        meta = {'record': 'run_metadata', 'model': model, 'model_version': None,
                'settings': {'temperature': 0}, 'score': 'NOT_SCORED',
                'note': 'model version requires separate local confirmation'}
        _write_private(target, [meta, *records])
    return summary


def summarize_independent_reviews(records, reviews):
    """Aggregate human-supplied scores only; never grade model output itself."""
    if not isinstance(records, list) or not isinstance(reviews, list):
        raise ValueError('invalid_review')
    by_id = {r.get('id'): r for r in records if isinstance(r, dict) and isinstance(r.get('id'), str)}
    if len(by_id) != len(records):
        raise ValueError('invalid_review')
    reviewed, total, critical, seen = 0, 0, 0, set()
    for review in reviews:
        if not isinstance(review, dict) or set(review) != {'id', 'source_accuracy', 'theological_fidelity', 'method_uncertainty', 'critical_error'}:
            raise ValueError('invalid_review')
        ref = review['id']
        if not isinstance(ref, str) or ref in seen or ref not in by_id or by_id[ref].get('status') != 'AWAITING_INDEPENDENT_REVIEW':
            raise ValueError('invalid_review')
        values = [review['source_accuracy'], review['theological_fidelity'], review['method_uncertainty']]
        if any(type(n) is not int or not 0 <= n <= cap for n, cap in zip(values, (4, 4, 2))) or type(review['critical_error']) is not bool:
            raise ValueError('invalid_review')
        seen.add(ref); reviewed += 1; total += sum(values); critical += int(review['critical_error'])
    return {'reviewed': reviewed, 'points': total, 'max_points': reviewed * 10,
            'critical_errors': critical, 'not_reviewed': len(records) - reviewed}


def score_private_files(results_path, reviews_path):
    """Read independent human grades without opening an oracle or model."""
    def read_bounded(path):
        try:
            with _local_file(path).open('rb') as stream:
                data = stream.read(8 * 1024 * 1024 + 1)
            if not data or len(data) > 8 * 1024 * 1024:
                raise ValueError('invalid_review')
            return data.decode('utf-8')
        except (OSError, UnicodeError):
            raise ValueError('invalid_review') from None
    try:
        lines = [json.loads(line) for line in read_bounded(results_path).splitlines() if line.strip()]
        reviews = json.loads(read_bounded(reviews_path))
        if len(lines) != 51 or not isinstance(lines[0], dict) or lines[0].get('record') != 'run_metadata':
            raise ValueError('invalid_review')
        return summarize_independent_reviews(lines[1:], reviews)
    except (ValueError, TypeError, RecursionError):
        raise ValueError('invalid_review') from None


def main(argv=None):
    parser = argparse.ArgumentParser(description='Private local benchmark; no automatic grading')
    parser.add_argument('--canonical')
    parser.add_argument('--audit')
    parser.add_argument('--model')
    parser.add_argument('--output')
    parser.add_argument('--score-results', help='Private local JSONL from a previous run')
    parser.add_argument('--score-reviews', help='Private local human-authored JSON scores')
    parser.add_argument('--qa-sha256', default=W11_SHA256,
                        help='Independently trusted QA archive SHA-256; default W-11')
    args = parser.parse_args(argv)
    try:
        if args.score_results or args.score_reviews:
            if not args.score_results or not args.score_reviews or any((args.canonical, args.audit, args.model, args.output)):
                raise CanonicalError('invalid_review')
            summary = score_private_files(args.score_results, args.score_reviews)
            print(json.dumps(summary, ensure_ascii=False))
            return 0
        if not args.canonical or not args.audit:
            raise CanonicalError('invalid_request')
        summary = replay(args.canonical, args.audit, model=args.model, output=args.output,
                         qa_expected_sha256=args.qa_sha256)
        print(json.dumps(summary, ensure_ascii=False))
        return 0
    except (CanonicalError, ValueError, OSError):
        print('C04_BENCHMARK_NOT_RUN: check local input integrity and compatibility')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
