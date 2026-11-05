"""Reproduce additive I-1 guard tests on an empty, dedicated test database.

The frozen D-3 hash alone is used in a rejected SQL statement; no research data
is read or sent to PostgreSQL. Leaves 004 and 005 applied on successful exit.
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from d2_bridge.staging import D3_RESEARCH_SHA256, TEST_ACK, _parse_url

if os.environ.get('SCRIPTURA_STAGING_APPROVED') != TEST_ACK:
    raise SystemExit('explicit synthetic staging test approval required')
url = os.environ.get('SCRIPTURA_TEST_STAGING_OWNER_URL')
if not url:
    raise SystemExit('isolated empty owner DB URL required')
cfg = _parse_url(url, staging=True)
env = {k: v for k, v in os.environ.items() if not k.upper().startswith('PG')}
env.update({'PGHOST': '127.0.0.1' if cfg['host'] == 'localhost' else cfg['host'],
            'PGPORT': str(cfg['port']), 'PGUSER': cfg['username'],
            'PGDATABASE': cfg['database'], 'PGCONNECT_TIMEOUT': '5'})
if cfg['password']:
    env['PGPASSWORD'] = cfg['password']
psql = os.environ.get('SCRIPTURA_TEST_PSQL', 'psql')

def run(sql):
    return subprocess.run([psql, '-X', '-q', '-A', '-t', '-v', 'ON_ERROR_STOP=1'],
                          input=sql, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          env=env, timeout=30, check=False)

def require(ok, label):
    if not ok:
        raise SystemExit('FAIL: ' + label)
    print('PASS: ' + label)

up = (ROOT / 'db/005_i1_research_guard.sql').read_text()
down = (ROOT / 'db/005_i1_research_guard.down.sql').read_text()
require(run(up).returncode == 0, '005 applies to isolated 004 staging schema')
# D-3 hash is the only real-derived input; the rejected fake row never persists.
insert = "INSERT INTO scriptura_d2_stage.snapshots(snapshot_id,archive_sha256,origin_zip,record_count,metadata_hash) VALUES ('TEST-SYNTHETIC-I1', '%s', 'synthetic.zip', 0, '%s');" % (D3_RESEARCH_SHA256, '0' * 64)
require(run(insert).returncode != 0, 'frozen D3 archive hash rejected by database')
r = run('SELECT count(*) FROM scriptura_d2_stage.snapshots;')
require(r.returncode == 0 and r.stdout.strip() == '0', 'failed D3 write leaves no record')
require(run(down).returncode == 0, '005 rollback succeeds when staging is empty')
require(run(up).returncode == 0, '005 can be reapplied')
# Only a generated synthetic hash is written and committed here, in a disposable DB.
insert_synthetic = insert.replace(D3_RESEARCH_SHA256, 'a' * 64)
require(run(insert_synthetic).returncode == 0, 'synthetic metadata can be staged')
require(run(down).returncode != 0, '005 rollback refuses existing synthetic history')
r = run('SELECT count(*) FROM scriptura_d2_stage.snapshots;')
require(r.returncode == 0 and r.stdout.strip() == '1', 'failed rollback preserves synthetic history')
