"""Synthetic K-4 attribution and evidence boundaries."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from k4_bridge.relations import build_relation_index, RelationIndex


class Receipt:
    def __init__(self, tables):
        self.tables = tables
    def accepted_records(self, table):
        return copy.deepcopy(self.tables.get(table, []))


def data():
    return {'sources': [{'id':'synthetic:source', 'creator':'synthetic:author'}],
            'editions': [{'id':'synthetic:edition', 'source_id':'synthetic:source'}],
            'locators': [{'id':'synthetic:locator', 'edition_id':'synthetic:edition', 'source_id':'synthetic:source'}],
            'agents':[{'id':'synthetic:speaker'}, {'id':'synthetic:writer'}],
            'communities':[{'id':'synthetic:community'}, {'id':'synthetic:other'}],
            'claims':[{'id':'synthetic:claim', 'source_locator_id':'synthetic:locator',
                       'attribution_kind':'community_self_explanation',
                       'community_id':'synthetic:community', 'community_id_role':'self',
                       'verification_status':'source_verified'}]}


class RelationTests(unittest.TestCase):
    def test_self_explanation_is_recorded_not_official_or_peer_reviewed(self):
        result = build_relation_index(Receipt(data())).for_claim('k4:claims:1')
        self.assertEqual(result['community']['role'], 'reported_self')
        self.assertEqual(result['community']['status'], 'recorded_unverified')
        self.assertEqual(result['input_verification_status'], 'source_verified')
        self.assertEqual(result['effective_official_status'], 'pending')
        self.assertEqual(result['independent_scholarly_review'], 'pending')

    def test_writer_is_not_claim_speaker(self):
        result = build_relation_index(Receipt(data())).for_claim('k4:claims:1')
        self.assertIsNone(result['speaker']['actor'])
        self.assertEqual(result['speaker']['status'], 'pending')

    def test_explicit_speaker_is_recorded_with_citation_not_verified(self):
        rows = data(); rows['claims'][0]['speaker_id'] = 'synthetic:speaker'
        result = build_relation_index(Receipt(rows)).for_claim('k4:claims:1')
        self.assertEqual(result['speaker'], {'actor':'k4:agents:1', 'status':'recorded_unverified'})
        self.assertEqual(result['citation']['locator'], 'k4:locators:1')

    def test_critique_subject_does_not_become_speaker(self):
        rows=data(); claim=rows['claims'][0]
        claim.update(attribution_kind='external_critique', community_id_role='target', speaker_id='synthetic:speaker')
        result=build_relation_index(Receipt(rows)).for_claim('k4:claims:1')
        self.assertEqual(result['community']['role'], 'critique_target')
        self.assertEqual(result['speaker']['actor'], 'k4:agents:1')
        self.assertNotEqual(result['speaker']['actor'], result['community']['community'])

    def test_mismatched_role_does_not_become_self_explanation(self):
        rows=data(); rows['claims'][0].update(attribution_kind='external_critique', community_id_role='self')
        self.assertEqual(build_relation_index(Receipt(rows)).for_claim('k4:claims:1')['community']['status'], 'pending')

    def test_disagreeing_community_targets_are_pending(self):
        rows=data(); rows['claims'][0].update(attribution_kind='external_critique', community_id_role='target', target_community_id='synthetic:other')
        self.assertEqual(build_relation_index(Receipt(rows)).for_claim('k4:claims:1')['community']['status'], 'pending')

    def test_same_target_cannot_be_reinterpreted_as_reported_self(self):
        rows=data(); rows['claims'][0]['target_community_id']='synthetic:community'
        self.assertEqual(build_relation_index(Receipt(rows)).for_claim('k4:claims:1')['community']['status'], 'pending')
        rows['claims'][0]['attribution_kind']='external_critique'
        self.assertEqual(build_relation_index(Receipt(rows)).for_claim('k4:claims:1')['community']['status'], 'pending')

    def test_official_source_claim_never_automatically_promotes(self):
        rows=data(); rows['claims'][0].update(attribution_kind='official_doctrine', authority_status='source_verified')
        result=build_relation_index(Receipt(rows)).for_claim('k4:claims:1')
        self.assertEqual(result['kind'], 'unconfirmed_official_claim')
        self.assertEqual(result['input_attribution'], 'official_doctrine')
        self.assertEqual(result['effective_official_status'], 'pending')
        self.assertEqual(result['community']['status'], 'pending')

    def test_missing_or_conflicting_citation_blocks_relationship(self):
        for edit in ('missing', 'mismatch', 'duplicate'):
            with self.subTest(edit=edit):
                rows=data()
                if edit=='missing': rows['editions']=[]
                elif edit=='mismatch': rows['locators'][0]['source_id']='synthetic:other'
                else: rows['locators'].append(dict(rows['locators'][0]))
                result=build_relation_index(Receipt(rows)).for_claim('k4:claims:1')
                self.assertIsNone(result['citation'])
                self.assertEqual(result['community']['status'], 'pending')

    def test_source_reference_alone_cannot_infer_affiliation(self):
        rows=data(); rows['affiliations']=[{'id':'synthetic:a','agent_id':'synthetic:speaker','community_id':'synthetic:community'}]
        index=build_relation_index(Receipt(rows))
        self.assertEqual(index.affiliations(), ())
        self.assertEqual(index.summary()['affiliations_pending'], 1)

    def test_affiliation_date_order_and_locator(self):
        rows=data(); rows['affiliations']=[{'id':'synthetic:a', 'agent_id':'synthetic:speaker', 'community_id':'synthetic:community', 'source_locator_id':'synthetic:locator','valid_from':'2000-01-01','valid_until':'2010-01-01'}]
        index=build_relation_index(Receipt(rows))
        self.assertEqual(len(index.affiliations()),1)
        self.assertEqual(index.affiliations()[0]['status'],'recorded_unverified')
        rows['affiliations'][0]['valid_until']='1990-01-01'
        self.assertEqual(build_relation_index(Receipt(rows)).affiliations(),())

    def test_returned_affiliation_cannot_mutate_index(self):
        rows=data(); rows['affiliations']=[{'id':'synthetic:a', 'agent_id':'synthetic:speaker',
            'community_id':'synthetic:community', 'source_locator_id':'synthetic:locator'}]
        index=build_relation_index(Receipt(rows))
        exposed=index.affiliations()[0]
        exposed['citation']['source']='changed'
        self.assertEqual(index.affiliations()[0]['citation']['source'],'k4:sources:1')

    def test_partial_dates_preserve_precision_and_reject_impossible_order(self):
        rows=data(); rows['affiliations']=[{'id':'synthetic:a', 'agent_id':'synthetic:speaker',
            'community_id':'synthetic:community', 'source_locator_id':'synthetic:locator',
            'valid_from':'2000', 'valid_until':'2000-06'}]
        relation=build_relation_index(Receipt(rows)).affiliations()[0]
        self.assertEqual((relation['valid_from'],relation['valid_until']),('2000','2000-06'))
        rows['affiliations'][0]['valid_until']='1999-12'
        self.assertEqual(build_relation_index(Receipt(rows)).affiliations(),())
        rows['affiliations'][0]['valid_until']='2000-13'
        self.assertEqual(build_relation_index(Receipt(rows)).affiliations(),())

    def test_malformed_kind_and_role_are_unmapped_not_crash(self):
        rows=data(); rows['claims'][0]['attribution_kind']=['malformed']
        rows['affiliations']=[{'id':'synthetic:a', 'agent_id':'synthetic:speaker',
            'community_id':'synthetic:community', 'source_locator_id':'synthetic:locator', 'role':['malformed']}]
        index=build_relation_index(Receipt(rows))
        self.assertEqual(index.for_claim('k4:claims:1')['kind'],'unmapped')
        self.assertEqual(index.affiliations()[0]['role'],'unmapped')

    def test_errors_and_repr_never_print_sensitive_identifiers(self):
        sentinel='SYNTHETIC_PRIVATE_SENTINEL'
        class Broken:
            def accepted_records(self, _): raise ValueError(sentinel)
        with self.assertRaises(ValueError) as caught: build_relation_index(Broken())
        self.assertEqual(str(caught.exception),'relation_build_failed')
        index=build_relation_index(Receipt(data()))
        self.assertNotIn('synthetic:',repr(index))
        with self.assertRaises(ValueError): RelationIndex(None, {}, (), {})

    def test_unknown_status_is_not_untrusted_text(self):
        rows=data(); rows['claims'][0]['verification_status']='SYNTHETIC_PRIVATE_SENTINEL'
        self.assertEqual(build_relation_index(Receipt(rows)).for_claim('k4:claims:1')['input_verification_status'],'unknown')

if __name__=='__main__':unittest.main()
