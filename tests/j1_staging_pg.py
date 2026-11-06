"""J-1 synthetic-only staging guard integration on a disposable local DB.

The only real-derived values sent to PostgreSQL are fixed hashes in deliberately
rejected synthetic metadata rows. No D-7 archive or research record is
opened, transmitted, or stored. This test creates only a generated fixture.
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from d2_bridge.staging import (
    D4_RESEARCH_SHA256, D5_RESEARCH_SHA256, D6_RESEARCH_SHA256, D7_RESEARCH_SHA256,
    StagingError, _connection, _parse_url, action_allowed, stage_synthetic,
)
from s1b2_synthetic_factory import SNAPSHOT, write_archive

OWNER = os.environ.get('SCRIPTURA_TEST_STAGING_OWNER_URL')
WRITER = os.environ.get('SCRIPTURA_STAGING_DATABASE_URL')
if os.environ.get('SCRIPTURA_STAGING_APPROVED') != 'synthetic-test-only' or not OWNER or not WRITER:
    raise SystemExit('explicit synthetic-only acknowledgement and isolated owner/writer URLs required')
owner_cfg, writer_cfg = _parse_url(OWNER, staging=True), _parse_url(WRITER, staging=True)
if (owner_cfg['host_group'],owner_cfg['port'],owner_cfg['database']) != (writer_cfg['host_group'],writer_cfg['port'],writer_cfg['database']) or owner_cfg['username'] == writer_cfg['username']:
    raise SystemExit('owner and writer must be distinct users on the same dedicated test database')
if owner_cfg['database'] != 'scriptura_staging_j1_guard':
    raise SystemExit('J-1 test requires disposable scriptura_staging_j1_guard database')
PSQL = os.environ.get('SCRIPTURA_TEST_PSQL', 'psql')

def psql(sql, *, owner=True):
    cfg = owner_cfg if owner else writer_cfg
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith('PG')}
    env.update({'PGHOST': '127.0.0.1' if cfg['host'] == 'localhost' else cfg['host'],
                'PGPORT': str(cfg['port']), 'PGUSER': cfg['username'],
                'PGDATABASE': cfg['database'], 'PGCONNECT_TIMEOUT': '5'})
    if cfg['password']:
        env['PGPASSWORD'] = cfg['password']
    return subprocess.run([PSQL,'-X','-q','-A','-t','-v','ON_ERROR_STOP=1'], input=sql,
                          text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          env=env, timeout=30, check=False)

class J1StagingPostgresTests(unittest.TestCase):
    def test_01_apply_empty_rollback_and_reapply(self):
        up=(ROOT/'db/008_j1_research_guard.sql').read_text()
        down=(ROOT/'db/008_j1_research_guard.down.sql').read_text()
        for migration in (up, down, up):
            result=psql(migration)
            self.assertEqual(result.returncode, 0, 'empty guard migration sequence failed')
    def test_02_fixed_research_hashes_rejected_by_db(self):
        for index, digest in enumerate((D7_RESEARCH_SHA256,)):
            result=psql("INSERT INTO scriptura_d2_stage.snapshots(snapshot_id,archive_sha256,origin_zip,record_count,metadata_hash) VALUES ('TEST-SYNTHETIC-J1-%d','%s','synthetic.zip',0,'%s')" % (index,digest,'0'*64))
            self.assertNotEqual(result.returncode,0)
            self.assertIn('j1_reject_frozen_d7_archive',result.stderr)
        self.assertEqual(psql('SELECT count(*) FROM scriptura_d2_stage.snapshots').stdout.strip(),'0')
    def test_02b_prior_i3_denylist_remains_in_force(self):
        for index, digest in enumerate((D4_RESEARCH_SHA256,D5_RESEARCH_SHA256,D6_RESEARCH_SHA256)):
            result=psql("INSERT INTO scriptura_d2_stage.snapshots(snapshot_id,archive_sha256,origin_zip,record_count,metadata_hash) VALUES ('TEST-SYNTHETIC-J1-PRIOR-%d','%s','synthetic.zip',0,'%s')" % (index,digest,'0'*64))
            self.assertNotEqual(result.returncode,0)
            self.assertIn('i3_reject_frozen_d4_d5_d6_archives',result.stderr)
        self.assertEqual(psql('SELECT count(*) FROM scriptura_d2_stage.snapshots').stdout.strip(),'0')
    def test_03_internal_api_rejects_known_research_hash_before_file_or_connection(self):
        for digest in (D7_RESEARCH_SHA256,):
            with self.assertRaisesRegex(StagingError,'synthetic_archive_required'):
                stage_synthetic('/does/not/exist', expected_sha256=digest, expected_counts={},
                                expected_snapshot='TEST-SYNTHETIC-J1', psql_bin='/does/not/exist')
    def test_04_invalid_row_rolls_back_synthetic_snapshot_atomically(self):
        # The second statement intentionally violates the record_type constraint.
        result=psql("""BEGIN;
          INSERT INTO scriptura_d2_stage.snapshots(snapshot_id,archive_sha256,origin_zip,record_count,metadata_hash)
          VALUES ('TEST-SYNTHETIC-J1-ATOMIC',repeat('b',64),'synthetic.zip',1,repeat('0',64));
          INSERT INTO scriptura_d2_stage.records(snapshot_id,record_type,record_id,origin_file,row_number,origin_file_sha256,original_sha256,disposition,reasons)
          VALUES ('TEST-SYNTHETIC-J1-ATOMIC','not-a-kind','fake','d2/records_merged/not-a-kind.jsonl',1,repeat('0',64),repeat('0',64),'quarantined',ARRAY[]::text[]);
          COMMIT;""", owner=False)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('records_record_type_check',result.stderr)
        self.assertEqual(psql('SELECT count(*) FROM scriptura_d2_stage.snapshots').stdout.strip(),'0')
        self.assertEqual(psql('SELECT count(*) FROM scriptura_d2_stage.records').stdout.strip(),'0')
    def test_05_generated_synthetic_fixture_and_idempotent_replay(self):
        with tempfile.TemporaryDirectory(prefix='j1-generated-synthetic-') as d:
            path=Path(d)/'synthetic.zip'
            sha,counts=write_archive(path)
            kwargs={'expected_sha256':sha,'expected_counts':counts,'expected_snapshot':SNAPSHOT,'psql_bin':PSQL}
            first=stage_synthetic(path, **kwargs)
            self.assertEqual(stage_synthetic(path, **kwargs),first)
            self.assertFalse(first['canonical_promotion'])
            self.assertFalse(first['payload_stored'])
    def test_06_restricted_writer_cannot_mutate_or_delete(self):
        for statement in ('UPDATE scriptura_d2_stage.records SET disposition=\'eligible\'',
                          'DELETE FROM scriptura_d2_stage.snapshots',
                          'TRUNCATE scriptura_d2_stage.records'):
            result=psql(statement,owner=False)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('permission denied for table',result.stderr)
    def test_07_rights_remain_unknown_and_all_nine_actions_preserved(self):
        result=psql("SELECT count(*),count(DISTINCT rights_action) FROM scriptura_d2_stage.records WHERE record_type='rights' AND rights_decision='unknown'",owner=False)
        self.assertEqual(result.stdout.strip(),'9|9')
    def test_08_nonempty_rollback_refused_and_history_preserved(self):
        before=psql('SELECT count(*) FROM scriptura_d2_stage.records').stdout.strip()
        result=psql((ROOT/'db/008_j1_research_guard.down.sql').read_text())
        self.assertNotEqual(result.returncode,0)
        self.assertIn('rollback refused: staging provenance exists',result.stderr)
        self.assertEqual(psql('SELECT count(*) FROM scriptura_d2_stage.records').stdout.strip(),before)
        self.assertEqual(psql("SELECT count(*) FROM pg_constraint WHERE conrelid='scriptura_d2_stage.snapshots'::regclass AND conname='j1_reject_frozen_d7_archive'").stdout.strip(),'1')
    def test_09_external_archive_cli_input_is_rejected(self):
        result=subprocess.run([sys.executable,str(ROOT/'scripts/stage_synthetic.py'),'/no-input-accepted.zip'],capture_output=True,text=True,timeout=10)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('No input paths or options are accepted',result.stderr)
    def test_10_nonlocal_and_colliding_database_paths_are_rejected(self):
        for invalid in ('postgresql://u@nonlocal.invalid/scriptura_staging_j1_guard',
                        'postgresql://u@127.0.0.1/production',
                        'postgresql://u@127.0.0.1/scriptura_staging_j1_guard?host=elsewhere'):
            with self.assertRaisesRegex(StagingError,'invalid_database_configuration'):
                _parse_url(invalid,staging=True)
        env={'SCRIPTURA_STAGING_APPROVED':'synthetic-test-only',
             'SCRIPTURA_STAGING_DATABASE_URL':WRITER,'DATABASE_URL':OWNER}
        with self.assertRaisesRegex(StagingError,'staging_matches_existing_database'):
            _connection(env)
    def test_11_conditional_and_unknown_rights_are_never_treated_as_permission(self):
        actions=('browse','collect_metadata','store_raw','store_excerpt','index_fulltext',
                 'embed','send_to_model','redistribute','public_link')
        for decision in ('unknown','conditional'):
            for action in actions:
                self.assertFalse(action_allowed({action:decision},action))

if __name__ == '__main__': unittest.main(verbosity=2)
