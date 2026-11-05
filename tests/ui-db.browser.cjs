// Browser-to-HTTP-to-PostgreSQL integration; requires an isolated synthetic seed DB.
const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const base = process.env.SCRIPTURA_TEST_URL || 'http://127.0.0.1:3107';
let browser, page;
const requests = [];
before(async () => {
  browser = await chromium.launch({ headless: true, executablePath: process.env.CHROMIUM_PATH || undefined, args: ['--no-sandbox'] });
  page = await browser.newPage();
  page.on('request', request => { if (request.url().includes('/api/v1/')) requests.push(request.url()); });
  await page.goto(base + '/explore', { waitUntil: 'networkidle' });
});
after(async () => { if (browser) await browser.close(); });
test('실제 자료 기본 선택은 합성 데이터를 혼합하지 않는다', async () => {
  assert.equal(await page.locator('#data-mode').inputValue(), 'research');
  assert.equal(await page.title(), 'SCRIPTURA | 연구 자료 탐색');
  assert.ok(await page.getByText('연구 자료 탐색 · 검증과 권리 상태를 개별 확인해 주세요').isVisible());
  assert.equal(await page.getByText('가상 연구자 A').count(), 0);
});
test('명시한 합성 모드는 경고와 PostgreSQL 주소 체계를 표시한다', async () => {
  await page.locator('#data-mode').selectOption('synthetic');
  await page.getByText('합성 테스트 / 실제 학술 데이터 아님').waitFor();
  await page.locator('#scheme option[value=\"ref:osis-demo\"]').waitFor({ state: 'attached' });
  await page.locator('#db-passage option[value=\"psg:isa714\"]').waitFor({ state: 'attached' });
  assert.ok(requests.some(u => u.includes('dataset=database') && u.includes('data_mode=synthetic')));
  await page.getByText('표시할 주장이 없습니다').waitFor();
  assert.equal(await page.getByText('표시할 주장이 없습니다').count(), 1);
});
test('검증 대기 토글에서만 합성 주장과 출처·관계 상태를 표시한다', async () => {
  await page.getByLabel('검증 대기 자료 포함').check();
  await page.getByText('2개의 주장').waitFor();
  assert.ok(await page.getByText('가상의 연구 메모 A — 실제로 존재하지 않는 문헌', { exact: true }).isVisible());
  assert.ok(await page.getByText('저장 정책: metadata_only / 권리: unknown').isVisible());
  assert.ok((await page.getByText(/qualifies · 확정되지 않음/).count()) > 0);
  assert.ok((await page.getByText(/uncertain · 확정되지 않음/).count()) > 0);
  assert.ok((await page.getByText(/quotes · 확정되지 않음/).count()) > 0);
  assert.ok((await page.getByText(/출처 위치:/).count()) > 0);
});
test('연구자와 주소 검색 필터가 DB 결과를 좁힌다', async () => {
  await page.locator('#agent').selectOption('agt:demo-a');
  await page.getByText('1개의 주장').waitFor();
  assert.ok(await page.getByText(/당대 배경을 가장 먼저/).first().isVisible());
  await page.locator('#agent').selectOption('');
  await page.locator('#reference').fill('Matt.1.23');
  await page.getByRole('button', { name: '검색', exact: true }).click();
  await page.locator('#db-passage option[value=\"psg:mat123\"]').waitFor({ state: 'attached' });
  await page.getByText('0개의 주장').waitFor();
});
