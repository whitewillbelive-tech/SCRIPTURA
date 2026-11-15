"""Synthetic-only D16 group membership, isolation and boundary tests."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from k37_bridge.d16_groups import build_d16_index, get_d16_sets, d16_summary, safe_d16_passage


def entry(line, **value):
    return {'line': line, 'value': value}


def fixture():
    layers = {
        'd13': {'passages': [entry(1,id='private-p1',corpus='Bible',reference_scheme='synthetic-one',reference='Genesis 1:1')],
                'claims': [entry(1,id='private-c1',passage_ids=['private-p1'])]},
        'd14': {'passages': [entry(1,id='private-p2',corpus='Quran',reference_scheme='synthetic-two',reference='Quran 2:1')],
                'claims': [entry(1,id='private-c2',passage_ids=['private-p1']), entry(2,id='private-c3',passage_ids=['private-p2'])]}}
    records = [{'key':'d13:claims:1'}, {'key':'d14:claims:1'}, {'key':'d14:claims:2'}]
    groups = [entry(1,claim_ids=['private-c1','private-c2'],passage_id='private-p1'),
              entry(2,claim_ids=['private-c2','private-c3'],passage_ids=['private-p1','private-p2'])]
    return layers, records, groups


class D16GroupsTests(unittest.TestCase):
    def test_exact_group_and_cross_corpus_partition(self):
        layers,records,groups=fixture(); idx=build_d16_index(layers,records,groups)
        entries=get_d16_sets({'_d16_group_index':idx}); summary=d16_summary({'_d16_group_index':idx})
        self.assertEqual(summary['validated_groups'],2)
        self.assertEqual(summary['partitioned_entries'],3)
        self.assertEqual(summary['claim_refs'],4)
        self.assertEqual(len(entries),3)
        self.assertEqual(entries[0]['claim_keys'],['d13:claims:1','d14:claims:1'])
        self.assertNotEqual(entries[1]['corpus'],entries[2]['corpus'])
        self.assertNotEqual(entries[1]['scheme'],entries[2]['scheme'])
        self.assertEqual(entries[1]['claim_keys'],['d14:claims:1'])
        self.assertEqual(entries[2]['claim_keys'],['d14:claims:2'])
        self.assertTrue(all('private-' not in str(item) for item in entries))

    def test_invalid_or_missing_member_is_pending(self):
        layers,records,groups=fixture(); groups[0]['value']['claim_ids'].append('private-missing')
        result=d16_summary({'_d16_group_index':build_d16_index(layers,records,groups)})
        self.assertEqual(result['pending_groups'],1)
        self.assertEqual(result['validated_groups'],1)

    def test_group_does_not_invent_claim_passage_connection(self):
        layers,records,groups=fixture();groups[0]['value']['claim_ids']=['private-c1','private-c3']
        result=d16_summary({'_d16_group_index':build_d16_index(layers,records,groups)})
        self.assertEqual(result['pending_groups'],1)

    def test_missing_and_duplicate_entries_fail_closed(self):
        layers,records,groups=fixture();groups[0]['value']['claim_ids']=['private-c1','private-c1']
        groups[1]['line']=groups[0]['line']
        result=d16_summary({'_d16_group_index':build_d16_index(layers,records,groups)})
        self.assertEqual(result['pending_groups'],2)
        self.assertEqual(result['validated_groups'],0)

    def test_malformed_claim_reference_quarantines_only_dependent_groups(self):
        layers,records,groups=fixture()
        layers['d13']['claims'][0]['value']['passage_ids']=[['invalid']]
        result=d16_summary({'_d16_group_index':build_d16_index(layers,records,groups)})
        self.assertEqual(result['pending_groups'],1)
        self.assertEqual(result['validated_groups'],1)

    def test_duplicate_group_coordinate_quarantines_both_rows(self):
        layers,records,groups=fixture();groups[1]['line']=groups[0]['line']
        result=d16_summary({'_d16_group_index':build_d16_index(layers,records,groups)})
        self.assertEqual(result['pending_groups'],2)
        self.assertEqual(result['validated_groups'],0)

    def test_untrusted_index_and_bad_reference_are_not_exposed(self):
        self.assertEqual(get_d16_sets({'_d16_group_index':{'items':['secret']}}),[])
        self.assertIsNone(safe_d16_passage({'corpus':'Bible_1','scheme':'d16_scheme_1','reference':'<synthetic>'}))
        self.assertIsNone(safe_d16_passage({'corpus':'Quran_1','scheme':'d16_scheme_1','reference':'Genesis 1:1'}))
        self.assertIsNotNone(safe_d16_passage({'corpus':'Bible_1','scheme':'d16_scheme_1','reference':'Genesis 1:1, 3'}))
        self.assertIsNotNone(safe_d16_passage({'corpus':'Bible_1','scheme':'d16_scheme_1','reference':'Genesis 1'}))

    def test_result_is_detached_and_opaque(self):
        layers,records,groups=fixture(); idx=build_d16_index(layers,records,groups)
        self.assertNotIn('private-',repr(idx))
        first=get_d16_sets({'_d16_group_index':idx}); first[0]['claim_keys'].append('private-evil')
        self.assertNotIn('private-evil',get_d16_sets({'_d16_group_index':idx})[0]['claim_keys'])


if __name__=='__main__':unittest.main()
