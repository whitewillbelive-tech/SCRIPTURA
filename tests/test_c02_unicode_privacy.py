"""Synthetic-only privacy regression for compatibility Unicode characters."""
import unittest

from test_k13_local_candidate import sample, make
from test_real_content import fixture, build
from k37_bridge.real_content import content_for_record


class UnicodePrivacyTests(unittest.TestCase):
    def test_contact_data_in_compatibility_forms_is_not_projected(self):
        values = (
            'ｓｙｎｔｈｅｔｉｃ＠ｅｘａｍｐｌｅ．ｉｎｖａｌｉｄ',
            'ｈｔｔｐｓ：／／ｅｘａｍｐｌｅ．ｉｎｖａｌｉｄ',
            '０１０－１２３４－５６７８',
            '０００１０１－１２３４５６７',
        )
        for value in values:
            for field, projected in (('title', 'source_title'), ('creator', 'source_creator'),
                                     ('publisher', 'source_publisher')):
                with self.subTest(field=field, kind=values.index(value)):
                    dataset, layers = sample()
                    layers['d9']['sources'][0]['value'][field] = value
                    for key in ('d9:sources:1', 'd9:claims:1'):
                        result = make(dataset, layers, key)[projected]
                        self.assertEqual(result['status'], 'restricted')
                        self.assertIsNone(result['value'])
                        self.assertEqual(result['reason'], 'sensitive_or_personal')

    def test_safe_compatibility_characters_are_not_rewritten(self):
        dataset, layers = sample()
        value = 'ＡＢＣ 학술 자료'
        layers['d9']['sources'][0]['value']['title'] = value
        result = make(dataset, layers)['source_title']
        self.assertEqual(result['status'], 'recorded_unverified')
        self.assertEqual(result['value'], value)

    def test_protected_names_cannot_be_disguised_in_metadata(self):
        dataset, layers = sample()
        layers['d9']['agents'] = [{'value': {'id': 'synthetic:private',
                                             'name': 'SYNTHETICPRIVATE', 'privacy_status': 'private'}}]
        for field, projected in (('title', 'source_title'), ('creator', 'source_creator'),
                                 ('publisher', 'source_publisher')):
            with self.subTest(field=field):
                row = layers['d9']['sources'][0]['value']
                prior = row[field]
                row[field] = 'ＳＹＮＴＨＥＴＩＣＰＲＩＶＡＴＥ'
                result = make(dataset, layers)[projected]
                self.assertEqual(result['status'], 'restricted')
                self.assertIsNone(result['value'])
                row[field] = prior

    def test_protected_names_cannot_be_disguised_in_claim_content(self):
        layers, records, dataset = fixture()
        layers['d13']['agents'] = [{'line': 1, 'value': {'id': 'synthetic-private',
                                   'name': 'SYNTHETICPRIVATE', 'privacy_status': 'private'}}]
        claim = layers['d13']['claims'][0]['value']
        for field, projected in (('speaker', 'reported_speaker'), ('tradition', 'tradition'),
                                 ('statement_ko', 'summary'), ('reasoning_ko', 'reasoning')):
            with self.subTest(field=field):
                prior = claim[field]
                claim[field] = 'ＳＹＮＴＨＥＴＩＣＰＲＩＶＡＴＥ'
                result = content_for_record(build(layers, records, dataset), 'D16', 'd13:claims:1')
                self.assertIsNone(result[projected])
                claim[field] = prior


if __name__ == '__main__':
    unittest.main()
