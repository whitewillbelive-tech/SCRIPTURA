"""Synthetic-only generic archive trust, isolation, and quarantine tests."""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZIP_DEFLATED

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from k3_bridge.receipt import ReceiptError, ResearchReceipt, receive

BASE = 'a' * 64


def sample():
    return {
        'sources': [{'id': 'synthetic:source', 'title': 'Synthetic Source'}],
        'editions': [{'id': 'synthetic:edition', 'source_id': 'synthetic:source'}],
        'locators': [{'id': 'synthetic:locator', 'source_id': 'synthetic:source', 'edition_id': 'synthetic:edition'}],
        'passages': [{'id': 'synthetic:passage', 'corpus': 'Bible', 'scheme': 'synthetic', 'reference': 'Synthetic 1:1'}],
        'claims': [{'id': 'synthetic:claim', 'source_locator_id': 'synthetic:locator', 'passage_ids': ['synthetic:passage']}],
        'evidence': [{'id': 'synthetic:evidence', 'claim_id': 'synthetic:claim', 'locator_id': 'synthetic:locator'}],
    }


def archive(tables=None, version='D13', baseline=BASE, extra=None):
    tables = sample() if tables is None else tables
    files, payloads = [], {}
    for table, rows in tables.items():
        name = 'records/' + table + '.jsonl'
        data = b''.join(json.dumps(row, sort_keys=True).encode() + b'\n' for row in rows)
        payloads[name] = data
        files.append({'path': name, 'table': table, 'sha256': hashlib.sha256(data).hexdigest(), 'count': len(rows)})
    manifest = json.dumps({'schema': 'scriptura.research-archive.v1', 'version': version,
                           'baseline_sha256': baseline, 'files': files}, sort_keys=True).encode()
    out = io.BytesIO()
    with ZipFile(out, 'w', ZIP_DEFLATED) as z:
        z.writestr('manifest.json', manifest)
        for name, data in payloads.items():
            z.writestr(name, data)
        if extra:
            z.writestr(extra, b'synthetic')
    return out.getvalue(), hashlib.sha256(manifest).hexdigest()


class GenericReceiptTests(unittest.TestCase):
    def read(self, tables=None, **kwargs):
        blob, trust = archive(tables, **kwargs)
        return receive(blob, trusted_manifest_sha256=trust, trusted_baseline_sha256=BASE, baseline_ids={})

    def test_authenticated_increment_and_future_version(self):
        for version in ('D13', 'D14', 'D157'):
            receipt = self.read(version=version)
            self.assertEqual(receipt.aggregate()['accepted_rows'], 6)
            self.assertEqual(receipt.aggregate()['quarantined_reference'], 0)
            self.assertEqual(len(receipt.accepted_records('claims')), 1)
            self.assertEqual(receipt.accepted_records('communities'), [])
            self.assertEqual(receipt.version(), version)
            self.assertEqual(receipt.provenance(), {'version': version, 'baseline_anchor_matched': True,
                                                    'baseline_ids_binding_verified': False})

    def test_caller_provided_independent_trust_anchors_required(self):
        blob, trust = archive()
        for manifest, baseline in [('0' * 64, BASE), (trust, '0' * 64), ('invalid', BASE)]:
            with self.assertRaisesRegex(ReceiptError, '^archive_invalid$'):
                receive(blob, trusted_manifest_sha256=manifest, trusted_baseline_sha256=baseline, baseline_ids={})
        with self.assertRaisesRegex(ReceiptError, '^receipt_untrusted$'):
            ResearchReceipt(None, 'D13', {}, {})

    def test_version_progression_against_independent_trusted_baseline(self):
        blob, trust = archive(version='D14')
        opts = dict(trusted_manifest_sha256=trust, trusted_baseline_sha256=BASE, baseline_ids={})
        receipt = receive(blob, **opts, trusted_baseline_version='D13')
        self.assertEqual(receipt.aggregate()['version_order_unverified'], 0)
        self.assertEqual(receive(blob, **opts).aggregate()['version_order_unverified'], 1)
        for baseline in ('D14', 'D15', 'invalid'):
            with self.assertRaisesRegex(ReceiptError, '^archive_invalid$'):
                receive(blob, **opts, trusted_baseline_version=baseline)

    def test_duplicate_new_ids_quarantines_dependents_and_keeps_baseline(self):
        rows = sample()
        rows['sources'].append({'id': 'synthetic:source', 'title': 'Synthetic Source 2'})
        baseline = {'synthetic:baseline': 'sources'}
        before = deepcopy(baseline)
        blob, trust = archive(rows)
        receipt = receive(blob, trusted_manifest_sha256=trust, trusted_baseline_sha256=BASE, baseline_ids=baseline)
        self.assertEqual(baseline, before)
        self.assertEqual(receipt.aggregate()['quarantined_id_collision'], 2)
        self.assertEqual(receipt.aggregate()['accepted_rows'], 1)
        self.assertEqual(receipt.aggregate()['quarantined_reference'], 4)

    def test_collision_with_baseline_never_deletes_baseline(self):
        rows = {'sources': [{'id': 'synthetic:base', 'title': 'Synthetic 1'}, {'id': 'synthetic:new', 'title': 'Synthetic 2'}]}
        blob, trust = archive(rows)
        baseline = {'synthetic:base': 'sources'}
        receipt = receive(blob, trusted_manifest_sha256=trust, trusted_baseline_sha256=BASE, baseline_ids=baseline)
        self.assertEqual(receipt.aggregate()['accepted_rows'], 1)
        self.assertEqual(receipt.aggregate()['quarantined_id_collision'], 1)
        self.assertEqual(baseline, {'synthetic:base': 'sources'})

    def test_bibliographic_duplicate_candidates_are_not_id_conflicts_or_merges(self):
        rows = {'sources': [{'id': 'synthetic:one', 'title': ' Synthetic   Title ', 'doi': 'synthetic:doi'},
                            {'id': 'synthetic:two', 'title': 'synthetic title', 'doi': 'SYNTHETIC:DOI'}]}
        receipt = self.read(rows)
        self.assertEqual(receipt.aggregate()['accepted_rows'], 2)
        self.assertEqual(receipt.aggregate()['quarantined_id_collision'], 0)
        self.assertEqual(receipt.aggregate()['duplicate_title_candidates_within'], 1)
        self.assertEqual(receipt.aggregate()['duplicate_doi_candidates_within'], 1)

    def test_baseline_cross_row_semantics_are_explicitly_pending(self):
        rows = {'locators': [{'id': 'synthetic:loc', 'source_id': 'synthetic:base-source',
                              'edition_id': 'synthetic:base-edition'}]}
        blob, trust = archive(rows)
        receipt = receive(blob, trusted_manifest_sha256=trust, trusted_baseline_sha256=BASE,
                          baseline_ids={'synthetic:base-source': 'sources', 'synthetic:base-edition': 'editions'})
        self.assertEqual(receipt.aggregate()['accepted_rows'], 1)
        self.assertEqual(receipt.aggregate()['baseline_semantics_unverified'], 1)

    def test_unknown_reference_and_wrong_type_are_quarantined(self):
        rows = sample(); rows['claims'][0]['passage_ids'] = ['synthetic:source']
        result = self.read(rows).aggregate()
        self.assertEqual(result['accepted_rows'], 4)
        self.assertEqual(result['quarantined_reference'], 2)

    def test_semantic_edition_source_mismatch_quarantined(self):
        rows = sample(); rows['sources'].append({'id': 'synthetic:other', 'title': 'Synthetic Other'})
        rows['locators'][0]['source_id'] = 'synthetic:other'
        result = self.read(rows).aggregate()
        self.assertEqual(result['quarantined_reference'], 3)
        self.assertEqual(result['accepted_rows'], 4)

    def test_evidence_may_cite_different_valid_source(self):
        rows = sample()
        rows['sources'].append({'id': 'synthetic:other', 'title': 'Synthetic Other'})
        rows['editions'].append({'id': 'synthetic:other-ed', 'source_id': 'synthetic:other'})
        rows['locators'].append({'id': 'synthetic:other-loc', 'source_id': 'synthetic:other', 'edition_id': 'synthetic:other-ed'})
        rows['evidence'][0]['locator_id'] = 'synthetic:other-loc'
        result = self.read(rows).aggregate()
        self.assertEqual(result['accepted_rows'], 9)
        self.assertEqual(result['quarantined_reference'], 0)

    def test_unknown_corpus_and_malformed_rights_quarantined_separately(self):
        rows = sample()
        rows['passages'].append({'id': 'synthetic:other', 'corpus': 'other', 'scheme': 'synthetic', 'reference': 'Synthetic 1'})
        rows['rights'] = [{'id': 'synthetic:right', 'action': ['invalid'], 'decision': 'allowed', 'source_id': 'synthetic:source'}]
        result = self.read(rows).aggregate()
        self.assertEqual(result['accepted_rows'], 6)
        self.assertEqual(result['quarantined_schema'], 2)

    def test_relation_endpoint_dialects_and_ambiguous_mapping(self):
        rows = sample()
        rows['claims'].append({'id': 'synthetic:claim2', 'source_locator_id': 'synthetic:locator', 'passage_ids': ['synthetic:passage']})
        rows['relationships'] = [
            {'id': 'synthetic:r1', 'relation_type': 'contrast',
             'from_claim_id': 'synthetic:claim', 'to_claim_id': 'synthetic:claim2'},
            {'id': 'synthetic:r2', 'relation_type': 'contrasts',
             'subject_id': 'synthetic:claim', 'object_id': 'synthetic:claim2'},
            {'id': 'synthetic:r3', 'relation_type': 'rebuts',
             'from_claim_id': 'synthetic:claim', 'to_claim_id': 'synthetic:claim',
             'subject_id': 'synthetic:claim', 'object_id': 'synthetic:claim'},
        ]
        result = self.read(rows).aggregate()
        self.assertEqual(result['accepted_rows'], 9)
        self.assertEqual(result['quarantined_reference'], 1)

    def test_traversal_and_unlisted_members_rejected(self):
        for extra in ('../synthetic', 'unlisted.txt', '/synthetic', 'records\\synthetic'):
            blob, trust = archive(extra=extra)
            with self.assertRaisesRegex(ReceiptError, '^archive_invalid$'):
                receive(blob, trusted_manifest_sha256=trust, trusted_baseline_sha256=BASE, baseline_ids={})

    def test_malformed_version_schema_and_zip_rejected_without_data(self):
        for version in ('D0', '../synthetic', 'D14\n', 'D9999999'):
            blob, trust = archive(version=version)
            with self.assertRaisesRegex(ReceiptError, '^archive_invalid$'):
                receive(blob, trusted_manifest_sha256=trust, trusted_baseline_sha256=BASE, baseline_ids={})
        with self.assertRaisesRegex(ReceiptError, '^archive_invalid$'):
            receive(b'synthetic sentinel', trusted_manifest_sha256='0' * 64, trusted_baseline_sha256=BASE, baseline_ids={})

    def test_limits_and_opaque_repr_and_defensive_copy(self):
        blob, trust = archive()
        with patch('k3_bridge.receipt.MAX_ARCHIVE', 5):
            with self.assertRaisesRegex(ReceiptError, '^archive_invalid$'):
                receive(blob, trusted_manifest_sha256=trust, trusted_baseline_sha256=BASE, baseline_ids={})
        result = self.read()
        self.assertNotIn('synthetic:', repr(result))
        self.assertNotIn('synthetic:', str(result.aggregate()))
        result.accepted_records('sources')[0]['id'] = 'changed'
        self.assertEqual(result.accepted_records('sources')[0]['id'], 'synthetic:source')

    def test_large_increment_accepts_unique_rows_without_quadratic_scan(self):
        rows = {'sources': [{'id': 'synthetic:item:' + str(i), 'title': 'Synthetic ' + str(i)} for i in range(100_000)]}
        result = self.read(rows)
        self.assertEqual(result.aggregate()['input_rows'], 100_000)
        self.assertEqual(result.aggregate()['accepted_rows'], 100_000)
        self.assertEqual(result.aggregate()['quarantined_reference'], 0)


if __name__ == '__main__':
    unittest.main()
