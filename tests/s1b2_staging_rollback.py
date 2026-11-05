"""Exercise 004 rollback on an EMPTY disposable staging DB, with no real data."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from d2_bridge.staging import _parse_url, TEST_ACK

if os.environ.get('SCRIPTURA_STAGING_APPROVED') != TEST_ACK:
    raise SystemExit('explicit synthetic staging test approval required')
url=os.environ.get('SCRIPTURA_TEST_STAGING_OWNER_URL')
if not url: raise SystemExit('isolated empty owner DB URL required')
cfg=_parse_url(url,staging=True)
env={k:v for k,v in os.environ.items() if not k.upper().startswith('PG')}
env.update({'PGHOST':'127.0.0.1' if cfg['host']=='localhost' else cfg['host'], 'PGPORT':str(cfg['port']), 'PGUSER':cfg['username'], 'PGDATABASE':cfg['database'], 'PGCONNECT_TIMEOUT':'5'})
if cfg['password']: env['PGPASSWORD']=cfg['password']
psql=os.environ.get('SCRIPTURA_TEST_PSQL','psql')
def run(sql):
    return subprocess.run([psql,'-X','-q','-A','-t','-v','ON_ERROR_STOP=1'],input=sql,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,timeout=30,check=False)
def require(condition, label):
    if not condition: raise SystemExit('FAIL: '+label)
    print('PASS: '+label)

up=(ROOT/'db/004_d2_staging.sql').read_text()
down=(ROOT/'db/004_d2_staging.down.sql').read_text()
require(run(up).returncode==0,'004 applies only to an empty staging DB')
require(run('CREATE TABLE scriptura_d2_stage.s1b2_test_guard(id integer);').returncode==0,'create test-owned extra object')
require(run(down).returncode!=0,'rollback refuses additional objects')
r=run("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='scriptura_d2_stage' AND c.relname IN ('snapshots','records','s1b2_test_guard') AND c.relkind='r';")
require(r.returncode==0 and r.stdout.strip()=='3','failed rollback preserves every object')
require(run('DROP TABLE scriptura_d2_stage.s1b2_test_guard;').returncode==0,'remove only the object this test created')
require(run(down).returncode==0,'empty rollback succeeds')
require(run(up).returncode==0,'reapply succeeds')
