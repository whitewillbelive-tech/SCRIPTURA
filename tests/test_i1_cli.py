"""Safety and private-trace behaviour of the public I-1 CLI, synthetic only."""
import json
import io
from contextlib import redirect_stdout, redirect_stderr
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tests')]
import i1_bridge_cli as cli
from i1_synthetic_factory import build_archive


class I1CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='scriptura-i1-cli-')
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)

    def test_private_trace_preserves_reference_ids_without_source_text(self):
        records={t:[] for t in ('claims','coverage','bibliographic_edges')}
        records['claims']=[{'data':{'id':'claim:fiction','agent_id':'agent:fiction','statement_ko':'DO NOT COPY FULL TEXT','locator_id':'locator:fiction'}, 'file':'d3/records_merged/claims.jsonl','row_number':1,'sha256':'a'*64,'disposition':'quarantined','reasons':['manual_review']}]
        records['coverage']=[{'data':{'id':'cov:fiction','work_label':'Fictional unit','scope_note':'DO NOT COPY TEXT','citation_sources':{'x':'https://example.invalid/private'}},'file':'d3/coverage/CANON_COVERAGE_D3_FINAL.jsonl','row_number':1,'sha256':'b'*64,'disposition':'quarantined','reasons':['manual_review']}]
        report=cli.private_review(records)
        self.assertEqual(report['rows'][0]['original_id'],'claim:fiction')
        self.assertEqual(report['rows'][0]['reference_ids']['agent_id'],'agent:fiction')
        serialized=json.dumps(report)
        self.assertNotIn('DO NOT COPY',serialized)
        self.assertNotIn('example.invalid',serialized)
        self.assertFalse(report['canonical_promotion'])

    def test_private_trace_keeps_original_status_and_rights_separately(self):
        def entry(data, name):
            return {'data':data,'file':f'd3/records_merged/{name}.jsonl','row_number':1,'sha256':'a'*64,'disposition':'quarantined','reasons':['review_required']}
        records={'claims':[entry({'id':'claim:fiction','review_status':'source_verified','statement_ko':'DO NOT COPY'},'claims')],
                 'rights':[entry({'id':'rights:fiction','edition_id':'edition:fiction','action':'embed','decision':'conditional','scope_note':'PRIVATE TERMS'},'rights')],
                 'reviews':[entry({'id':'review:fiction','decision':'candidate','target_id':'claim:fiction','notes':'PRIVATE NOTES'},'reviews')],
                 'coverage':[]}
        rows=cli.private_review(records)['rows']
        self.assertEqual(rows[0]['original_status'],'source_verified')
        self.assertEqual(rows[1]['rights_decision'],{'action':'embed','decision':'conditional'})
        self.assertEqual(rows[1]['reference_ids']['edition_id'],'edition:fiction')
        self.assertEqual(rows[2]['original_status'],'candidate')
        self.assertNotIn('PRIVATE',json.dumps(rows))
        self.assertNotIn('DO NOT COPY',json.dumps(rows))

    def test_affiliation_coverage_deduplicates_claims_and_never_infers_doctrine(self):
        def item(table,data,row):
            return {'data':data,'file':f'd3/records_merged/{table}.jsonl','row_number':row,'sha256':'c'*64,'disposition':'quarantined','reasons':['review_required']}
        records={'coverage':[],
                 'passages':[item('passages',{'id':'p1','work':'Fictional Work'},1),item('passages',{'id':'p2','work':'Fictional Work'},2)],
                 'affiliations':[item('affiliations',{'id':'a1','agent_id':'agent:fiction','tradition':'Fictional tradition','review_status':'candidate'},1),item('affiliations',{'id':'a2','agent_id':'agent:fiction','tradition':'Fictional tradition','review_status':'candidate'},2),item('affiliations',{'id':'a3','agent_id':'agent:fiction','tradition':'Fictional tradition','review_status':'source_checked'},3)],
                 'claims':[item('claims',{'id':'c1','agent_id':'agent:fiction','passage_ids':['p1','p2'],'review_status':'candidate','attribution_kind':'individual_opinion'},1),item('claims',{'id':'c2','agent_id':'agent:fiction','passage_ids':['p1'],'review_status':'source_verified','attribution_kind':'scholarly_interpretation'},2),item('claims',{'id':'c3','agent_id':'agent:no-affiliation','passage_ids':['p1'],'review_status':'candidate','attribution_kind':'individual_opinion'},3)]}
        report=cli.private_review(records)
        cross=report['affiliation_claim_coverage']
        self.assertEqual(len(cross),4)
        self.assertTrue(all(x['claim_count']==1 for x in cross))
        self.assertEqual({x['claim_status'] for x in cross},{'candidate','source_verified'})
        self.assertEqual({x['affiliation_status'] for x in cross},{'candidate','source_checked'})
        self.assertEqual({x['attribution_kind'] for x in cross},{'individual_opinion','scholarly_interpretation'})
        self.assertNotIn('official_doctrine',json.dumps(cross))
        self.assertIn('do not establish',report['note'])

    def test_private_trace_permissions_and_no_overwrite(self):
        with patch.object(cli,'ROOT',self.path):
            target=cli.write_private('synthetic.json',{'fake':'content'})
            self.assertEqual(stat.S_IMODE(target.stat().st_mode),0o600)
            self.assertEqual(stat.S_IMODE(target.parent.stat().st_mode),0o700)
            with self.assertRaises(FileExistsError):cli.write_private('synthetic.json',{'other':'data'})
            self.assertEqual(json.loads(target.read_text()),{'fake':'content'})

    def test_private_trace_rejects_traversal_and_symlink(self):
        with patch.object(cli,'ROOT',self.path):
            for name in ('../evil.json','/tmp/evil.json','evil.txt'):
                with self.subTest(name=name),self.assertRaises(ValueError):cli.write_private(name,{})
            (self.path/'.local').symlink_to(self.path,target_is_directory=True)
            with self.assertRaises(ValueError):cli.write_private('file.json',{})

    def test_preview_rejects_unpinned_synthetic_zip_without_database_access(self):
        archive=self.path/'fiction.zip';build_archive(archive)
        before=archive.read_bytes()
        env=os.environ.copy();env['DATABASE_URL']='postgresql://fiction@127.0.0.1:1/not_a_database'
        for mode in ('validate','dry-run','ingest-preview'):
            run=subprocess.run([sys.executable,str(ROOT/'scripts/i1_bridge_cli.py'),mode,str(archive)],cwd=self.path,env=env,capture_output=True,text=True,timeout=10)
            self.assertEqual(run.returncode,1,run.stderr)
            report=json.loads(run.stdout)
            self.assertEqual(report['status'],'fail')
            self.assertFalse(report['database_write'])
            self.assertFalse(report['canonical_promotion'])
            self.assertNotIn('Fictional source',run.stdout)
        self.assertEqual(archive.read_bytes(),before)
        self.assertEqual(sorted(p.name for p in self.path.iterdir()),['fiction.zip'])

    def test_quarantine_summary_contains_only_approved_fields(self):
        report={'status':'pass','schema_version':'i1-test','archive_sha256':'a'*64,'baseline_sha256':'b'*64,'dispositions':{'eligible':0,'quarantined':1},'quarantine_reasons':{'manual_review':1},'records':[{'table':'claims','row_number':1,'line_sha256':'c'*64,'disposition':'quarantined','reason_codes':['manual_review']}], 'private_marker':'DO NOT EXPOSE'}
        output=self.path/'quarantine.json'
        with patch.object(cli,'validate_archive',return_value=(report,{})),redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(['dry-run','unused.zip','--quarantine-output',str(output)]),0)
        summary=json.loads(output.read_text())
        self.assertEqual(summary['dispositions']['quarantined'],1)
        self.assertEqual(summary['records'][0]['line_sha256'],'c'*64)
        self.assertFalse(summary['database_write'])
        self.assertFalse(summary['canonical_promotion'])
        self.assertNotIn('DO NOT EXPOSE',output.read_text())

    def test_quarantine_summary_does_not_overwrite_existing_file(self):
        report={'status':'pass','schema_version':'test','archive_sha256':'a'*64,'baseline_sha256':'b'*64,'dispositions':{},'quarantine_reasons':{},'records':[]}
        output=self.path/'preserve.json';output.write_text('preserve')
        with patch.object(cli,'validate_archive',return_value=(report,{})),redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(['dry-run','unused.zip','--quarantine-output',str(output)]),2)
        self.assertEqual(output.read_text(),'preserve')

    def test_failed_validation_never_creates_quarantine_summary(self):
        output=self.path/'must-not-exist.json'
        with patch.object(cli,'validate_archive',return_value=({'status':'fail'},{})),redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(['dry-run','unused.zip','--quarantine-output',str(output)]),1)
        self.assertFalse(output.exists())

    def test_invalid_pinned_input_cannot_create_private_report(self):
        archive=self.path/'fiction.zip';build_archive(archive)
        name='not_created_i1_test.json'
        target=ROOT/'.local'/'i1'/name
        self.assertFalse(target.exists())
        run=subprocess.run([sys.executable,str(ROOT/'scripts/i1_bridge_cli.py'),'ingest-preview',str(archive),'--private-trace',name],cwd=self.path,capture_output=True,text=True,timeout=10)
        self.assertEqual(run.returncode,1)
        self.assertFalse(target.exists())


if __name__=='__main__':unittest.main()
