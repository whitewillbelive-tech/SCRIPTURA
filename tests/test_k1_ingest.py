"""Synthetic-only K-1 boundary, quarantine and future evidence tests."""
import copy
import hashlib
import io
import sys
import unittest
from pathlib import Path
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from j2_bridge.candidate_readonly import CandidateError
from k1_bridge.candidate_archive import (_ledger_summary, _source_duplicate_counts, _linkage_counts,
                                          _ledger_references, _manifest_counts, load_k1_archive)
from k1_bridge.synthetic_eligibility import synthetic_display_allowed


def entry(**kwargs):
    return {'value': kwargs, 'line': 1}


class ReceiptTests(unittest.TestCase):
    def test_manifest_checks_bytes_missing_and_complete_coverage(self):
        def archive(data, *, missing=False):
            contents = io.BytesIO()
            with ZipFile(contents, 'w') as z:
                z.writestr('synthetic/a.txt', data)
                expected = hashlib.sha256(b'expected').hexdigest()
                z.writestr('synthetic/checksums.txt', expected + '  ' + ('missing.txt' if missing else 'a.txt') + '\n')
            contents.seek(0)
            return ZipFile(contents)
        with archive(b'expected') as z:
            result = _manifest_counts(z, 'synthetic/checksums.txt')
            self.assertEqual((result['matched'], result['missing'], result['invalid']), (1, 0, 0))
            self.assertTrue(result['all_members_covered'])
        with archive(b'tampered') as z:
            self.assertEqual(_manifest_counts(z, 'synthetic/checksums.txt')['invalid'], 1)
        with archive(b'expected', missing=True) as z:
            result = _manifest_counts(z, 'synthetic/checksums.txt')
            self.assertEqual(result['missing'], 1)
            self.assertFalse(result['all_members_covered'])

    def test_ledger_preserves_candidate_as_observation_only(self):
        rows = [entry(entity_id='synthetic:a', field_group='bibliography', decision='candidate_visible_local'),
                entry(entity_id='synthetic:a', field_group='full_text', decision='unknown')]
        result = _ledger_summary(rows)
        self.assertEqual(result['candidate_visible_local'], 1)
        self.assertEqual(result['unknown'], 1)
        self.assertEqual(result['total'], 2)
        self.assertNotIn('permissions', result)

    def test_ledger_rejects_duplicate_entity_group(self):
        row = entry(entity_id='synthetic:a', field_group='bibliography', decision='unknown')
        with self.assertRaises(CandidateError):
            _ledger_summary([row, copy.deepcopy(row)])

    def test_ledger_rejects_unknown_status_group_and_missing_entity(self):
        for update in ({'decision': 'allowed'}, {'field_group': 'invented'}, {'entity_id': ''}):
            row = dict(entity_id='synthetic:a', field_group='bibliography', decision='unknown')
            row.update(update)
            with self.subTest(field=next(iter(update))), self.assertRaises(CandidateError):
                _ledger_summary([entry(**row)])

    def test_duplicate_candidates_do_not_merge(self):
        old = [{'id': 'synthetic:old', 'title': 'A', 'url': 'https://example.invalid/a'}]
        new = [{'id': 'synthetic:new', 'title': 'a', 'url': 'https://example.invalid/a'}]
        counts = _source_duplicate_counts(old, new)
        self.assertEqual(counts['cross_title'], 1)
        self.assertEqual(counts['cross_url'], 1)
        self.assertEqual(len(old), 1)
        self.assertEqual(len(new), 1)
        self.assertTrue(all(type(value) is int for value in counts.values()))

    def test_duplicate_new_identity_fails_closed(self):
        with self.assertRaises(CandidateError):
            _source_duplicate_counts([{'id': 'synthetic:a'}], [{'id': 'synthetic:a'}])
        with self.assertRaises(CandidateError):
            _source_duplicate_counts([], [{'id': 'synthetic:a'}, {'id': 'synthetic:a'}])

    def test_linkage_counts_ambiguous_target_as_unresolved(self):
        source = entry(id='synthetic:s')
        edition = entry(id='synthetic:e', source_id='synthetic:s')
        new = {'sources': [source], 'editions': [edition], 'locators': [], 'rights': [],
               'rights_actions': [], 'review_queue': []}
        result = _linkage_counts({'old': {'sources': [source]}, 'new': new}, new)
        self.assertEqual(result['editions_source_id_present'], 1)
        self.assertEqual(result['editions_source_id_resolved'], 0)
        self.assertTrue(all(type(value) is int for value in result.values()))

    def test_ledger_chain_and_exact_groups_reject_wrong_edition(self):
        groups = ('bibliography', 'own_summary', 'short_quote', 'full_text', 'private_link')
        rows = [entry(entity_id='synthetic:s', entity_kind='source', field_group=g,
                      decision='unknown') for g in groups]
        rows[0]['value'].update(decision='candidate_visible_local', exact_display_field=['title', 'creator'],
                                source_edition_id='synthetic:e', source_locator_id='synthetic:l',
                                other_subfields_default_hidden=True)
        source = entry(id='synthetic:s')
        edition = entry(id='synthetic:e', source_id='synthetic:s')
        locator = entry(id='synthetic:l', edition_id='synthetic:e')
        layers = {'synthetic': {'sources': [source], 'editions': [edition], 'locators': [locator]}}
        result = _ledger_references(rows, layers)
        self.assertTrue(result['groups_complete'])
        self.assertTrue(result['candidate_chain_valid'])
        bad = copy.deepcopy(layers)
        bad['synthetic']['editions'][0]['value']['source_id'] = 'synthetic:other'
        self.assertFalse(_ledger_references(rows, bad)['candidate_chain_valid'])
        self.assertFalse(_ledger_references(rows[:-1], layers)['groups_complete'])
        bad_rows = copy.deepcopy(rows)
        bad_rows[0]['value']['entity_kind'] = 'claim'
        self.assertEqual(_ledger_references(bad_rows, layers)['invalid_entity_references'], 1)

    def test_non_archive_returns_fixed_error(self):
        with self.assertRaises(CandidateError) as ctx:
            load_k1_archive(b'synthetic-not-a-zip')
        self.assertIn(str(ctx.exception), {'archive_invalid', 'archive_not_recognized'})


class SyntheticEligibilityTests(unittest.TestCase):
    def setUp(self):
        self.e = {'entity_id': 'synthetic:source', 'edition_id': 'synthetic:edition',
                  'locator_id': 'synthetic:locator', 'reviewer': 'synthetic:reviewer',
                  'action': 'browse', 'purpose': 'private_local_candidate_review_only',
                  'jurisdiction': 'synthetic:test', 'field': 'source_title',
                  'decision': 'candidate_visible_local', 'rights_decision': 'allowed',
                  'reviewed_at': '2026-01-01', 'valid_from': '2025-01-01', 'valid_until': '2027-01-01',
                  'license_evidence': 'https://example.invalid/license',
                  'source_evidence': 'https://example.invalid/source',
                  'rights_evidence': 'https://example.invalid/rights',
                  'verification_method': 'independently_checked', 'transformation': 'identity',
                  'other_subfields_default_hidden': True}
        self.r = {key: self.e[key] for key in ('entity_id', 'edition_id', 'locator_id', 'action', 'purpose', 'jurisdiction', 'field')}

    def test_exact_synthetic_fields_can_be_simulated(self):
        for field in ('source_title', 'source_creator'):
            e = dict(self.e, field=field); r = dict(self.r, field=field)
            self.assertTrue(synthetic_display_allowed(e, r, today='2026-06-01'))

    def test_wrong_identity_field_scope_or_purpose_cannot_transfer(self):
        for key, bad in {'entity_id': 'synthetic:other', 'edition_id': 'synthetic:other',
                         'locator_id': 'synthetic:other', 'field': 'source_doi',
                         'purpose': 'redistribution', 'action': 'embed', 'jurisdiction': 'synthetic:other'}.items():
            with self.subTest(key=key):
                self.assertFalse(synthetic_display_allowed(self.e, dict(self.r, **{key: bad}), today='2026-06-01'))

    def test_unverified_or_conditional_rights_and_real_identity_rejected(self):
        for key, bad in {'rights_decision': 'conditional', 'verification_method': 'unchecked',
                         'entity_id': 'real:source', 'reviewer': 'real:reviewer',
                         'other_subfields_default_hidden': False, 'transformation': 'summary',
                         'license_evidence': 'https://example.com/license', 'source_evidence': '',
                         'rights_evidence': 'https://example.invalid/', 'decision': 'metadata_candidate'}.items():
            with self.subTest(key=key):
                self.assertFalse(synthetic_display_allowed(dict(self.e, **{key: bad}), self.r, today='2026-06-01'))

    def test_dates_missing_expired_and_before_review_fail(self):
        for now in ('2024-01-01', '2028-01-01', 'not-a-date', None):
            with self.subTest(now=now):
                self.assertFalse(synthetic_display_allowed(self.e, self.r, today=now))
        e = dict(self.e); del e['reviewed_at']
        self.assertFalse(synthetic_display_allowed(e, self.r, today='2026-06-01'))


if __name__ == '__main__':
    unittest.main()
