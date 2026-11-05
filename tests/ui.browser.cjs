// Run with the demo server already listening; see README for prerequisites.
const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const url = process.env.SCRIPTURA_TEST_URL || 'http://127.0.0.1:3107';
let browser, page;

before(async () => {
  browser = await chromium.launch({ headless: true, executablePath: process.env.CHROMIUM_PATH || undefined, args: ['--no-sandbox'] });
  page = await browser.newPage();
  await page.goto(url, { waitUntil: 'networkidle' });
});
after(async () => { if (browser) await browser.close(); });

test('합성 고지와 기본 검증 필터가 표시된다', async () => {
  assert.ok(await page.getByText('합성 데모 / 실제 학술 데이터 아님').first().isVisible());
  await page.getByText('표시할 주장이 없습니다').waitFor();
  assert.equal(await page.getByRole('button', { name: /가상 예시/ }).count(), 0);
  assert.ok(await page.getByText('후속 단계 · 비활성').isVisible());
});
test('미검증 전환으로 합성 주장, 출처 권리와 관계가 표시된다', async () => {
  await page.getByLabel('미검증 예시 표시').check();
  await page.getByText('2개의 주장').waitFor();
  assert.ok(await page.getByText('가상의 연구 메모 A — 실제로 존재하지 않는 문헌').isVisible());
  assert.ok(await page.getByText('저장 정책: metadata_only / 권리: unknown').isVisible());
  assert.ok(await page.getByText('qualifies · proposed').isVisible());
  await page.getByRole('button', { name: /후대 정경적 적용/ }).click();
  assert.ok(await page.getByText('가상의 연구 메모 B — 실제로 존재하지 않는 문헌').isVisible());
});
test('전통 필터는 근거 없는 귀속을 만들지 않는다', async () => {
  await page.locator('#tradition').selectOption('trd:demo-a');
  await page.getByText('선택한 전통에 연결된 데모 주장이 없습니다.').waitFor();
  assert.equal(await page.getByText('0개의 주장').count(), 1);
  await page.locator('#tradition').selectOption('');
  await page.getByText('2개의 주장').waitFor();
});
test('본문 선택을 바꾸면 그 본문의 결과로 갱신된다', async () => {
  await page.locator('#passage').selectOption('psg:mat123');
  await page.getByText('0개의 주장').waitFor();
  assert.equal(await page.getByText('qualifies · proposed').count(), 0);
  await page.locator('#passage').selectOption('psg:isa714');
  await page.getByText('2개의 주장').waitFor();
  await page.getByLabel('미검증 예시 표시').uncheck();
  await page.getByText('0개의 주장').waitFor();
});
