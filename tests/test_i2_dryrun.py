"""D4 reception tests: invented archives only, no research data or network."""
import copy
import csv
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tests')]
from i2_d4_factory import build_d4
from i2_bridge.d4 import inspect_archive


class D4DryRunTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='i2-fictional-');self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'fiction-d4.zip'

    def check(self, *, mutate_files=None, mutate_manifest=None, extra_entries=None, pin=None, d3_pin=None, d2_pin=None, counts_delta=None, allow_synthetic=True):
        sha,d3,d2,counts=build_d4(self.path,mutate_files=mutate_files,mutate_manifest=mutate_manifest,extra_entries=extra_entries)
        for table, delta in (counts_delta or {}).items(): counts[table]+=delta
        return inspect_archive(self.path,expected_sha256=pin or sha,expected_d3_sha256=d3_pin or d3,expected_d2_sha256=d2_pin or d2,expected_counts=counts,allow_synthetic=allow_synthetic)

    def test_valid_fixture_is_read_only_and_does_not_promote(self):
        r=self.check();before=self.path.read_bytes()
        self.assertEqual(r['status'],'pass',r['errors']);self.assertEqual(r['manifest_entries'],72)
        self.assertFalse(r['database_write']);self.assertFalse(r['canonical_promotion'])
        self.assertEqual(r['claims']['automatic_authority_adoptions'],0);self.assertEqual(r['claims']['automatic_scholarly_promotions'],0)
        self.assertEqual(r['authority_gaps']['insufficient_evidence'],r['claims']['total']);self.assertEqual(before,self.path.read_bytes())
        text=json.dumps(r,ensure_ascii=False);self.assertNotIn('Fictional source',text);self.assertNotIn('src:synthetic-',text);self.assertNotIn('example.invalid',text)

    def test_frozen_input_and_nested_lineage_hashes_fail_closed(self):
        for kw in ({'pin':'0'*64},{'d3_pin':'0'*64},{'d2_pin':'0'*64}):
            with self.subTest(kw=kw):self.assertEqual(self.check(**kw)['status'],'fail')

    def test_hash_list_and_file_coverage_must_match(self):
        def bad_hash(lines):lines[0]='0'*64+lines[0][64:]
        def missing(lines):lines.pop()
        for fn in (bad_hash,missing):
            with self.subTest(fn=fn.__name__):self.assertEqual(self.check(mutate_manifest=fn)['status'],'fail')

    def test_duplicate_and_traversal_zip_entries_are_rejected(self):
        for entries in ([('../outside',b'fiction')],[('baseline/records/sources.jsonl',b'fiction')]):
            with self.subTest(entries=len(entries)):
                self.assertEqual(self.check(extra_entries=entries)['status'],'fail')

    def test_baseline_bytes_and_delta_merge_are_checked(self):
        def alter_baseline(files):files['baseline/records/sources.jsonl']+=b' \n'
        def alter_delta(files):files['d4/records_delta/claims.jsonl']=b'{"id":"fake"}\n'
        for fn in (alter_baseline,alter_delta):
            with self.subTest(fn=fn.__name__):self.assertEqual(self.check(mutate_files=fn)['status'],'fail')

    def test_bibliographic_records_cannot_become_arguments(self):
        def alter(files):
            k='d4/graph/bibliographic_edges_merged.jsonl'
            files[k]=files[k].replace(b'bibliographic_citation',b'rebuts',1)
        self.assertEqual(self.check(mutate_files=alter)['status'],'fail')

    def test_rights_csv_extra_values_and_evidence_mismatch_rejected(self):
        def alter(files):
            k='d4/D4_RIGHTS_MATRIX.csv';rows=list(csv.reader(io.StringIO(files[k].decode())))
            rows[1].append('fiction');out=io.StringIO(newline='');csv.writer(out,lineterminator='\n').writerows(rows);files[k]=out.getvalue().encode()
        def mismatch(files):
            k='d4/D4_RIGHTS_MATRIX.csv';rows=list(csv.reader(io.StringIO(files[k].decode())))
            rows[1][rows[0].index('decision')]='allowed';out=io.StringIO(newline='');csv.writer(out,lineterminator='\n').writerows(rows);files[k]=out.getvalue().encode()
        for fn in (alter,mismatch):
            with self.subTest(fn=fn.__name__):self.assertEqual(self.check(mutate_files=fn)['status'],'fail')

    def test_missing_or_duplicate_rights_columns_rejected(self):
        def mutate(files):
            k='d4/D4_RIGHTS_MATRIX.csv';rows=list(csv.reader(io.StringIO(files[k].decode())));n=rows[0].index('decision')
            for row in rows:row.pop(n)
            out=io.StringIO(newline='');csv.writer(out,lineterminator='\n').writerows(rows);files[k]=out.getvalue().encode()
        self.assertEqual(self.check(mutate_files=mutate)['status'],'fail')

    def test_coverage_csv_and_individual_work_counts_checked(self):
        def mutate(files):
            k='d4/coverage/CANON_COVERAGE_D4.csv';files[k]=files[k].replace(b'not_recorded',b'partial',1)
        self.assertEqual(self.check(mutate_files=mutate)['status'],'fail')

    def test_all_nine_rights_actions_remain_default_denied(self):
        r=self.check();self.assertEqual(r['status'],'pass',r['errors']);self.assertEqual(len(r['rights']),9)
        for x in r['rights'].values():self.assertEqual(x['effective_allowed'],0)

    def test_original_status_and_authority_axes_do_not_promote(self):
        r=self.check();self.assertEqual(r['status'],'pass',r['errors'])
        self.assertEqual(r['claims']['automatic_authority_adoptions'],0);self.assertEqual(r['claims']['automatic_scholarly_promotions'],0)
        self.assertEqual(set(r['authority_gaps']['axis_absent_or_empty']),{'quotation_status','authority_status','argument_status','independent_review_status'})
        self.assertEqual(r['authority_gaps']['insufficient_evidence'],r['claims']['total'])

    def test_cli_cannot_override_frozen_input_pin(self):
        import subprocess
        self.check()
        proc=subprocess.run([sys.executable,'scripts/i2_d4_dryrun.py',str(self.path)],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(proc.returncode,1);self.assertIn('archive_sha256_mismatch',json.loads(proc.stdout)['errors'])


    def test_doi_duplicates_are_rejected_even_if_delta_and_merged_agree(self):
        def mutate(files):
            base=json.loads(files['baseline/records/sources.jsonl'].splitlines()[0]);base['id']='src:fiction-new';base['doi']='https://doi.org/10.99999/FICTION-0'
            line=(json.dumps(base,sort_keys=True)+'\n').encode();files['d4/records_delta/sources.jsonl']=line;files['d4/records_merged/sources.jsonl']+=line
        r=self.check(mutate_files=mutate,counts_delta={'sources':1});self.assertIn('duplicate_doi',r['errors'])

    def test_missing_foreign_keys_are_rejected(self):
        def mutate(files):
            entry={'id':'edition:fiction-new','source_id':'missing:source','label':'Fiction','language':'en','version_status':'partial'}
            line=(json.dumps(entry,sort_keys=True)+'\n').encode();files['d4/records_delta/editions.jsonl']=line;files['d4/records_merged/editions.jsonl']+=line
        r=self.check(mutate_files=mutate,counts_delta={'editions':1});self.assertIn('reference_missing',r['errors'])

    def test_nested_raw_content_is_rejected_and_never_returned(self):
        def mutate(files):
            base=json.loads(files['baseline/records/sources.jsonl'].splitlines()[0]);base['id']='src:fiction-new';base['doi']='10.99999/unique-new';base['extra']={'raw_text':'PRIVATE FICTION NEVER PRINT'}
            line=(json.dumps(base,sort_keys=True)+'\n').encode();files['d4/records_delta/sources.jsonl']=line;files['d4/records_merged/sources.jsonl']+=line
        r=self.check(mutate_files=mutate,counts_delta={'sources':1});self.assertIn('forbidden_content_field',r['errors']);self.assertNotIn('PRIVATE FICTION NEVER PRINT',json.dumps(r))

    def test_personal_opinion_cannot_become_official_by_label(self):
        def mutate(files):
            entry=json.loads(files['baseline/records/claims.jsonl'].splitlines()[0]);entry['id']='claim:fiction-new';entry['attribution_kind']='official_doctrine'
            line=(json.dumps(entry,sort_keys=True,ensure_ascii=False)+'\n').encode();files['d4/records_delta/claims.jsonl']=line;files['d4/records_merged/claims.jsonl']+=line
        r=self.check(mutate_files=mutate,counts_delta={'claims':1});self.assertIn('official_doctrine_not_institutional',r['errors'])

    def test_source_verified_claim_cannot_bypass_provenance(self):
        def mutate(files):
            entry=json.loads(files['baseline/records/claims.jsonl'].splitlines()[0]);entry['id']='claim:fiction-new';entry['review_status']='source_verified'
            line=(json.dumps(entry,sort_keys=True,ensure_ascii=False)+'\n').encode();files['d4/records_delta/claims.jsonl']=line;files['d4/records_merged/claims.jsonl']+=line
        r=self.check(mutate_files=mutate,counts_delta={'claims':1});self.assertIn('verified_claim_locator_missing',r['errors'])

    def test_consistent_but_incorrect_coverage_count_is_rejected(self):
        def mutate(files):
            jk='d4/coverage/CANON_COVERAGE_D4.jsonl';ck='d4/coverage/CANON_COVERAGE_D4.csv'
            rows=[json.loads(x) for x in files[jk].splitlines() if x.strip()];rows[0]['d4_merged_passage_records']+=1
            files[jk]=''.join(json.dumps(x,sort_keys=True)+'\n' for x in rows).encode()
            csvrows=list(csv.reader(io.StringIO(files[ck].decode())));idx=csvrows[0].index('d4_merged_passage_records');csvrows[1][idx]=str(int(csvrows[1][idx])+1)
            out=io.StringIO(newline='');csv.writer(out,lineterminator='\n').writerows(csvrows);files[ck]=out.getvalue().encode()
        self.assertIn('coverage_work_count_mismatch',self.check(mutate_files=mutate)['errors'])


    def test_bibliographic_id_cannot_collide_with_any_research_record(self):
        def mutate(files):
            base=json.loads(files['baseline/bibliographic_edges.jsonl'].splitlines()[0]);base['id']='src:synthetic-0'
            line=(json.dumps(base,sort_keys=True)+'\n').encode();files['d4/graph/bibliographic_edges_delta.jsonl']=line;files['d4/graph/bibliographic_edges_merged.jsonl']+=line
        self.assertIn('bibliography_id_invalid',self.check(mutate_files=mutate)['errors'])

    def test_source_checked_bibliography_requires_checked_locator(self):
        def mutate(files):
            base=json.loads(files['baseline/bibliographic_edges.jsonl'].splitlines()[0]);base['id']='bib:fiction-extra';base['review_status']='source_checked';base['checked_at']='2026-01-01T00:00:00Z'
            line=(json.dumps(base,sort_keys=True)+'\n').encode();files['d4/graph/bibliographic_edges_delta.jsonl']=line;files['d4/graph/bibliographic_edges_merged.jsonl']+=line
        self.assertIn('bibliography_unchecked_locator',self.check(mutate_files=mutate)['errors'])

    def test_coverage_id_cannot_collide_with_bibliography(self):
        def mutate(files):
            jk='d4/coverage/CANON_COVERAGE_D4.jsonl';ck='d4/coverage/CANON_COVERAGE_D4.csv'
            rows=[json.loads(x) for x in files[jk].splitlines() if x.strip()];rows[0]['id']='bib:fiction-0';files[jk]=''.join(json.dumps(x,sort_keys=True)+'\n' for x in rows).encode()
            c=list(csv.reader(io.StringIO(files[ck].decode())));c[1][c[0].index('id')]='bib:fiction-0';o=io.StringIO(newline='');csv.writer(o,lineterminator='\n').writerows(c);files[ck]=o.getvalue().encode()
        self.assertIn('coverage_id_invalid',self.check(mutate_files=mutate)['errors'])

    def test_coverage_enum_and_citation_url_are_checked(self):
        def invalid_enum(files):
            jk='d4/coverage/CANON_COVERAGE_D4.jsonl';ck='d4/coverage/CANON_COVERAGE_D4.csv'
            rows=[json.loads(x) for x in files[jk].splitlines() if x.strip()];rows[0]['opc_wcf_listing_status']='universal_truth';files[jk]=''.join(json.dumps(x,sort_keys=True)+'\n' for x in rows).encode()
            c=list(csv.reader(io.StringIO(files[ck].decode())));c[1][c[0].index('opc_wcf_listing_status')]='universal_truth';o=io.StringIO(newline='');csv.writer(o,lineterminator='\n').writerows(c);files[ck]=o.getvalue().encode()
        self.assertIn('coverage_status_invalid',self.check(mutate_files=invalid_enum)['errors'])
        def invalid_citation(files):
            jk='d4/coverage/CANON_COVERAGE_D4.jsonl';rows=[json.loads(x) for x in files[jk].splitlines() if x.strip()];rows[0]['citation_sources']={'fiction':'not a URL'};files[jk]=''.join(json.dumps(x,sort_keys=True)+'\n' for x in rows).encode()
        self.assertIn('coverage_source_invalid',self.check(mutate_files=invalid_citation)['errors'])

    def test_research_mode_rejects_explicit_synthetic_record(self):
        def mutate(files):
            base=json.loads(files['baseline/records/sources.jsonl'].splitlines()[0]);base['id']='src:fiction-extra';base['doi']='10.99999/unique-extra';base['data_class']='synthetic'
            line=(json.dumps(base,sort_keys=True)+'\n').encode();files['d4/records_delta/sources.jsonl']=line;files['d4/records_merged/sources.jsonl']+=line
        self.assertIn('synthetic_research_mixture',self.check(mutate_files=mutate,counts_delta={'sources':1},allow_synthetic=False)['errors'])

    def test_malformed_auxiliary_values_fail_without_exception(self):
        def mutate(files):
            base=json.loads(files['baseline/bibliographic_edges.jsonl'].splitlines()[0]);base['id']='bib:fiction-malformed';base['from_source_id']={'unexpected':'type'}
            line=(json.dumps(base,sort_keys=True)+'\n').encode();files['d4/graph/bibliographic_edges_delta.jsonl']=line;files['d4/graph/bibliographic_edges_merged.jsonl']+=line
        r=self.check(mutate_files=mutate);self.assertEqual(r['status'],'fail');self.assertNotIn('unexpected',json.dumps(r))


    def test_coverage_csv_missing_or_duplicate_headers_are_rejected(self):
        for mode in ('missing','duplicate'):
            with self.subTest(mode=mode):
                def mutate(files):
                    key='d4/coverage/CANON_COVERAGE_D4.csv';rows=list(csv.reader(io.StringIO(files[key].decode())));idx=rows[0].index('opc_wcf_listing_status')
                    for row in rows:
                        if mode=='missing':row.pop(idx)
                        else:row.insert(idx,row[idx])
                    out=io.StringIO(newline='');csv.writer(out,lineterminator='\n').writerows(rows);files[key]=out.getvalue().encode()
                self.assertIn('coverage_csv_header_invalid',self.check(mutate_files=mutate)['errors'])


    def test_source_access_cannot_report_raw_content_storage(self):
        def mutate(files):
            event={'id':'event:fiction','source_id':'src:synthetic-0','locators':['loc:synthetic-1'],'observed_at':'2026-01-01T00:00:00Z','full_text_persisted_bytes':1}
            files['d4/SOURCE_ACCESS_LOG.jsonl']=(json.dumps(event)+'\n').encode()
        self.assertIn('source_access_raw_storage_reported',self.check(mutate_files=mutate)['errors'])

    def test_source_access_locator_must_match_source(self):
        def mutate(files):
            event={'id':'event:fiction','source_id':'src:synthetic-1','locators':['loc:synthetic-1'],'observed_at':'2026-01-01T00:00:00Z','full_text_persisted_bytes':0}
            files['d4/SOURCE_ACCESS_LOG.jsonl']=(json.dumps(event)+'\n').encode()
        self.assertIn('source_access_provenance_mismatch',self.check(mutate_files=mutate)['errors'])

    def test_access_observations_cannot_rewrite_baseline_or_claim_review(self):
        def citation(files):
            event={'id':'event:citation','baseline_edge_id':'bib:fiction-0','observed_at':'2026-01-01T00:00:00Z','changes_baseline':True,'independent_human_review':False}
            files['d4/graph/CITATION_ACCESS_EVENTS.jsonl']=(json.dumps(event)+'\n').encode()
        self.assertIn('citation_access_event_invalid',self.check(mutate_files=citation)['errors'])
        def doi(files):
            event={'id':'event:doi','baseline_source_id':'src:synthetic-0','observed_at':'2026-01-01T00:00:00Z','changes_baseline':False,'scholarly_reviewed':True,'full_text_acquired_bytes':0}
            files['d4/graph/DOI_ACCESS_EVENTS.jsonl']=(json.dumps(event)+'\n').encode()
        self.assertIn('doi_access_event_invalid',self.check(mutate_files=doi)['errors'])

    def test_research_unit_claim_count_checked_against_claim_links(self):
        def mutate(files):
            passage=json.loads(files['baseline/records/passages.jsonl'].splitlines()[0]);unit={'passage_id':passage['id'],'work':passage['work'],'reference':passage['reference'],'claim_count':99,'context_count':0,'perspective_contexts':[]}
            files['d4/coverage/D4_RESEARCH_UNIT_COVERAGE.json']=json.dumps([unit]).encode();o=io.StringIO(newline='');w=csv.DictWriter(o,fieldnames=('passage_id','work','reference','claim_count','context_count','perspective_contexts'),lineterminator='\n');w.writeheader();w.writerow(unit);files['d4/coverage/D4_RESEARCH_UNIT_COVERAGE.csv']=o.getvalue().encode()
        self.assertIn('research_unit_count_or_passage_mismatch',self.check(mutate_files=mutate)['errors'])


if __name__=='__main__':unittest.main()
