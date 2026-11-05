import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { spawn, type ChildProcess } from 'node:child_process';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createServer } from 'node:net';
import { DatabaseSync } from 'node:sqlite';

type Fixture = { passages: { id: string; scheme_id: string; external_ref: string }[]; claim_versions: { id: string }[]; claim_passages: { passage_id: string; claim_version_id: string }[]; traditions: { id: string }[] };
let base = '', temp = '', dbPath = '';
let server: ChildProcess;
let fixture: Fixture;
const token = 'test-only-token-local';
const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };
async function json(path: string, options: RequestInit = {}) {
  const response = await fetch(base + '/api/v1/' + path, options);
  return { status: response.status, body: await response.json() };
}
before(async () => {
  fixture = JSON.parse(await readFile('fixtures/demo_valid.json', 'utf8')) as Fixture;
  temp = await mkdtemp(join(tmpdir(), 'scriptura-api-test-'));
  dbPath = join(temp, 'demo.sqlite');
  const probe = createServer();
  await new Promise<void>((resolve, reject) => { probe.once('error', reject); probe.listen(0, '127.0.0.1', resolve); });
  const address = probe.address();
  if (!address || typeof address === 'string') throw new Error('No ephemeral port');
  const port = address.port;
  await new Promise<void>((resolve, reject) => probe.close((error) => error ? reject(error) : resolve()));
  base = `http://127.0.0.1:${port}`;
  server = spawn(process.execPath, ['node_modules/next/dist/bin/next', 'dev', '-H', '127.0.0.1', '-p', String(port)], {
    env: { ...process.env, SCRIPTURA_ADMIN_TOKEN: token, SCRIPTURA_DEMO_DB: dbPath, NEXT_TELEMETRY_DISABLED: '1' }, stdio: 'ignore'
  });
  const deadline = Date.now() + 45000;
  while (Date.now() < deadline) {
    if (server.exitCode !== null) throw new Error(`Server exited: ${server.exitCode}`);
    try { if ((await fetch(base + '/api/v1/passages')).ok) return; } catch { /* wait for startup */ }
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error('API startup timeout');
});
after(async () => {
  if (server && server.exitCode === null) {
    server.kill('SIGTERM');
    await new Promise<void>((resolve) => { server.once('exit', () => resolve()); setTimeout(resolve, 3000).unref(); });
  }
  if (temp) await rm(temp, { recursive: true, force: true });
});

test('기본 조회는 검증되지 않은 주장과 그래프를 숨기고 데모 경고를 포함한다', async () => {
  const link = fixture.claim_passages[0];
  const list = await json(`passages/${encodeURIComponent(link.passage_id)}/interpretations`);
  assert.equal(list.status, 200); assert.deepEqual(list.body.interpretations, []); assert.match(list.body.warning, /합성 데모/);
  assert.equal((await json(`claims/${encodeURIComponent(link.claim_version_id)}`)).status, 404);
  const graph = await json(`graph?passage_id=${encodeURIComponent(link.passage_id)}`);
  assert.deepEqual(graph.body.nodes, []); assert.deepEqual(graph.body.edges, []);
});
test('명시적 미검증 토글에서만 합성 주장과 출처 및 귀속을 조회한다', async () => {
  const link = fixture.claim_passages[0];
  const result = await json(`passages/${encodeURIComponent(link.passage_id)}/interpretations?include_unverified=true`);
  assert.equal(result.status, 200); assert.ok(result.body.interpretations.some((item: { id: string }) => item.id === link.claim_version_id));
  const detail = await json(`claims/${encodeURIComponent(link.claim_version_id)}?include_unverified=true`);
  assert.equal(detail.status, 200); assert.ok(detail.body.claim.attributions.length); assert.ok(detail.body.claim.evidence.length);
  assert.ok(detail.body.claim.evidence[0].source); assert.notEqual(detail.body.claim.review_status, 'source_verified');
});
test('주소 체계와 본문 주소를 함께 검색하며 없는 전통 귀속을 만들어 내지 않는다', async () => {
  const p = fixture.passages[0];
  const list = await json(`passages?scheme_id=${encodeURIComponent(p.scheme_id)}&ref=${encodeURIComponent(p.external_ref)}`);
  assert.equal(list.status, 200); assert.ok(list.body.passages.some((item: { id: string }) => item.id === p.id));
  const wrong = await json(`passages?scheme_id=missing&ref=${encodeURIComponent(p.external_ref)}`);
  assert.deepEqual(wrong.body.passages, []);
  const filtered = await json(`passages/${encodeURIComponent(p.id)}/interpretations?include_unverified=true&tradition_id=${encodeURIComponent(fixture.traditions[0].id)}`);
  assert.deepEqual(filtered.body.interpretations, []);
});
test('관리자 API는 인증되지 않은 읽기 및 쓰기를 거부한다', async () => {
  assert.equal((await json('admin/claims')).status, 401);
  assert.equal((await json('admin/audit', { headers: { Authorization: 'Bearer incorrect' } })).status, 401);
  assert.equal((await json('admin/claims', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ fixture_version_id: fixture.claim_versions[0].id }) })).status, 401);
});
test('관리자 생성은 합성 fixture만 허용하고 외부 원문을 거부한다', async () => {
  const reject = await json('admin/claims', { method: 'POST', headers, body: JSON.stringify({ fixture_version_id: fixture.claim_versions[0].id, full_text: 'unlicensed text' }) });
  assert.equal(reject.status, 400);
  const nonexistent = await json('admin/claims', { method: 'POST', headers, body: JSON.stringify({ fixture_version_id: 'external:unlicensed' }) });
  assert.equal(nonexistent.status, 400);
  const result = await json('admin/claims', { method: 'POST', headers, body: JSON.stringify({ fixture_version_id: fixture.claim_versions[0].id }) });
  assert.equal(result.status, 201); assert.equal(result.body.sample.review_status, 'extracted');
  const list = await json('admin/claims', { headers });
  assert.ok(list.body.samples.some((sample: { id: string }) => sample.id === result.body.sample.id));
  const detail = await json(`admin/claims/${encodeURIComponent(result.body.sample.id)}`, { headers });
  assert.equal(detail.status, 200); assert.equal(detail.body.sample.id, result.body.sample.id);
  assert.equal((await json(`admin/claims/${encodeURIComponent(result.body.sample.id)}`)).status, 401);
});
test('추출, 검수, 승인 이벤트를 보존하고 수정 및 삭제를 거부한다', async () => {
  const created = await json('admin/claims', { method: 'POST', headers, body: JSON.stringify({ fixture_version_id: fixture.claim_versions[0].id }) });
  const id = created.body.sample.id;
  for (const event of ['review', 'approval']) {
    const result = await json('admin/reviews', { method: 'POST', headers, body: JSON.stringify({ sample_id: id, event }) });
    assert.equal(result.status, 201);
  }
  const audit = await json(`admin/audit?entity_id=${encodeURIComponent(id)}`, { headers });
  assert.deepEqual(audit.body.events.map((event: { event: string }) => event.event).sort(), ['approval', 'extraction', 'review']);
  const db = new DatabaseSync(dbPath);
  try {
    assert.throws(() => db.prepare('UPDATE audit SET event = ? WHERE entity_id = ?').run('tampered', id), /append-only/);
    assert.throws(() => db.prepare('DELETE FROM audit WHERE entity_id = ?').run(id), /append-only/);
  } finally { db.close(); }
});
