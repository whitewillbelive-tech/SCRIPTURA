"""Gate I-1 contract and adversarial tests; no research data is used."""
import copy
import csv
import hashlib
import io
import zipfile
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tests')]
from i1_synthetic_factory import build_archive, synthetic_edges, synthetic_coverage
from s1b2_synthetic_factory import synthetic_rows, TABLES
from d3_bridge.validator import validate_archive


class I1SyntheticValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='scriptura-i1-synthetic-')
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'fiction-d3.zip'
        self.base=synthetic_rows(12)
        self.delta={table:[] for table in TABLES}
        self.edges=synthetic_edges()
        self.coverage=synthetic_coverage()

    def check(self, *, expected_sha=None, expected_baseline=None, expected_counts=None,
              mutate_files=None, mutate_manifest=None, extra_entries=None, allow_synthetic=False):
        sha,base_sha,counts=build_archive(self.path,base_rows=self.base,delta_rows=self.delta,
            edges=self.edges,coverage=self.coverage,mutate_files=mutate_files,
            mutate_manifest=mutate_manifest,extra_entries=extra_entries)
        return validate_archive(self.path,expected_sha256=expected_sha or sha,
            expected_baseline_sha256=expected_baseline or base_sha,
            expected_counts=expected_counts or counts,expected_manifest_count=69,
            allow_synthetic=allow_synthetic)

    def test_valid_archive_preserves_baseline_and_keeps_content_private(self):
        before=None
        report,records=self.check()
        before=self.path.read_bytes()
        self.assertEqual(report.get('status'),'pass',report)
        self.assertEqual(len(records['sources']),12)
        self.assertEqual(len(records['bibliographic_edges']),11)
        self.assertEqual(len(records['coverage']),80)
        self.assertEqual(self.path.read_bytes(),before)
        self.assertNotIn('Fictional source',json.dumps(report,ensure_ascii=False))
        self.assertNotIn('src:synthetic-',json.dumps(report,ensure_ascii=False))
        self.assertNotIn('example.invalid',json.dumps(report,ensure_ascii=False))
        self.assertTrue(all(r.get('disposition')=='quarantined' for r in records['claims']))

    def test_validation_does_not_modify_input_archive(self):
        sha,base_sha,counts=build_archive(self.path,base_rows=self.base,delta_rows=self.delta,edges=self.edges,coverage=self.coverage)
        before=self.path.read_bytes()
        report,_=validate_archive(self.path,expected_sha256=sha,expected_baseline_sha256=base_sha,expected_counts=counts,expected_manifest_count=69)
        self.assertEqual(report['status'],'pass',report)
        self.assertEqual(self.path.read_bytes(),before)

    def test_outer_pin_and_nested_d2_pin_are_independently_enforced(self):
        report,_=self.check(expected_sha='0'*64)
        self.assertNotEqual(report['status'],'pass')
        report,_=self.check(expected_baseline='0'*64)
        self.assertNotEqual(report['status'],'pass')

    def test_baseline_records_must_equal_nested_d2_exactly(self):
        def mutate(files):files['baseline/records/sources.jsonl']+=b' \n'
        report,_=self.check(mutate_files=mutate)
        self.assertNotEqual(report['status'],'pass')

    def test_baseline_plus_delta_must_equal_d3_merged(self):
        def mutate(files):files['d3/records_delta/sources.jsonl']=b'{"id":"fake"}\n'
        report,_=self.check(mutate_files=mutate)
        self.assertNotEqual(report['status'],'pass')

    def test_hash_list_integrity_and_manifest_count_are_enforced(self):
        def bad_hash(lines):lines[0]='0'*64+lines[0][64:]
        report,_=self.check(mutate_manifest=bad_hash)
        self.assertNotEqual(report['status'],'pass')
        def missing(lines):lines.pop()
        report,_=self.check(mutate_manifest=missing)
        self.assertNotEqual(report['status'],'pass')

    def test_bad_row_counts_and_duplicate_global_id_rejected(self):
        expected={t:len(self.base[t]) for t in TABLES};expected['claims']+=1
        report,_=self.check(expected_counts=expected)
        self.assertNotEqual(report['status'],'pass')
        other=copy.deepcopy(self.base['sources'][0]);self.delta['sources'].append(other)
        report,_=self.check()
        self.assertNotEqual(report['status'],'pass')

    def test_doi_normalization_finds_duplicate(self):
        record=copy.deepcopy(self.base['sources'][0]);record['id']='src:fiction-duplicate';record['doi']='https://doi.org/10.99999/FICTION-0'
        self.delta['sources'].append(record)
        report,_=self.check()
        self.assertNotEqual(report['status'],'pass')

    def test_edition_to_missing_source_is_rejected(self):
        self.delta['editions'].append({'id':'ed:bad','source_id':'src:missing','label':'fiction','language':'en','version_status':'partial'})
        report,_=self.check()
        self.assertNotEqual(report['status'],'pass')

    def test_duplicate_and_missing_rights_are_rejected(self):
        duplicate=copy.deepcopy(self.base['rights'][0]);duplicate['id']='right:duplicate'
        self.delta['rights'].append(duplicate)
        report,_=self.check()
        self.assertNotEqual(report['status'],'pass')
        self.delta['rights'].clear();self.base['rights'].pop()
        report,_=self.check()
        self.assertNotEqual(report['status'],'pass')

    def test_unknown_and_conditional_are_never_granted(self):
        self.base['rights'][0]['decision']='conditional'
        report,records=self.check()
        self.assertEqual(report['status'],'pass',report)
        for rec in records['rights']:
            self.assertFalse(rec.get('rights',{}).get('effective_allowed',False))

    def test_synthetic_or_raw_content_cannot_be_mixed_with_research(self):
        self.base['sources'][0]['data_class']='synthetic'
        report,_=self.check()
        self.assertNotEqual(report['status'],'pass')
        del self.base['sources'][0]['data_class']
        self.base['sources'][0]['raw_text']='SYNTHETIC DO NOT RETURN'
        report,_=self.check()
        self.assertNotEqual(report['status'],'pass')
        self.assertNotIn('SYNTHETIC DO NOT RETURN',json.dumps(report))

    def test_verified_claim_requires_provenance_and_never_implies_scholarly_review(self):
        self.base['claims'][0]['review_status']='source_verified'
        report,_=self.check()
        self.assertNotEqual(report['status'],'pass')
        self.base['locators'][0].update(verification_status='source_checked',checked_at='2026-01-01T00:00:00Z')
        self.base['evidence'][0]['review_status']='verified'
        self.base['reviews'][0]['decision']='source_verified'
        report,records=self.check()
        self.assertEqual(report['status'],'pass',report)
        self.assertEqual(records['claims'][0]['data']['review_status'],'source_verified')
        self.assertNotEqual(records['claims'][0]['data']['review_status'],'scholarly_reviewed')

    def test_bibliographic_edges_do_not_accept_missing_source_or_argument_type(self):
        self.edges[0]['to_source_id']='src:missing'
        report,_=self.check()
        self.assertNotEqual(report['status'],'pass')
        self.edges=synthetic_edges();self.edges[0]['relation_type']='rebuts'
        report,_=self.check()
        self.assertNotEqual(report['status'],'pass')

    def test_bibliographic_edge_locator_must_belong_to_citing_source(self):
        self.edges[0]['from_source_id']='src:synthetic-2'
        report,_=self.check()
        self.assertNotEqual(report['status'],'pass')

    def test_bibliographic_edges_require_unique_id_and_exact_count(self):
        self.edges[1]['id']=self.edges[0]['id']
        report,_=self.check()
        self.assertNotEqual(report['status'],'pass')
        self.edges=synthetic_edges()[:-1]
        report,_=self.check()
        self.assertNotEqual(report['status'],'pass')

    def test_coverage_count_and_listing_enums_are_checked(self):
        self.coverage=synthetic_coverage()
        self.coverage.pop()
        report,_=self.check()
        self.assertNotEqual(report['status'],'pass')
        self.coverage=synthetic_coverage();self.coverage[0]['opc_wcf_listing_status']='verified_all_traditions'
        report,_=self.check()
        self.assertNotEqual(report['status'],'pass')

    def test_coverage_csv_and_json_agree(self):
        def tamper(files):
            name='d3/coverage/CANON_COVERAGE_D3_FINAL.csv'
            files[name]=files[name].replace(b'not_recorded',b'partial',1)
        report,_=self.check(mutate_files=tamper)
        self.assertNotEqual(report['status'],'pass')

    def test_csv_missing_or_duplicate_headers_are_rejected(self):
        for name, field in (('d3/D3_RIGHTS_MATRIX.csv','decision'),('d3/coverage/CANON_COVERAGE_D3_FINAL.csv','opc_wcf_listing_status')):
            with self.subTest(name=name):
                def tamper(files):
                    rows=list(csv.reader(io.StringIO(files[name].decode('utf8'))))
                    index=rows[0].index(field)
                    for row in rows: row.pop(index)
                    out=io.StringIO(newline='');csv.writer(out,lineterminator='\n').writerows(rows)
                    files[name]=out.getvalue().encode('utf8')
                report,_=self.check(mutate_files=tamper)
                self.assertNotEqual(report['status'],'pass')
                def duplicate(files):
                    rows=list(csv.reader(io.StringIO(files[name].decode('utf8'))))
                    index=rows[0].index(field)
                    for row in rows:row.insert(index,row[index])
                    out=io.StringIO(newline='');csv.writer(out,lineterminator='\n').writerows(rows)
                    files[name]=out.getvalue().encode('utf8')
                report,_=self.check(mutate_files=duplicate)
                self.assertNotEqual(report['status'],'pass')

    def test_csv_extra_or_missing_row_values_are_rejected(self):
        for name in ('d3/D3_RIGHTS_MATRIX.csv','d3/coverage/CANON_COVERAGE_D3_FINAL.csv'):
            for mode in ('extra','extra_empty','missing'):
                with self.subTest(name=name,mode=mode):
                    def tamper(files):
                        rows=list(csv.reader(io.StringIO(files[name].decode('utf8'))))
                        if mode=='extra': rows[1].append('unexpected synthetic value')
                        elif mode=='extra_empty': rows[1].append('')
                        else: rows[1].pop()
                        out=io.StringIO(newline='');csv.writer(out,lineterminator='\n').writerows(rows)
                        files[name]=out.getvalue().encode('utf8')
                    report,_=self.check(mutate_files=tamper)
                    self.assertNotEqual(report['status'],'pass')

    def test_rights_matrix_provenance_must_match_records(self):
        name='d3/D3_RIGHTS_MATRIX.csv'
        for field in ('record_origin','source_id','source_title','edition_label'):
            with self.subTest(field=field):
                def tamper(files):
                    data=io.StringIO(files[name].decode('utf8'),newline='')
                    reader=csv.DictReader(data);header=reader.fieldnames;rows=list(reader)
                    rows[0][field]='fictional-mismatched-value'
                    out=io.StringIO(newline='');writer=csv.DictWriter(out,fieldnames=header,lineterminator='\n')
                    writer.writeheader();writer.writerows(rows)
                    files[name]=out.getvalue().encode('utf8')
                report,_=self.check(mutate_files=tamper)
                self.assertNotEqual(report['status'],'pass')
                self.assertIn('rights_csv_provenance_mismatch',report['errors'])

    def test_rights_matrix_csv_cannot_disagree_with_json_decision(self):
        def tamper(files):
            name='d3/D3_RIGHTS_MATRIX.csv'
            files[name]=files[name].replace(b',unknown,',b',allowed,',1)
        report,_=self.check(mutate_files=tamper)
        self.assertNotEqual(report['status'],'pass')

    def test_coverage_listing_sources_must_be_valid_urls(self):
        self.coverage[0]['citation_sources']['opc']='not a source location'
        report,_=self.check()
        self.assertNotEqual(report['status'],'pass')

    def test_coverage_reference_total_must_match_actual_passages(self):
        self.coverage[0]['d3_merged_passage_records'] = 99
        report,_=self.check()
        self.assertNotEqual(report['status'],'pass')

    def test_checked_bibliographic_claim_without_checked_locator_is_rejected(self):
        self.edges[0]['review_status'] = 'source_checked'
        report,_=self.check()
        self.assertNotEqual(report['status'],'pass')

    def test_rights_matrix_csv_must_preserve_scope(self):
        self.base['rights'][0]['purpose']='synthetic-research-only'
        def tamper(files):
            name='d3/D3_RIGHTS_MATRIX.csv'
            files[name]=files[name].replace(b'synthetic-research-only',b'commercial-public',1)
        report,_=self.check(mutate_files=tamper)
        self.assertNotEqual(report['status'],'pass')

    def test_coverage_work_counts_cannot_be_swapped_while_totals_stay_same(self):
        self.coverage[0]['d3_merged_passage_records']=0
        self.coverage[0]['d3_address_coverage']='not_recorded'
        self.coverage[1]['d3_merged_passage_records']=2
        self.coverage[1]['d3_address_coverage']='partial'
        report,_=self.check()
        self.assertNotEqual(report['status'],'pass')

    def test_auxiliary_original_text_and_synthetic_mixture_are_rejected(self):
        self.edges[0]['full_text']='SYNTHETIC NO OUTPUT'
        report,_=self.check()
        self.assertNotEqual(report['status'],'pass')
        self.assertNotIn('SYNTHETIC NO OUTPUT',json.dumps(report))
        self.edges=synthetic_edges();self.coverage[0]['is_synthetic']=True
        report,_=self.check()
        self.assertNotEqual(report['status'],'pass')

    def test_bibliographic_prior_origin_and_scope_are_required(self):
        for field in ('prior_origin','relation_scope'):
            with self.subTest(field=field):
                self.edges=synthetic_edges();self.edges[0][field]='   '
                report,_=self.check()
                self.assertNotEqual(report['status'],'pass')

    def test_missing_citation_edge_date_is_quarantined_individually(self):
        self.base['locators'][0].update(verification_status='source_checked',checked_at='2026-01-01T00:00:00Z')
        self.edges[0]['review_status']='source_checked'
        self.edges[0].pop('checked_at',None)
        report,records=self.check()
        self.assertEqual(report['status'],'pass',report)
        edge=records['bibliographic_edges'][0]
        self.assertEqual(edge['disposition'],'quarantined')
        self.assertIn('source_checked_edge_date_missing',edge['reasons'])
        self.assertFalse(report['bibliography']['claim_relation_conversion'])

    def test_nested_d2_excessive_compression_is_rejected(self):
        nested_hash=[]
        def mutate(files):
            name='baseline/SCRIPTURA_D11_D2_RESEARCH.zip'
            buffer=io.BytesIO(files[name])
            with zipfile.ZipFile(buffer,'a',compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr('synthetic/compression-bomb.txt',b'X'*(2*1024*1024))
            files[name]=buffer.getvalue();nested_hash.append(hashlib.sha256(files[name]).hexdigest())
        sha,_,counts=build_archive(self.path,base_rows=self.base,delta_rows=self.delta,edges=self.edges,coverage=self.coverage,mutate_files=mutate)
        report,_=validate_archive(self.path,expected_sha256=sha,expected_baseline_sha256=nested_hash[0],expected_counts=counts,expected_manifest_count=69)
        self.assertNotEqual(report['status'],'pass')

    def test_nested_d2_duplicate_member_is_not_accepted_even_with_matching_pin(self):
        nested_hash=[]
        def mutate(files):
            name='baseline/SCRIPTURA_D11_D2_RESEARCH.zip'
            buffer=io.BytesIO(files[name])
            with zipfile.ZipFile(buffer,'a') as archive:archive.writestr('RUN_MANIFEST.json',b'{}')
            files[name]=buffer.getvalue();nested_hash.append(hashlib.sha256(files[name]).hexdigest())
        sha,_,counts=build_archive(self.path,base_rows=self.base,delta_rows=self.delta,edges=self.edges,coverage=self.coverage,mutate_files=mutate)
        report,_=validate_archive(self.path,expected_sha256=sha,expected_baseline_sha256=nested_hash[0],expected_counts=counts,expected_manifest_count=69)
        self.assertNotEqual(report['status'],'pass')

    def test_duplicate_or_unsafe_zip_member_is_rejected(self):
        report,_=self.check(extra_entries=[('../fiction-escape.txt',b'fake')])
        self.assertNotEqual(report['status'],'pass')
        report,_=self.check(extra_entries=[('logs/FILE_SHA256SUMS.txt',b'')])
        self.assertNotEqual(report['status'],'pass')

    def test_manifest_not_covering_extra_member_fails(self):
        report,_=self.check(extra_entries=[('synthetic/unlisted.txt',b'fake')])
        self.assertNotEqual(report['status'],'pass')


if __name__=='__main__':unittest.main()
