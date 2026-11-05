import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from check_fixture_policy import check


class FixturePolicyTests(unittest.TestCase):
    def inspect(self, data):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'sample.json'
            path.write_text(json.dumps(data), encoding='utf-8')
            return check(path)

    def test_synthetic_metadata_only_fixture_allowed(self):
        self.assertEqual(self.inspect({'metadata': {'is_synthetic': True, 'approved_for_public_display': False}, 'sources': [{'title': 'fictional'}]}), [])

    def test_unclassified_and_real_data_are_not_fixture_approved(self):
        for metadata in ({}, {'is_synthetic': False, 'approved_for_public_display': False}, {'is_synthetic': True, 'approved_for_public_display': True}):
            with self.subTest(metadata=metadata):
                self.assertTrue(self.inspect({'metadata': metadata}))

    def test_raw_text_and_embeddings_rejected_at_any_depth(self):
        for key in ('full_text', 'raw_text', 'embedding', 'embeddings'):
            with self.subTest(key=key):
                self.assertTrue(self.inspect({'metadata': {'is_synthetic': True, 'approved_for_public_display': False}, 'nested': [{key: 'sample'}]}))
