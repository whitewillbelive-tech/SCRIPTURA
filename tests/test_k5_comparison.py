"""Synthetic K5 evidence-bound comparison; no research data."""
import contextlib
import io
import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from k5_bridge.comparison import build_private_index, exact_passage_claims


def synthetic():
    return {
        'sources': [{'id': 'synthetic:source'}],
        'editions': [{'id': 'synthetic:edition', 'source_id': 'synthetic:source'}],
        'locators': [{'id': 'synthetic:locator', 'source_id': 'synthetic:source', 'edition_id': 'synthetic:edition'}],
        'evidence': [{'id': 'synthetic:evidence', 'claim_id': 'synthetic:claim', 'locator_id': 'synthetic:locator'}],
        'claims': [{'id': 'synthetic:claim', 'locator_id': 'synthetic:locator', 'statement_ko': 'SYNTHETIC STATEMENT', 'reasoning_ko': 'SYNTHETIC REASON'},
                   {'id': 'synthetic:other', 'locator_id': 'synthetic:locator'}],
        'rights': [], 'relationships': []}


def review(field='statement_ko'):
    return {'claim_id': 'synthetic:claim', 'field': field,
            'source_id': 'synthetic:source', 'edition_id': 'synthetic:edition',
            'locator_id': 'synthetic:locator', 'evidence_id': 'synthetic:evidence',
            'scope': 'private_local_display', 'self_authored': True, 'nonquotation': True,
            'privacy_cleared': True, 'rights_cleared': True}


class ComparisonEvidenceTests(unittest.TestCase):
    def test_fields_are_independent_and_never_automatically_academic(self):
        index = build_private_index(synthetic(), [review()], verifier=lambda *args: True)
        self.assertEqual(index.for_claim('synthetic:claim'), {'statement_ko': {'value': 'SYNTHETIC STATEMENT', 'status': 'recorded_unverified'}})
        self.assertNotIn('reasoning_ko', index.for_claim('synthetic:claim'))
        self.assertNotIn('SYNTHETIC STATEMENT', repr(index))
        with self.assertRaises(TypeError):
            json.dumps(index)

    def test_independent_verifier_is_required_and_exact_true(self):
        for callback in (None, False):
            with self.assertRaises(ValueError):
                build_private_index(synthetic(), [review()], verifier=callback)
        for response in (False, 1, 'yes'):
            index = build_private_index(synthetic(), [review()], verifier=lambda *args: response)
            self.assertEqual(index.for_claim('synthetic:claim'), {})

    def test_verifier_exception_and_stdout_stderr_are_suppressed(self):
        def noisy(*args):
            print('SYNTHETIC-PRIVATE-SENTINEL')
            print('SYNTHETIC-PRIVATE-SENTINEL', file=sys.stderr)
            raise RuntimeError('SYNTHETIC-PRIVATE-SENTINEL')
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            index = build_private_index(synthetic(), [review()], verifier=noisy)
        self.assertEqual(index.for_claim('synthetic:claim'), {})
        self.assertNotIn('SYNTHETIC-PRIVATE-SENTINEL', out.getvalue() + err.getvalue())

    def test_false_or_mismatched_scope_does_not_grant(self):
        for key, value in (('source_id', 'synthetic:other'), ('edition_id', 'synthetic:other'),
                           ('locator_id', 'synthetic:other'), ('evidence_id', 'synthetic:other'),
                           ('scope', 'public'), ('self_authored', False), ('nonquotation', False),
                           ('privacy_cleared', False), ('rights_cleared', False)):
            bad = review(); bad[key] = value
            index = build_private_index(synthetic(), [bad], verifier=lambda *args: True)
            self.assertEqual(index.for_claim('synthetic:claim'), {})

    def test_mismatched_chain_or_duplicate_evidence_is_rejected(self):
        for change in ('edition', 'source', 'evidence', 'duplicate_id'):
            tables = synthetic()
            if change == 'edition': tables['editions'][0]['source_id'] = 'synthetic:other'
            if change == 'source': tables['locators'][0]['source_id'] = 'synthetic:other'
            if change == 'evidence': tables['evidence'].append(deepcopy(tables['evidence'][0]))
            if change == 'duplicate_id': tables['sources'].append(deepcopy(tables['sources'][0]))
            self.assertEqual(build_private_index(tables, [review()], verifier=lambda *args: True).for_claim('synthetic:claim'), {})

    def test_duplicate_review_and_field_restrictions_fail_closed(self):
        tables = synthetic()
        self.assertEqual(build_private_index(tables, [review(), review()], verifier=lambda *args: True).for_claim('synthetic:claim'), {})
        tables['locators'][0]['private_fields'] = ['statement_ko']
        index = build_private_index(tables, [review(), review('reasoning_ko')], verifier=lambda *args: True)
        self.assertNotIn('statement_ko', index.for_claim('synthetic:claim'))
        self.assertIn('reasoning_ko', index.for_claim('synthetic:claim'))

    def test_relevant_rights_block_while_other_action_does_not(self):
        for action, status in (('browse', 'unknown'), ('display', 'conditional'), ('reasoning_ko', 'denied')):
            tables = synthetic(); tables['rights'] = [{'edition_id': 'synthetic:edition', 'action': action, 'permission': status}]
            field = 'reasoning_ko' if action == 'reasoning_ko' else 'statement_ko'
            self.assertEqual(build_private_index(tables, [review(field)], verifier=lambda *args: True).for_claim('synthetic:claim'), {})
        tables = synthetic(); tables['rights'] = [{'edition_id': 'synthetic:edition', 'action': 'full_text', 'decision': 'denied'}]
        self.assertIn('statement_ko', build_private_index(tables, [review()], verifier=lambda *args: True).for_claim('synthetic:claim'))

    def test_sensitive_text_and_objects_are_not_published(self):
        for value in ('SYNTHETIC <tag>', 'SYNTHETIC https://example.invalid/a', 'SYNTHETIC name@example.invalid', '“SYNTHETIC quote”'):
            tables = synthetic(); tables['claims'][0]['statement_ko'] = value
            self.assertEqual(build_private_index(tables, [review()], verifier=lambda *args: True).for_claim('synthetic:claim'), {})
        tables = synthetic(); tables['sources'][0]['privacy_status'] = 'private'
        self.assertEqual(build_private_index(tables, [review()], verifier=lambda *args: True).for_claim('synthetic:claim'), {})

    def test_relationships_never_inferred_or_accepted_without_evidence(self):
        tables = synthetic()
        self.assertEqual(build_private_index(tables, [], verifier=lambda *args: True).relations_for('synthetic:claim'), [])
        row = {'id': 'synthetic:relation', 'subject_id': 'synthetic:claim', 'object_id': 'synthetic:other', 'relation_type': 'rebuts'}
        tables['relationships'] = [row]
        self.assertEqual(build_private_index(tables, [], verifier=lambda *args: True).relations_for('synthetic:claim'), [])
        row['locator_id'] = 'synthetic:locator'
        pending = build_private_index(tables, [], verifier=lambda *args: False).relations_for('synthetic:claim')
        self.assertEqual(pending[0]['kind'], 'unconfirmed_relation')
        self.assertEqual(pending[0]['reported_kind'], 'rebuts')
        self.assertEqual(pending[0]['status'], 'pending_evidence_review')
        index = build_private_index(tables, [], verifier=lambda *args: True)
        relation = index.relations_for('synthetic:claim')[0]
        self.assertEqual(relation['status'], 'recorded_unverified')
        self.assertEqual(relation['target_key'], index.reference_for_claim('synthetic:other'))
        self.assertTrue(relation['target_key'].startswith('k5:claims:'))
        self.assertNotIn('synthetic:other', json.dumps(relation))
        row['relation_type'] = 'invented'
        self.assertEqual(build_private_index(tables, [], verifier=lambda *args: True).relations_for('synthetic:claim'), [])

    def test_exact_address_never_crosses_corpus_or_scheme(self):
        selected = {'corpus': 'bible', 'scheme': 'scheme-a', 'reference': 'synthetic 1:1'}
        items = [{'key': 'k5:claims:1', 'passages': [dict(selected)]},
                 {'key': 'k5:claims:2', 'passages': [dict(selected, corpus='quran')]},
                 {'key': 'd12:claims:3', 'passages': [dict(selected, scheme='scheme-b')]},
                 {'key': 'k5:claims:4', 'passages': [dict(selected, reference='synthetic 1:2')]},
                 {'key': 'SYNTHETIC-PRIVATE-ORIGINAL-ID', 'passages': [dict(selected)]},
                 {'key': 'k5:claims:' + '9' * 300, 'passages': [dict(selected)]}]
        self.assertEqual(exact_passage_claims(items, selected), ['k5:claims:1'])
        with self.assertRaises(ValueError):
            exact_passage_claims(items, {'corpus': 'bible'})

    def test_malformed_reference_and_relation_are_safe(self):
        tables = synthetic()
        tables['claims'][0]['locator_id'] = {'private': 'SYNTHETIC-PRIVATE-SENTINEL'}
        tables['relationships'] = [{'relation_type': [], 'subject_id': {}, 'object_id': []}]
        index = build_private_index(tables, [review()], verifier=lambda *args: True)
        self.assertEqual(index.for_claim('synthetic:claim'), {})
        self.assertEqual(index.relations_for('synthetic:claim'), [])
        tables['relationships'] = None
        with self.assertRaises(ValueError) as caught:
            build_private_index(tables, [review()], verifier=lambda *args: True)
        self.assertEqual(str(caught.exception), 'comparison_invalid')

    def test_evidence_from_distinct_source_is_bound_and_permissions_separate(self):
        tables = synthetic()
        tables['sources'].append({'id': 'synthetic:second-source'})
        tables['editions'].append({'id': 'synthetic:second-edition', 'source_id': 'synthetic:second-source'})
        tables['locators'].append({'id': 'synthetic:second-locator', 'source_id': 'synthetic:second-source', 'edition_id': 'synthetic:second-edition'})
        tables['evidence'].append({'id': 'synthetic:second-evidence', 'claim_id': 'synthetic:claim', 'locator_id': 'synthetic:second-locator'})
        checked = review('reasoning_ko')
        checked.update(evidence_id='synthetic:second-evidence', evidence_source_id='synthetic:second-source',
                       evidence_edition_id='synthetic:second-edition', evidence_locator_id='synthetic:second-locator')
        # Multiple cited evidence records are legitimate when the review names
        # one explicitly and that evidence has a verified separate chain.
        index = build_private_index(tables, [checked], verifier=lambda *args: True)
        self.assertIn('reasoning_ko', index.for_claim('synthetic:claim'))
        for field in ('evidence_source_id', 'evidence_edition_id', 'evidence_locator_id'):
            mismatch = dict(checked, **{field: 'synthetic:wrong'})
            self.assertEqual(build_private_index(tables, [mismatch], verifier=lambda *args: True).for_claim('synthetic:claim'), {})
        broken = deepcopy(tables)
        broken['editions'][1]['source_id'] = 'synthetic:wrong'
        self.assertEqual(build_private_index(broken, [checked], verifier=lambda *args: True).for_claim('synthetic:claim'), {})
        limited = deepcopy(tables)
        limited['rights'] = [{'edition_id': 'synthetic:second-edition', 'action': 'reasoning_ko', 'permission': 'denied'}]
        self.assertEqual(build_private_index(limited, [checked], verifier=lambda *args: True).for_claim('synthetic:claim'), {})
        restricted = deepcopy(tables)
        restricted['locators'][1]['private_fields'] = ['reasoning_ko']
        self.assertEqual(build_private_index(restricted, [checked], verifier=lambda *args: True).for_claim('synthetic:claim'), {})

    def test_k3_relation_schema_aliases_and_conflicting_references(self):
        tables = synthetic()
        row = {'id': 'synthetic:relation', 'from_claim_id': 'synthetic:claim',
               'to_claim_id': 'synthetic:other', 'relation_type': 'support',
               'source_locator_id': 'synthetic:locator'}
        tables['relationships'] = [row]
        result = build_private_index(tables, [], verifier=lambda *args: True).relations_for('synthetic:claim')
        self.assertEqual(result[0]['kind'], 'supports')
        for raw, expected in (('qualify', 'qualifies'), ('contrast', 'contrasts'),
                              ('contradict', 'contradicts'), ('direct_rebuttal', 'rebuts')):
            row['relation_type'] = raw
            result = build_private_index(tables, [], verifier=lambda *args: True).relations_for('synthetic:claim')
            self.assertEqual(result[0]['kind'], expected)
        row['subject_id'] = 'synthetic:wrong'
        self.assertEqual(build_private_index(tables, [], verifier=lambda *args: True).relations_for('synthetic:claim'), [])
        row.pop('subject_id')
        tables['editions'][0]['source_id'] = 'synthetic:wrong'
        self.assertEqual(build_private_index(tables, [], verifier=lambda *args: True).relations_for('synthetic:claim'), [])


if __name__ == '__main__':
    unittest.main()
