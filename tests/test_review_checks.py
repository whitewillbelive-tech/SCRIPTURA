"""Synthetic-only review evidence and reference tests."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from k37_bridge.review_checks import validate_review_refs


def wrap(row):return {'line':1,'value':row}

def fixture():
    layers={'d13': {'sources':[wrap({'id':'synthetic:s1'}),wrap({'id':'synthetic:s2'})],
                    'editions':[wrap({'id':'synthetic:e1','source_id':'synthetic:s1'})],
                    'locators':[wrap({'id':'synthetic:l1','source_id':'synthetic:s1','edition_id':'synthetic:e1'})],
                    'claims':[wrap({'id':'synthetic:c1','source_id':'synthetic:s1','source_locator_id':'synthetic:l1'}),wrap({'id':'synthetic:c2','source_id':'synthetic:s2'})],
                    'relationships':[wrap({'id':'synthetic:r1'})]}}
    tables={'claim_review_events':[wrap({'baseline_claim_id':'synthetic:c1','baseline_source_id':'synthetic:s1','baseline_locator_id':'synthetic:l1'})],
            'd12_field_audit':[wrap({'baseline_claim_id':'synthetic:c1'})],
            'source_duplicate_review':[wrap({'new_source_id':'synthetic:s1','prior_source_id':'synthetic:s2'})],
            'relation_evidence':[wrap({'baseline_relation_id':'synthetic:r1','baseline_subject_claim_id':'synthetic:c1','baseline_object_claim_id':'synthetic:c2'})],
            'relationships':[wrap({'subject_id':'synthetic:c1','object_id':'synthetic:c2'})],
            'rights_evidence':[wrap({'source_id':'synthetic:s1','edition_id':'synthetic:e1'})]}
    return layers,tables


class ReviewChecksTests(unittest.TestCase):
    def test_valid_review_references_do_not_imply_verification(self):
        layers,tables=fixture();r=validate_review_refs(layers,tables)
        for key in tables:self.assertEqual(r[key+'_references_valid'],1)
        self.assertEqual(r['d12_field_audit_missing_optional'],1)
        self.assertTrue(all(isinstance(v,int) and not isinstance(v,bool) for v in r.values()))
        self.assertNotIn('synthetic:',repr(r))
        self.assertNotIn('verified',r)

    def test_source_conflict_is_not_silently_accepted(self):
        layers,tables=fixture();tables['claim_review_events'][0]['value']['baseline_source_id']='synthetic:s2'
        r=validate_review_refs(layers,tables)
        self.assertEqual(r['claim_review_events_chain_conflicts'],1)
        self.assertEqual(r['claim_review_events_pending'],1)
        self.assertEqual(r['d12_field_audit_references_valid'],1)

    def test_relation_evidence_must_match_recorded_endpoints(self):
        layers,tables=fixture()
        layers['d13']['relationships'][0]['value'].update(subject_id='synthetic:c2',object_id='synthetic:c1')
        r=validate_review_refs(layers,tables)
        self.assertEqual(r['relation_evidence_chain_conflicts'],1)
        self.assertEqual(r['relation_evidence_pending'],1)

    def test_missing_and_wrong_table_are_pending(self):
        layers,tables=fixture();tables['relation_evidence'][0]['value']['baseline_subject_claim_id']='synthetic:s1'
        tables['source_duplicate_review'][0]['value'].pop('prior_source_id')
        r=validate_review_refs(layers,tables)
        self.assertEqual(r['relation_evidence_unresolved'],1)
        self.assertEqual(r['source_duplicate_review_missing_required'],1)

    def test_cross_table_collision_and_changed_history_stay_ambiguous(self):
        layers,tables=fixture();layers['d14']={'claims':[wrap({'id':'synthetic:c1','other':'different'})]}
        r=validate_review_refs(layers,tables)
        self.assertEqual(r['ambiguous_baseline_ids'],1)
        self.assertEqual(r['claim_review_events_pending'],1)

    def test_identical_historical_rows_are_deduplicated(self):
        layers,tables=fixture();layers['d14']={'claims':[wrap({'id':'synthetic:c1','source_id':'synthetic:s1','source_locator_id':'synthetic:l1'})]}
        r=validate_review_refs(layers,tables)
        self.assertEqual(r['ambiguous_baseline_ids'],0)
        self.assertEqual(r['claim_review_events_references_valid'],1)

    def test_missing_optional_is_not_same_as_missing_required(self):
        layers,tables=fixture();r=validate_review_refs(layers,tables)
        self.assertEqual(r['relationships_missing_optional'],2)
        self.assertEqual(r['relationships_pending'],0)
        self.assertEqual(r['relationships_references_valid'],1)

    def test_malformed_input_has_fixed_exception(self):
        with self.assertRaisesRegex(ValueError,'^review_refs_invalid$'):
            validate_review_refs({'synthetic:secret':{'bad':object()}},{})

if __name__=='__main__':unittest.main()
