// Browser-to-HTTP integration for the synthetic I-2 authority comparison.
// Start the local app before running; no real research data or DB is needed.
const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const base = process.env.SCRIPTURA_TEST_URL || 'http://127.0.0.1:3107';
let browser, page;
const group = name => page.locator(`section[aria-labelledby="group-${name}"]`);
before(async () => {
  browser = await chromium.launch({ headless: true, executablePath: process.env.CHROMIUM_PATH || undefined, args: ['--no-sandbox'] });
  page = await browser.newPage();
  await page.goto(base + '/authority', { waitUntil: 'networkidle' });
});
after(async () => { if (browser) await browser.close(); });

test('합성 고지와 별도 범주의 실제 API 응답을 표시한다', async () => {
  assert.ok(await page.getByText(/합성 데모 \/ 실제 학술 데이터 아님/).first().isVisible());
  await page.getByText('7개 예시', { exact: true }).waitFor();
  await page.getByLabel('기준일').fill('2025-01-01');
  await group('official').getByText('가상 공동체의 채택 문헌', { exact: true }).waitFor();
  for (const heading of ['집단 자신의 공식 채택 입장','공동체 교육과 기관 간행물','전통 안의 개인 설명','외부의 설명과 비판','언어·역사 및 학술적 검토']) {
    assert.ok(await page.getByRole('heading', { name: heading, exact: true }).isVisible());
  }
  assert.ok(await group('official').getByText('가상 공동체의 채택 문헌', { exact: true }).isVisible());
  assert.ok(await group('institution').getByText('가상 기관의 교육 설명', { exact: true }).isVisible());
  assert.ok(await page.getByText('후속 단계 · 비활성', { exact: true }).isVisible());
});
test('대표성·발행·확인 경로·권리와 네 독립 검증 상태를 표시한다', async () => {
  const official = group('official').locator('article');
  assert.ok(await official.getByText('집단 대표성의 근거', { exact: true }).isVisible());
  assert.ok(await official.getByText('합성 채택 문서 및 범위 확인', { exact: true }).isVisible());
  assert.ok(await official.getByText(/직접 확인/).first().isVisible());
  assert.ok(await official.getByText(/2020-01-01/).first().isVisible());
  assert.ok(await official.getByText(/원문 저장·임베딩·재배포/).isVisible());
  const axes = official.locator('[aria-label="독립된 네 검증 상태"]');
  assert.ok(await axes.getByText('직접 대조', { exact: true }).isVisible());
  assert.ok(await axes.getByText('채택 근거 확인', { exact: true }).isVisible());
  assert.ok(await axes.getByText('평가하지 않음', { exact: true }).isVisible());
  assert.ok(await axes.getByText('기록 없음', { exact: true }).isVisible());
});
test('개인 의견과 전언을 채택된 공동체 입장과 분리한다', async () => {
  assert.ok(await group('individual').getByText('가상 개인 의견', { exact: true }).isVisible());
  assert.equal(await group('official').getByText('가상 개인 의견', { exact: true }).count(), 0);
  assert.ok(await group('outside').getByText('가상 외부 비판', { exact: true }).isVisible());
  assert.ok((await group('outside').getByText('전언', { exact: true }).count()) >= 1);
  assert.ok(await group('academic').getByText('기록 없음', { exact: true }).isVisible());
  assert.ok(await group('historical').getByText(/1951-01-01/).isVisible());
});
test('기준일 밖의 채택은 미확정이며 과거 간행물을 현재 입장으로 승격하지 않는다', async () => {
  await page.getByLabel('기준일').fill('2050-01-01');
  await group('uncertain').getByText('가상 공동체의 채택 문헌', { exact: true }).waitFor();
  assert.equal(await group('official').locator('article').count(), 0);
  assert.ok(await group('uncertain').getByText('근거 부족 · 미확정').first().isVisible());
  assert.ok(await group('historical').getByText('가상 과거 간행물', { exact: true }).isVisible());
  await page.getByLabel('기준일').fill('2025-01-01');
  await group('official').getByText('가상 공동체의 채택 문헌', { exact: true }).waitFor();
});
test('전통과 범주 필터는 개인 의견만 분리하고 서버 실패 시 이전 결과를 지운다', async () => {
  await page.getByLabel('가상 전통').selectOption('synthetic:tradition-a');
  await page.getByText('3개 예시', { exact: true }).waitFor();
  await page.getByLabel('비교 범주').selectOption('individual_insider_view');
  await page.getByText('1개 예시', { exact: true }).waitFor();
  assert.ok(await group('individual').getByText('가상 개인 의견', { exact: true }).isVisible());
  assert.equal(await group('official').locator('article').count(), 0);
  await page.route('**/api/v1/authority?*', route => route.fulfill({status: 503, contentType: 'application/json', body: '{}'}));
  await page.getByRole('button', { name: '초기화' }).click();
  await page.getByRole('alert').waitFor();
  assert.equal(await page.locator('article').count(), 0);
  await page.unroute('**/api/v1/authority?*');
});
