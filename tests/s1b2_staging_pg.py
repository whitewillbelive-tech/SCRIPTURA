"""Explicit synthetic-only PostgreSQL integration; requires disposable staging DB.

Prerequisites and CI role provisioning: docs/STAGING_SCHEMA.md. This script
never creates a database or accepts a real research archive.
"""
import os
import hashlib
import zipfile
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from d2_bridge.staging import StagingError, _parse_url, stage_synthetic
from s1b2_synthetic_factory import SNAPSHOT, synthetic_rows, write_archive

OWNER = os.environ.get('SCRIPTURA_TEST_STAGING_OWNER_URL')
WRITER = os.environ.get('SCRIPTURA_STAGING_DATABASE_URL')
PSQL = os.environ.get('SCRIPTURA_TEST_PSQL', 'psql')
if not OWNER or not WRITER:
    raise SystemExit('Set SCRIPTURA_TEST_STAGING_OWNER_URL and SCRIPTURA_STAGING_DATABASE_URL for an isolated test DB')
owner_cfg, writer_cfg = _parse_url(OWNER,staging=True), _parse_url(WRITER,staging=True)
if (owner_cfg['host_group'],owner_cfg['port'],owner_cfg['database']) != (writer_cfg['host_group'],writer_cfg['port'],writer_cfg['database']) or owner_cfg['username'] == writer_cfg['username']:
    raise SystemExit('Owner and writer must be different users on the same isolated test DB')


def psql(sql, owner=True):
    cfg = owner_cfg if owner else writer_cfg
    env = {k:v for k,v in os.environ.items() if not k.upper().startswith('PG')}
    env.update({'PGHOST':'127.0.0.1' if cfg['host']=='localhost' else cfg['host'], 'PGPORT':str(cfg['port']), 'PGUSER':cfg['username'], 'PGDATABASE':cfg['database'], 'PGCONNECT_TIMEOUT':'5'})
    if cfg['password']: env['PGPASSWORD']=cfg['password']
    return subprocess.run([PSQL,'-X','-q','-A','-t','-v','ON_ERROR_STOP=1'],input=sql,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,timeout=30,check=False)


class StagingPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='scriptura-staging-test-')
        cls.path = Path(cls.temp.name)/'synthetic.zip'
        cls.sha,cls.counts = write_archive(cls.path)
        cls.env = dict(os.environ,SCRIPTURA_STAGING_APPROVED='synthetic-test-only',SCRIPTURA_STAGING_DATABASE_URL=WRITER)
        cls.params = dict(expected_sha256=cls.sha,expected_counts=cls.counts,expected_snapshot=SNAPSHOT,env=cls.env,psql_bin=PSQL)
        cls.first = stage_synthetic(cls.path,**cls.params)

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def test_01_repeat_is_idempotent_and_keeps_record_counts(self):
        self.assertEqual(stage_synthetic(self.path,**self.params), self.first)
        r=psql('SELECT count(*) FROM scriptura_d2_stage.snapshots; SELECT count(*) FROM scriptura_d2_stage.records;',False)
        self.assertEqual(r.returncode,0)
        self.assertEqual(r.stdout.strip().splitlines(), ['1',str(sum(self.counts.values()))])

    def test_02_all_nine_rights_and_source_hashes_are_preserved_without_payload(self):
        r=psql("SELECT count(*) FROM scriptura_d2_stage.records WHERE record_type='rights' AND rights_decision='unknown'; SELECT count(*) FROM scriptura_d2_stage.records WHERE length(origin_file_sha256)=64 AND length(original_sha256)=64; SELECT count(*) FROM information_schema.columns WHERE table_schema='scriptura_d2_stage' AND column_name IN ('payload','raw_text','full_text','embedding');",False)
        self.assertEqual(r.returncode,0)
        self.assertEqual(r.stdout.strip().splitlines(), ['9',str(sum(self.counts.values())),'0'])
        with zipfile.ZipFile(self.path) as z:
            raw = z.read('d2/records_merged/sources.jsonl')
        expected_file_hash = hashlib.sha256(raw).hexdigest()
        expected_line_hash = hashlib.sha256(raw.splitlines(keepends=True)[0]).hexdigest()
        provenance = psql("SELECT origin_file_sha256,original_sha256 FROM scriptura_d2_stage.records WHERE record_type='sources' AND row_number=1;",False)
        self.assertEqual(provenance.returncode,0)
        self.assertEqual(provenance.stdout.strip(),expected_file_hash+'|'+expected_line_hash)

    def test_03_changed_archive_same_snapshot_fails_without_partial_write(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'synthetic.zip'; rows=synthetic_rows(); rows['sources'][0]['title']='Different fictional test'
            sha,counts=write_archive(path,rows)
            with self.assertRaisesRegex(StagingError,'staging_transaction_rejected'):
                stage_synthetic(path,expected_sha256=sha,expected_counts=counts,expected_snapshot=SNAPSHOT,env=self.env,psql_bin=PSQL)
        r=psql('SELECT count(*) FROM scriptura_d2_stage.snapshots; SELECT count(*) FROM scriptura_d2_stage.records;',False)
        self.assertEqual(r.stdout.strip().splitlines(),['1',str(sum(self.counts.values()))])

    def test_04_owner_and_unrestricted_roles_are_rejected(self):
        with self.assertRaisesRegex(StagingError,'staging_transaction_rejected'):
            stage_synthetic(self.path,**(self.params | {'env':self.env | {'SCRIPTURA_STAGING_DATABASE_URL':OWNER}}))

    def test_05_immutable_provenance_and_nonempty_rollback_refused(self):
        self.assertNotEqual(psql("UPDATE scriptura_d2_stage.records SET disposition='eligible';").returncode,0)
        self.assertNotEqual(psql((ROOT/'db/004_d2_staging.down.sql').read_text()).returncode,0)
        self.assertEqual(psql('SELECT count(*) FROM scriptura_d2_stage.snapshots;').stdout.strip(),'1')

if __name__ == '__main__': unittest.main(verbosity=2)
