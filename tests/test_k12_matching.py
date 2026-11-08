"""Synthetic-only K-1.2 public snapshot matching and confidentiality tests."""
import copy
import json
import socket
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from k12_bridge.matching import plan_private_matches
from j2_private_preview import filter_records

KEY = 'd8:sources:1'
FIELDS = {'source_title': 'SYNTHETIC-TITLE', 'source_creator': 'SYNTHETIC-AUTHOR',
          'source_publisher': 'SYNTHETIC-PUBLISHER', 'source_year': '2099'}
PRIVATE = {KEY: {'source_id': 'synthetic:source', 'edition_id': 'synthetic:edition',
                 'identifiers': {'doi': '10.55555/synthetic-doi'}, 'fields': FIELDS}}
PUBLIC = [{'doi': 'https://doi.org/10.55555/synthetic-doi', 'fields': FIELDS}]


class PublicMatchingTests(unittest.TestCase):
    def test_exact_match_counts_each_field_without_disclosing_values(self):
        plan = plan_private_matches(PRIVATE, PUBLIC)
        self.assertEqual(plan.summary()['matched_cards'], 1)
        self.assertTrue(all(plan.summary()[field] == 1 for field in FIELDS))
        self.assertNotIn(FIELDS['source_title'], repr(plan))
        self.assertNotIn('synthetic-doi', repr(plan))
        with self.assertRaises(TypeError):
            json.dumps(plan)

    def test_missing_publisher_or_year_cannot_be_inferred(self):
        public = copy.deepcopy(PUBLIC)
        del public[0]['fields']['source_publisher']
        del public[0]['fields']['source_year']
        result = plan_private_matches(PRIVATE, public).summary()
        self.assertEqual(result['matched_cards'], 1)
        self.assertEqual(result['source_title'], 1)
        self.assertEqual(result['source_creator'], 1)
        self.assertEqual(result['source_publisher'], 0)
        self.assertEqual(result['source_year'], 0)

    def test_conflicting_identity_fields_or_year_reject_entire_match(self):
        for field in ('source_title', 'source_creator', 'source_year'):
            public = copy.deepcopy(PUBLIC)
            public[0]['fields'][field] = 'SYNTHETIC-OTHER'
            with self.subTest(field=field):
                result = plan_private_matches(PRIVATE, public).summary()
                self.assertEqual(result['matched_cards'], 0)
                self.assertEqual(result['identity_mismatch'], 1)

    def test_duplicate_public_doi_is_ambiguous_even_for_identical_rows(self):
        result = plan_private_matches(PRIVATE, PUBLIC + copy.deepcopy(PUBLIC)).summary()
        self.assertEqual(result['matched_cards'], 0)
        self.assertEqual(result['ambiguous_public'], 1)

    def test_duplicate_doi_for_other_source_or_edition_fails_closed(self):
        for field in ('source_id', 'edition_id'):
            private = copy.deepcopy(PRIVATE)
            private['d8:sources:2'] = copy.deepcopy(private[KEY])
            private['d8:sources:2'][field] = 'synthetic:other'
            with self.subTest(field=field):
                result = plan_private_matches(private, PUBLIC).summary()
                self.assertEqual(result['matched_cards'], 0)
                self.assertEqual(result['ambiguous_private'], 2)

    def test_same_source_and_edition_may_be_related_to_two_cards(self):
        private = copy.deepcopy(PRIVATE)
        private['d8:claims:1'] = copy.deepcopy(private[KEY])
        result = plan_private_matches(private, PUBLIC).summary()
        self.assertEqual(result['matched_cards'], 2)

    def test_missing_or_invalid_doi_is_never_used_as_an_identity(self):
        for doi in ('', 'not-a-doi', 'https://example.invalid/path', None):
            private = copy.deepcopy(PRIVATE)
            private[KEY]['identifiers']['doi'] = doi
            with self.subTest(kind=type(doi).__name__):
                self.assertEqual(plan_private_matches(private, PUBLIC).summary()['matched_cards'], 0)

    def test_snapshot_match_itself_cannot_enable_api_or_private_search(self):
        plan = plan_private_matches(PRIVATE, PUBLIC)
        row = {'key': KEY, 'stage': 'd8', 'record_kind': 'source'}
        dataset = {'dataset': 'D10', 'records': [row], 'counts': {}, 'warnings': [],
                   '_verified_metadata_index': plan}
        response = filter_records(dataset, {})
        self.assertEqual(response['records'][0]['verified_metadata'], {})
        self.assertEqual(filter_records(dataset, {'q': ['SYNTHETIC-TITLE']})['total'], 0)

    def test_comparison_never_performs_network_requests(self):
        with patch.object(socket, 'create_connection', side_effect=AssertionError('network')):
            self.assertEqual(plan_private_matches(PRIVATE, PUBLIC).summary()['matched_cards'], 1)

    def test_invalid_input_uses_fixed_error_only(self):
        with self.assertRaisesRegex(ValueError, '^invalid_match_input$'):
            plan_private_matches('SYNTHETIC-PRIVATE', [])


if __name__ == '__main__':
    unittest.main()
