"""Synthetic K-1.1 metadata projection and evidence separation tests."""
import copy
import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from j2_private_preview import filter_records
from k11_bridge.metadata import VerifiedMetadataIndex, prepare_private_candidates, synthetic_index_for_tests

KEY = 'd8:sources:1'
OTHER = 'd8:sources:2'
DATA = {KEY: {'source_title': 'SYNTHETIC-TITLE', 'source_creator': 'SYNTHETIC-AUTHOR',
              'source_publisher': 'SYNTHETIC-PUBLISHER', 'source_year': '2099',
              'community_name': 'SYNTHETIC-COMMUNITY'}}
RECORDS = {KEY: {'source_id': 'synthetic:source', 'edition_id': 'synthetic:edition', 'fields': DATA[KEY]}}


def evidence(field='source_title'):
    return {'key': KEY, 'field': field, 'source_id': 'synthetic:source',
            'edition_id': 'synthetic:edition', 'reviewer': 'synthetic:reviewer',
            'value': DATA[KEY][field], 'source_confirmation': 'independently_confirmed',
            'rights_review': 'independently_confirmed', 'privacy_review': 'cleared',
            'scope': 'private_local_display_and_search', 'jurisdiction': 'synthetic:test',
            'basis': 'applicable_law_private_factual_metadata', 'conflict': False,
            'source_evidence': 'https://example.invalid/source',
            'rights_evidence': 'https://example.invalid/rights',
            'reviewed_at': '2026-01-01', 'valid_from': '2025-01-01', 'valid_until': '2027-01-01'}


def dataset(index=None):
    row = {'key': KEY, 'stage': 'd8', 'record_kind': 'source',
           'source_title': 'SYNTHETIC-RAW-SECRET', 'source_creator': 'SYNTHETIC-RAW-AUTHOR',
           'verification_status': 'source_checked', 'authority_status': 'pending_authority',
           'independent_review_status': 'pending', 'verified_metadata': DATA[KEY],
           'field_policy': {'source_metadata': 'candidate_visible_local'}}
    other = dict(row, key=OTHER)
    return {'dataset': 'D10', 'records': [row, other], 'counts': {}, 'warnings': [],
            '_verified_metadata_index': index}


def index(reviews):
    return synthetic_index_for_tests('D10', RECORDS, reviews, today='2026-06-01')


class MetadataProjectionTests(unittest.TestCase):
    def test_confirmed_fields_do_not_depend_on_theological_or_authority_status(self):
        source = dataset(index([evidence(x) for x in DATA[KEY]]))
        result = filter_records(source, {})
        self.assertEqual(result['metadata_projection'], 'k1.1-verified')
        self.assertEqual(result['records'][0]['verified_metadata'], DATA[KEY])
        self.assertEqual(result['records'][0]['authority_status'], 'pending_authority')
        self.assertEqual(result['records'][0]['independent_review_status'], 'pending')
        self.assertEqual(result['records'][0]['source_verification_status'], 'verified_fields_only')
        self.assertEqual(result['records'][1]['verified_metadata'], {})
        self.assertEqual(result['records'][1]['source_verification_status'], 'unconfirmed')
        self.assertTrue(all(count == 1 for count in result['metadata_coverage'].values()))

    def test_untrusted_input_objects_and_raw_fields_do_not_authorize(self):
        source = dataset({KEY: DATA[KEY]})
        result = filter_records(source, {})
        self.assertTrue(all(not row['verified_metadata'] for row in result['records']))
        self.assertNotIn('SYNTHETIC-RAW-SECRET', json.dumps(result))
        self.assertEqual(filter_records(source, {'q': ['SYNTHETIC-RAW-SECRET']})['total'], 0)
        with self.assertRaises(ValueError):
            VerifiedMetadataIndex(None, 'D10', {KEY: DATA[KEY]})

    def test_only_reviewed_projection_is_searchable(self):
        source = dataset(index([evidence('source_title'), evidence('source_creator'), evidence('community_name')]))
        for query in ({'q': ['synthetic-title']}, {'researcher': ['synthetic-author']},
                      {'community': ['synthetic-community']}):
            result = filter_records(source, query)
            self.assertEqual(result['total'], 1)
            self.assertEqual(result['records'][0]['key'], KEY)
        self.assertEqual(filter_records(source, {'q': ['synthetic-publisher']})['total'], 0)
        self.assertEqual(filter_records(source, {'q': ['2099']})['total'], 0)

    def test_invalid_scope_source_license_and_privacy_review_deny_independently(self):
        mutations = {'source_confirmation': 'pending', 'rights_review': 'pending',
                     'privacy_review': 'pending', 'scope': 'public', 'jurisdiction': 'unknown',
                     'basis': 'public_web', 'source_evidence': 'https://example.com/x',
                     'rights_evidence': None, 'reviewer': 'not-synthetic', 'conflict': True,
                     'valid_until': '2025-01-01', 'value': 'SYNTHETIC-OTHER'}
        for key, value in mutations.items():
            with self.subTest(condition=key):
                item = evidence()
                item[key] = value
                self.assertEqual(filter_records(dataset(index([item])), {})['records'][0]['verified_metadata'], {})

    def test_missing_and_conflicting_or_duplicate_reviews_fail_closed(self):
        good = evidence()
        for case in ([good, copy.deepcopy(good)], [dict(good, rights_review='pending'), good],
                     [dict(good, source_evidence=None)]):
            self.assertEqual(filter_records(dataset(index(case)), {})['records'][0]['verified_metadata'], {})

    def test_three_usage_basis_types_are_independent_of_research_truth(self):
        for basis in ('licensed_permission', 'public_domain', 'applicable_law_private_factual_metadata'):
            item = evidence()
            item['basis'] = basis
            with self.subTest(basis=basis):
                self.assertIn('source_title', filter_records(dataset(index([item])), {})['records'][0]['verified_metadata'])

    def test_non_synthetic_records_and_evidence_never_enter_test_index(self):
        value = 'UNAPPROVED-PRIVATE-VALUE'
        for field in ('source_title', 'source_creator', 'source_publisher', 'community_name'):
            fake = copy.deepcopy(DATA)
            fake[KEY][field] = value
            item = evidence(field)
            item['value'] = value
            records = {KEY: {'source_id': 'synthetic:source', 'edition_id': 'synthetic:edition', 'fields': fake[KEY]}}
            projection = synthetic_index_for_tests('D10', records, [item], today='2026-06-01')
            result = filter_records(dataset(projection), {})
            self.assertEqual(result['records'][0]['verified_metadata'], {})
            self.assertNotIn(value, repr(projection))

    def test_index_is_bound_to_dataset_and_does_not_repr_values(self):
        projection = index([evidence()])
        source = dataset(projection)
        source['dataset'] = 'D9'
        self.assertEqual(filter_records(source, {})['records'][0]['verified_metadata'], {})
        self.assertNotIn(DATA[KEY]['source_title'], repr(projection))

    def test_source_and_edition_mismatch_never_grant_same_value(self):
        for field in ('source_id', 'edition_id'):
            item = evidence()
            item[field] = 'synthetic:other'
            result = filter_records(dataset(index([item])), {})
            self.assertEqual(result['records'][0]['verified_metadata'], {})

    def test_community_verification_does_not_claim_source_confirmation(self):
        result = filter_records(dataset(index([evidence('community_name')])), {})
        self.assertEqual(result['records'][0]['source_verification_status'], 'unconfirmed')
        self.assertIn('community_name', result['records'][0]['verified_metadata'])

    def test_raw_sources_are_bound_in_memory_and_require_independent_verifier(self):
        layers = {'d8': {'sources': [{'line': 1, 'value': {'id': 'synthetic:source',
                   'title': DATA[KEY]['source_title'], 'creator': DATA[KEY]['source_creator'],
                   'publisher': DATA[KEY]['source_publisher'], 'publication_year': 2099}}],
                   'editions': [{'line': 1, 'value': {'id': 'synthetic:edition', 'source_id': 'synthetic:source'}}]}}
        original = dataset()
        candidates = prepare_private_candidates(original, layers)
        self.assertNotIn('SYNTHETIC-TITLE', repr(candidates))
        rejected = candidates.attach_reviewed(original, [evidence()], today='2026-06-01', independent_verifier=lambda row, review: False)
        self.assertEqual(filter_records(rejected, {})['records'][0]['verified_metadata'], {})
        approved = candidates.attach_reviewed(original, [evidence()], today='2026-06-01', independent_verifier=lambda row, review: True)
        self.assertEqual(filter_records(approved, {})['records'][0]['verified_metadata'], {'source_title': 'SYNTHETIC-TITLE'})
        with self.assertRaises(ValueError):
            candidates.attach_reviewed(dict(original, dataset='D9'), [evidence()], today='2026-06-01', independent_verifier=lambda row, review: True)

    def test_missing_or_multiple_editions_do_not_infer_a_source(self):
        source = {'line': 1, 'value': {'id': 'synthetic:source', 'title': 'SYNTHETIC-TITLE'}}
        edition = {'line': 1, 'value': {'id': 'synthetic:edition', 'source_id': 'synthetic:source'}}
        for editions in ([], [edition, dict(edition, line=2)]):
            candidates = prepare_private_candidates(dataset(), {'d8': {'sources': [source], 'editions': editions}})
            approved = candidates.attach_reviewed(dataset(), [evidence()], today='2026-06-01', independent_verifier=lambda row, review: True)
            self.assertEqual(filter_records(approved, {})['records'][0]['verified_metadata'], {})

    def test_private_verifier_stdout_stderr_are_discarded(self):
        layers = {'d8': {'sources': [{'line': 1, 'value': {'id': 'synthetic:source', 'title': DATA[KEY]['source_title']}}],
                         'editions': [{'line': 1, 'value': {'id': 'synthetic:edition', 'source_id': 'synthetic:source'}}]}}
        candidates = prepare_private_candidates(dataset(), layers)
        sentinel = 'SYNTHETIC-CALLBACK-PRIVATE-SENTINEL'
        def noisy(row, review):
            print(sentinel, row)
            print(sentinel, review, file=sys.stderr)
            return True
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            approved = candidates.attach_reviewed(dataset(), [evidence()], today='2026-06-01', independent_verifier=noisy)
        self.assertNotIn(sentinel, out.getvalue() + err.getvalue())
        self.assertEqual(filter_records(approved, {})['records'][0]['verified_metadata'], {'source_title': 'SYNTHETIC-TITLE'})

    def test_private_verifier_exception_is_suppressed_and_fails_closed(self):
        layers = {'d8': {'sources': [{'line': 1, 'value': {'id': 'synthetic:source', 'title': DATA[KEY]['source_title']}}],
                         'editions': [{'line': 1, 'value': {'id': 'synthetic:edition', 'source_id': 'synthetic:source'}}]}}
        candidates = prepare_private_candidates(dataset(), layers)
        sentinel = 'SYNTHETIC-EXCEPTION-PRIVATE-SENTINEL'
        def failing(row, review):
            print(sentinel, file=sys.stderr)
            raise RuntimeError(sentinel)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rejected = candidates.attach_reviewed(dataset(), [evidence()], today='2026-06-01', independent_verifier=failing)
        self.assertNotIn(sentinel, out.getvalue() + err.getvalue())
        self.assertEqual(filter_records(rejected, {})['records'][0]['verified_metadata'], {})


if __name__ == '__main__':
    unittest.main()
