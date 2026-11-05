"""Contract and adversarial checks using generated synthetic data only."""
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))
from s1b2_synthetic_factory import ACTIONS, SNAPSHOT, synthetic_rows, write_archive
from d2_bridge.validator import validate_archive


class SyntheticValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='scriptura-s1b2-tests-')
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'synthetic.zip'
        self.rows = synthetic_rows()

    def validate(self, *, rows=None, alter_files=None, alter_manifest=None, extra_entries=None, expected_sha=None, expected_counts=None, expected_snapshot=SNAPSHOT, expected_manifest_count=65):
        actual, counts = write_archive(self.path, rows if rows is not None else self.rows, alter_files=alter_files, alter_manifest=alter_manifest, extra_entries=extra_entries)
        return validate_archive(self.path, expected_sha256=expected_sha or actual, expected_snapshot=expected_snapshot, expected_counts=expected_counts or counts, expected_manifest_count=expected_manifest_count)

    def assert_fail_or_held(self, report, records, table, record_id):
        if report.get('status') != 'pass':
            return
        matches = [r for r in records.get(table, []) if r.get('data', {}).get('id') == record_id]
        self.assertEqual(len(matches), 1)
        self.assertTrue(matches[0].get('reasons'), 'unsafe record must carry a reason')
        self.assertNotIn(matches[0].get('disposition'), ('applicable', 'apply', 'accepted', 'ready', 'valid'))

    def test_valid_synthetic_archive_is_read_only_and_has_all_twelve_tables(self):
        report, records = self.validate()
        self.assertEqual(report.get('status'), 'pass', report)
        self.assertEqual(len(records), 12)
        self.assertEqual(len(records['rights']), 9)
        self.assertEqual(records['claims'][0]['data']['review_status'], 'candidate')
        self.assertEqual(report.get('snapshot'), SNAPSHOT)
        self.assertEqual(report.get('archive_sha256'), hashlib.sha256(self.path.read_bytes()).hexdigest())
        source = records['sources'][0]
        original_line = (json.dumps(self.rows['sources'][0], ensure_ascii=False, sort_keys=True) + '\n').encode('utf-8')
        self.assertEqual(source['sha256'], hashlib.sha256(original_line).hexdigest())
        self.assertEqual(source['file'], 'd2/records_merged/sources.jsonl')
        self.assertEqual(source['row_number'], 1)
        self.assertNotIn('Fictional source', json.dumps(report, ensure_ascii=False))
        self.assertNotIn('example.invalid', json.dumps(report, ensure_ascii=False))

    def test_synthetic_snapshot_recreation_is_byte_identical(self):
        first_sha, first_counts = write_archive(self.path, self.rows)
        second = self.path.parent / 'synthetic-repeat.zip'
        second_sha, second_counts = write_archive(second, self.rows)
        self.assertEqual(first_counts, second_counts)
        self.assertEqual(first_sha, second_sha)
        self.assertEqual(self.path.read_bytes(), second.read_bytes())
        with ZipFile(second) as archive:
            self.assertTrue(all(info.date_time == (2020, 1, 1, 0, 0, 0) for info in archive.infolist()))

    def test_outer_zip_sha_mismatch_is_rejected(self):
        report, _ = self.validate(expected_sha='0'*64)
        self.assertNotEqual(report.get('status'), 'pass')

    def test_internal_manifest_hash_tamper_is_rejected_even_with_matching_zip_hash(self):
        def tamper(m): m['file_hashes'][0]['sha256'] = '0'*64
        report, _ = self.validate(alter_manifest=tamper)
        self.assertNotEqual(report.get('status'), 'pass')

    def test_manifest_entry_count_and_row_count_are_enforced(self):
        def drop(m): m['file_hashes'].pop()
        report, _ = self.validate(alter_manifest=drop)
        self.assertNotEqual(report.get('status'), 'pass')
        counts = {k:len(v) for k,v in self.rows.items()}; counts['claims'] += 1
        report, _ = self.validate(expected_counts=counts)
        self.assertNotEqual(report.get('status'), 'pass')

    def test_delta_merged_disagreement_is_rejected(self):
        def alter(files): files['d2/records_delta/claims.jsonl'] = b''
        report, _ = self.validate(alter_files=alter)
        self.assertNotEqual(report.get('status'), 'pass')

    def test_zip_slip_entry_is_rejected(self):
        outside = self.path.parent.parent / (self.path.parent.name + '-escape.txt')
        self.assertFalse(outside.exists())
        report, _ = self.validate(extra_entries=[('../' + outside.name, b'test')])
        self.assertNotEqual(report.get('status'), 'pass')
        self.assertIn('unsafe_archive_path', report.get('errors', {}))
        self.assertFalse(outside.exists())

    def test_duplicate_archive_path_is_rejected(self):
        report, _ = self.validate(extra_entries=[('RUN_MANIFEST.json', b'{}')])
        self.assertNotEqual(report.get('status'), 'pass')

    def test_compression_bomb_is_rejected_before_processing(self):
        def enlarge(files): files['synthetic/support-00.txt'] = b'X' * (40 * 1024 * 1024)
        report, _ = self.validate(alter_files=enlarge)
        self.assertNotEqual(report.get('status'), 'pass')

    def test_zip_excessive_compression_ratio_is_rejected(self):
        def enlarge(files): files['synthetic/support-00.txt'] = b'X' * (2 * 1024 * 1024)
        report, _ = self.validate(alter_files=enlarge)
        self.assertNotEqual(report.get('status'), 'pass')

    def test_duplicate_json_keys_are_rejected(self):
        def duplicate_keys(files):
            raw = b'{"id":"source-a","id":"source-b"}\n'
            files['d2/records_delta/sources.jsonl'] = raw
            files['d2/records_merged/sources.jsonl'] = raw
        report, _ = self.validate(alter_files=duplicate_keys)
        self.assertNotEqual(report.get('status'), 'pass')
        self.assertIn('record_json_invalid', report.get('errors', {}))

    def test_json_nonfinite_constants_are_rejected(self):
        def nonfinite(files):
            raw = b'{"id":"source-a","year":NaN}\n'
            files['d2/records_delta/sources.jsonl'] = raw
            files['d2/records_merged/sources.jsonl'] = raw
        report, _ = self.validate(alter_files=nonfinite)
        self.assertNotEqual(report.get('status'), 'pass')
        self.assertIn('record_json_invalid', report.get('errors', {}))

    def test_snapshot_identity_mismatch_is_rejected(self):
        report, _ = self.validate(expected_snapshot='other-snapshot')
        self.assertNotEqual(report.get('status'), 'pass')

    def test_duplicate_edition_action_not_granted(self):
        right = copy.deepcopy(next(r for r in self.rows['rights'] if r['action'] == 'embed'))
        right['id'] = 'right:duplicate-embed'
        right['decision'] = 'allowed'
        self.rows['rights'].append(right)
        report, records = self.validate()
        self.assertIn('rights_action_duplicate', report.get('errors', {}))

    def test_mixed_synthetic_and_real_records_are_not_accepted_as_real(self):
        source = self.rows['sources'][0]
        source['is_synthetic'] = True
        report, records = self.validate()
        self.assertIn('synthetic_research_mixture', report.get('errors', {}))

    def test_checked_empty_locator_is_not_confirmed(self):
        locator = self.rows['locators'][0]
        locator.update(verification_status='source_checked', checked_at='2026-01-01T00:00:00Z', location='')
        report, records = self.validate()
        self.assertIn('record_required_field_empty', report.get('errors', {}))

    def test_whitespace_locator_cannot_support_source_verified_claim(self):
        self.rows['locators'][0].update(verification_status='source_checked', checked_at='2026-01-01T00:00:00Z', location='   ')
        self.rows['claims'][0]['review_status'] = 'source_verified'
        self.rows['evidence'][0]['review_status'] = 'verified'
        self.rows['reviews'][0]['decision'] = 'source_verified'
        report, _ = self.validate()
        self.assertTrue({'verified_claim_locator_missing', 'record_required_field_empty'} & set(report.get('errors', {})))
        self.assertNotEqual(report.get('status'), 'pass')

    def test_invalid_nonempty_review_dates_are_rejected(self):
        for table, field, expected in (
            ('locators', 'checked_at', 'locator_date_invalid'),
            ('rights', 'checked_at', 'rights_date_invalid'),
            ('reviews', 'reviewed_at', 'review_identity_or_time_missing'),
        ):
            with self.subTest(table=table):
                rows = copy.deepcopy(self.rows)
                rows[table][0][field] = 'not-a-date'
                report, _ = self.validate(rows=rows)
                self.assertIn(expected, report.get('errors', {}))
                self.assertNotEqual(report.get('status'), 'pass')

    def test_missing_source_fk_does_not_become_applicable(self):
        self.rows['editions'][0]['source_id'] = 'src:missing'
        report, records = self.validate()
        self.assertIn('reference_missing', report.get('errors', {}))

    def test_duplicate_global_id_is_rejected(self):
        self.rows['agents'][0]['id'] = self.rows['sources'][0]['id']
        report, _ = self.validate()
        self.assertNotEqual(report.get('status'), 'pass')

    def test_duplicate_normalized_doi_does_not_become_applicable(self):
        dupe = copy.deepcopy(self.rows['sources'][0])
        dupe['id'] = 'src:synthetic-duplicate'
        dupe['doi'] = 'https://doi.org/10.99999/FICTION-0'
        self.rows['sources'].append(dupe)
        report, records = self.validate()
        self.assertIn('duplicate_doi', report.get('errors', {}))

    def test_raw_original_text_field_is_not_accepted(self):
        self.rows['sources'][0]['raw_text'] = 'SYNTHETIC FORBIDDEN CONTENT'
        report, records = self.validate()
        self.assertIn('forbidden_content_field', report.get('errors', {}))
        self.assertNotIn('SYNTHETIC FORBIDDEN CONTENT', json.dumps(report, ensure_ascii=False))

    def test_claim_source_verified_without_valid_history_is_not_accepted(self):
        self.rows['claims'][0]['review_status'] = 'source_verified'
        report, records = self.validate()
        self.assertIn('verified_claim_locator_missing', report.get('errors', {}))

    def test_scholarly_review_not_forged_from_source_verification(self):
        claim = self.rows['claims'][0]
        claim['review_status'] = 'source_verified'
        self.rows['locators'][0].update(verification_status='source_checked', checked_at='2026-01-01T00:00:00Z')
        self.rows['evidence'][0]['review_status'] = 'verified'
        self.rows['reviews'][0]['decision'] = 'source_verified'
        report, records = self.validate()
        self.assertEqual(report.get('status'), 'pass', report)
        result = records['claims'][0]['data']
        self.assertEqual(result['review_status'], 'source_verified')
        self.assertNotEqual(result['review_status'], 'scholarly_reviewed')
        self.assertNotIn(records['claims'][0]['disposition'], ('ready', 'accepted', 'applicable'))

    def test_textual_narrative_requires_literary_voice_and_is_not_retyped(self):
        self.rows['claims'][0]['attribution_kind'] = 'textual_narrative'
        report, _ = self.validate()
        self.assertIn('narrative_voice_mismatch', report.get('errors', {}))
        self.rows['agents'][0]['kind'] = 'literary_voice'
        report, records = self.validate()
        self.assertEqual(report.get('status'), 'pass', report)
        self.assertEqual(records['claims'][0]['data']['attribution_kind'], 'textual_narrative')
        self.assertEqual(records['agents'][0]['data']['kind'], 'literary_voice')

    def test_official_doctrine_cannot_be_attributed_to_individual(self):
        claim = self.rows['claims'][0]
        claim.update(attribution_kind='official_doctrine', official_basis_locator_id='loc:synthetic-1')
        self.rows['locators'][0].update(verification_status='source_checked', checked_at='2026-01-01T00:00:00Z')
        report, _ = self.validate()
        self.assertIn('official_doctrine_not_institutional', report.get('errors', {}))

    def test_partial_alignment_is_not_coerced_to_verified(self):
        report, records = self.validate()
        self.assertEqual(report.get('status'), 'pass', report)
        alignment = records['alignments'][0]
        self.assertEqual(alignment['data']['alignment_type'], 'equivalent_segment')
        self.assertEqual(alignment['data']['review_status'], 'partial_pending')
        self.assertNotIn(alignment['disposition'], ('ready', 'accepted', 'applicable'))

    def test_unknown_and_conditional_rights_never_allow_sensitive_actions(self):
        for record in self.rows['rights']:
            if record['action'] in ('store_raw','store_excerpt','index_fulltext','embed','send_to_model','redistribute','public_link'):
                record['decision'] = 'conditional' if record['action'] == 'embed' else 'unknown'
        report, records = self.validate()
        self.assertEqual(report.get('status'), 'pass', report)
        for record in records['rights']:
            if record['data']['action'] in ('store_raw','store_excerpt','index_fulltext','embed','send_to_model','redistribute','public_link'):
                self.assertIs(record.get('rights', {}).get('effective_allowed'), False)
                self.assertEqual(report['rights'][record['data']['action']]['effective_allowed'], 0)

    def test_missing_action_is_rejected_not_default_allowed(self):
        self.rows['rights'] = [right for right in self.rows['rights'] if right['action'] != 'embed']
        report, _ = self.validate()
        self.assertNotEqual(report.get('status'), 'pass')
        self.assertIn('rights_action_missing', report.get('errors', {}))

    def test_allowed_with_evidence_still_requires_independent_review(self):
        right = next(r for r in self.rows['rights'] if r['action'] == 'embed')
        right.update(decision='allowed', evidence_url='https://example.invalid/terms', checked_at='2026-01-01T00:00:00Z')
        report, records = self.validate()
        self.assertEqual(report.get('status'), 'pass', report)
        result = next(r for r in records['rights'] if r['data']['id'] == right['id'])
        self.assertIs(result['rights']['effective_allowed'], False)
        self.assertEqual(report['rights']['embed']['effective_allowed'], 0)

    def test_research_scholarly_review_requires_separate_human_review_event(self):
        claim = self.rows['claims'][0]
        claim['review_status'] = 'scholarly_reviewed'
        report, records = self.validate()
        self.assert_fail_or_held(report, records, 'claims', claim['id'])
        self.assertIn('independent_review_missing', report.get('errors', {}))

    def test_manifest_declared_counts_match_merged_jsonl(self):
        def alter(m): m['d2_merged_counts']['sources'] += 1
        report, _ = self.validate(alter_manifest=alter)
        self.assertNotEqual(report.get('status'), 'pass')

    def test_unjustified_allowed_rights_not_promoted(self):
        right = next(r for r in self.rows['rights'] if r['action'] == 'store_raw')
        right['decision'] = 'allowed'
        report, records = self.validate()
        self.assertIn('rights_allowed_without_evidence', report.get('errors', {}))


if __name__ == '__main__':
    unittest.main()
