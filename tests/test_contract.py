import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from validate_fixture import validate  # noqa: E402


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads((ROOT / 'fixtures' / 'demo_valid.json').read_text(encoding='utf-8'))

    def test_valid_synthetic_fixture(self):
        self.assertEqual(validate(copy.deepcopy(self.fixture)), [])

    def test_cannot_publish_synthetic_data(self):
        data = copy.deepcopy(self.fixture)
        data['metadata']['approved_for_public_display'] = True
        self.assertTrue(any('Synthetic' in s for s in validate(data)))

    def test_cannot_duplicate_ids(self):
        data = copy.deepcopy(self.fixture)
        data['agents'].append(data['agents'][0])
        self.assertTrue(any('duplicate ID' in s for s in validate(data)))

    def test_fails_missing_foreign_key(self):
        data = copy.deepcopy(self.fixture)
        data['claim_passages'][0]['passage_id'] = 'psg:nonexistent'
        self.assertTrue(any('missing passages reference' in s for s in validate(data)))

    def test_work_scheme_corpus_mismatch(self):
        data = copy.deepcopy(self.fixture)
        data['corpora'].append({'id':'cor:other','name':'other','corpus_kind':'other'})
        data['reference_schemes'][0]['corpus_id'] = 'cor:other'
        self.assertTrue(any('scheme corpus mismatch' in s for s in validate(data)))

    def test_full_text_needs_verified_license(self):
        data = copy.deepcopy(self.fixture)
        data['sources'][0]['storage_policy'] = 'full_text_allowed'
        self.assertTrue(any('full text requires verified rights' in s for s in validate(data)))

    def test_verified_claim_needs_provenance(self):
        data = copy.deepcopy(self.fixture)
        data['claim_versions'][0]['review_status'] = 'source_verified'
        self.assertTrue(any('verified attribution' in s for s in validate(data)))
        self.assertTrue(any('checked and verified source evidence' in s for s in validate(data)))

    def test_official_doctrine_person_forbidden(self):
        data = copy.deepcopy(self.fixture)
        data['claim_attributions'][0]['attribution_kind'] = 'official_doctrine'
        self.assertTrue(any('individual person' in s for s in validate(data)))

    def test_verified_relation_requires_checked_source(self):
        data = copy.deepcopy(self.fixture)
        data['claim_relations'][0]['review_status'] = 'verified'
        self.assertTrue(any('verified relation requires checked source' in s for s in validate(data)))

    def test_interpretive_link_requires_claimant(self):
        data = copy.deepcopy(self.fixture)
        data['passage_relations'][0]['relation_type'] = 'interpretively_linked'
        self.assertTrue(any('missing agents reference' in s for s in validate(data)))

    def test_claim_evidence_requires_target(self):
        data = copy.deepcopy(self.fixture)
        data['claim_evidence'][0].pop('source_locator_id')
        self.assertTrue(any('no evidence target' in s for s in validate(data)))


if __name__ == '__main__':
    unittest.main()
