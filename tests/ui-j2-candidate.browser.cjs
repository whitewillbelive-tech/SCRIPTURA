// Synthetic-only browser regression for the J-2 private local UI.
// Starts the explicit test server; never opens a research archive.
const { test, before, after, afterEach } = require('node:test');
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const { spawn } = require('node:child_process');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const secret = 'synthetic-only-session-secret-123';
let browser, page, server, base;
const row = (overrides = {}) => ({
  key: 'd8:claims:1', stage: 'D8', record_kind: 'claim', attribution: 'individual_opinion',
  verification_status: 'source_checked', authority_status: 'unknown', independent_review_status: 'not_done', rights_status: 'unknown',
  tradition: '가상 전통', researcher: '가상 연구자', speaker: '가상 발화자', speaker_type:'unknown', passage_corpus: '가상 본문', passage_scheme: '가상 체계', passage_reference: 'A 1:1',
  source_title: '가상 문헌', source_creator: '가상 저자', source_kind: 'synthetic', source_doi: null, source_year: 2001,
  access_path: 'search_only', locator: null, evidence: [{kind:'synthetic_evidence',status:'pending'}], relationships:[{kind:'contrast',status:'pending',direction:'outgoing',assessment:'pending_evidence_review',target_key:'d8:claims:2'}],
  summary:'SYNTHETIC_SECRET_SUMMARY_MUST_NOT_RENDER', source_url:'https://example.invalid/private', unmapped:['synthetic_field'], ...overrides,
});
const payload = (records = [row()], total = records.length, extra = {}) => ({dataset:'synthetic',records,total,page_size:100,unmapped_summary:{d8:{claims:{input_count:17,mapping:'partial'},rights:{input_count:216,mapping:'unmapped'}}}, ...extra});
const reply = (route, data = payload(), status = 200) => route.fulfill({status, contentType:'application/json; charset=utf-8', body: JSON.stringify(data)});
async function waitReady(proc) {
  return await new Promise((resolve, reject) => {
    let buffer = ''; const timer = setTimeout(() => reject(new Error('synthetic server startup timed out')), 15000);
    proc.stdout.on('data', chunk => { buffer += chunk.toString(); const m = buffer.match(/READY (http:\/\/127\.0\.0\.1:\d+)/); if(m) {clearTimeout(timer);resolve(m[1]);} });
    proc.once('exit', code => { clearTimeout(timer);reject(new Error(`synthetic server exited ${code}`)); });
    proc.once('error', err => {clearTimeout(timer);reject(err);});
  });
}
before(async () => {
  server = spawn(process.env.PYTHON || 'python3', [path.join(root,'tests/j2_preview_test_server.py')], { cwd:root, env:{...process.env,SCRIPTURA_TEST_SECRET:secret}, stdio:['ignore','pipe','pipe'] });
  base = await waitReady(server);
  browser = await chromium.launch({ headless:true, executablePath:process.env.CHROMIUM_PATH || undefined, args:['--no-sandbox'] });
  page = await browser.newPage();
  await page.goto(base, {waitUntil:'networkidle'});
});
after(async () => { if(browser) await browser.close(); if(server) server.kill('SIGTERM'); });
afterEach(async()=>{if(page && await page.locator('#research-drawer[open]').count()) await page.getByRole('button',{name:'상세 닫기'}).click();});

test('연구 후보 화면은 명시적 세션 인증 전 자료를 조회하지 않는다', async () => {
  assert.match(await page.getByRole('status').textContent(), /세션/);
  await page.locator('.research-help > summary').click();
  assert.ok(await page.getByText(/표시 보류된 원문과 자유 텍스트는 가려집니다/).isVisible());
  await page.locator('.research-help > summary').click();
  assert.equal(await page.locator('.candidate').count(),0);
  assert.equal(await page.evaluate(() => location.hash), '');
  assert.equal(await page.evaluate(() => localStorage.length + sessionStorage.length), 0);
});
test('세션 비밀은 메모리로 전달하고 합성 자료와 안전한 메타데이터만 표시한다', async () => {
  let sawAuth = false;
  await page.route('**/api/candidates**', route => { sawAuth = route.request().headers().authorization === `Bearer ${secret}`; return reply(route); });
  await page.getByLabel('세션 비밀').fill(secret);
  await page.getByRole('button',{name:'세션 열기'}).click();
  await page.getByText('합성 시험 자료 / 실제 연구 데이터 아님.').waitFor();
  assert.equal(sawAuth,true);
  await page.locator('.research-metadata > summary').click();
  const mapping = page.getByRole('group',{name:'자료 범위와 미대응'});
  await mapping.locator('summary').click();
  assert.ok(await mapping.getByText('d8 · claims: 입력 17건 · 일부만 대응',{exact:true}).isVisible());
  assert.ok(await mapping.getByText('d8 · rights: 입력 216건 · 미대응',{exact:true}).isVisible());
  assert.equal(await page.getByLabel('세션 비밀').inputValue(),'');
  assert.equal(await page.evaluate(() => localStorage.length + sessionStorage.length),0);
  assert.ok(!page.url().includes(secret));
  await page.getByRole('button',{name:/가상 문헌/}).click();
  await page.getByRole('region',{name:'후보 상세'}).getByRole('button',{name:'검증 정보 보기'}).click();
  const detail = page.getByRole('dialog',{name:'검증 정보'});
  assert.ok(await detail.getByText('개인 의견',{exact:true}).isVisible());
  assert.ok(await detail.getByText('not_done',{exact:true}).count() === 0);
  assert.ok(await detail.getByText('독립 심사 미실시',{exact:true}).isVisible());
  assert.ok(await detail.getByText('발화 주체 유형 · 미확정',{exact:true}).isVisible());
  assert.ok(await detail.getByText('가상 본문 · 가상 체계 · A 1:1',{exact:true}).isVisible());
  assert.ok(await detail.getByText(/근거 · synthetic_evidence · pending/).isVisible());
  assert.ok(await detail.getByText(/관계 · 이 후보 → 연결 대상 · contrast · pending/).isVisible());
  await detail.getByText('대응되지 않은 필드 이름 보기').click();
  assert.ok(await detail.getByText('synthetic_field',{exact:true}).isVisible());
  assert.equal(await page.getByText('SYNTHETIC_SECRET_SUMMARY_MUST_NOT_RENDER').count(),0);
  assert.equal(await page.locator('a[href*="example.invalid"]').count(),0);
  await detail.getByRole('button',{name:'상세 닫기'}).click();
});
test('필터 수정은 오래된 카드와 상세를 즉시 지우고 검색에 반영한다', async () => {
  await page.locator('#advanced-filters > summary').click();
  await page.getByLabel('종교 · 교단 · 단체').fill('가상');
  await page.getByLabel('자료 단계').selectOption('d8');
  await page.getByLabel('관계 · 반론 종류').fill('contrast');
  await page.getByLabel('권리 행위').selectOption('store_excerpt');
  await page.getByLabel('권리 결정 · 추가 관찰').selectOption('unknown');
  assert.equal(await page.locator('.candidate').count(),0);
  assert.match(await page.getByRole('status').textContent(),/조건이 변경/);
  const response = page.waitForResponse(r => r.url().includes('/api/candidates') && new URL(r.url()).searchParams.get('community') === '가상' && new URL(r.url()).searchParams.get('stage') === 'd8' && new URL(r.url()).searchParams.get('relation_kind') === 'contrast' && new URL(r.url()).searchParams.get('rights_action') === 'store_excerpt' && new URL(r.url()).searchParams.get('rights_decision') === 'unknown');
  await page.getByRole('button',{name:'후보 검색'}).click(); await response;
  await page.getByRole('button',{name:/가상 문헌/}).waitFor();
});
test('503은 카드와 상세를 비우고 같은 조건에서 재조회할 수 있다', async () => {
  await page.unroute('**/api/candidates**');
  const fail = route => reply(route,{},503);
  await page.route('**/api/candidates**', fail);
  const failed = page.waitForResponse(r => r.url().includes('/api/candidates') && r.status() === 503);
  await page.getByRole('button',{name:'초기화'}).click(); await failed;
  await page.getByRole('region',{name:'검색 결과'}).getByRole('alert').getByText(/자료를 불러오지 못했습니다/).waitFor();
  assert.equal(await page.locator('.candidate').count(),0);
  await page.unroute('**/api/candidates**',fail);
  await page.route('**/api/candidates**', route => reply(route));
  const ok = page.waitForResponse(r => r.url().includes('/api/candidates') && r.status() === 200);
  await page.getByRole('button',{name:'초기화'}).click(); await ok;
  await page.getByRole('button',{name:/가상 문헌/}).waitFor();
  assert.equal(await page.getByRole('region',{name:'검색 결과'}).getByRole('alert').count(),0);
});
test('페이지 이동은 응답의 크기를 따라가고 이전 선택 상세를 지운다', async () => {
  await page.unroute('**/api/candidates**');
  await page.route('**/api/candidates**', route => {
    const offset = new URL(route.request().url()).searchParams.get('offset');
    return reply(route,payload([offset ? row({key:'synthetic:2',source_title:'가상 두번째'}) : row()],2,{page_size:1}));
  });
  await page.getByRole('button',{name:'후보 검색'}).click();
  await page.getByRole('button',{name:/가상 문헌/}).waitFor();
  await page.getByRole('button',{name:/가상 문헌/}).click();
  await page.getByRole('button',{name:'다음',exact:true}).click();
  await page.getByRole('button',{name:/가상 두번째/}).waitFor();
  assert.ok(await page.getByRole('region',{name:'후보 상세'}).getByText(/선택하세요/).isVisible());
  assert.ok(await page.getByRole('button',{name:'다음',exact:true}).isDisabled());
  assert.ok(await page.getByRole('button',{name:'이전',exact:true}).isEnabled());
});
test('늦은 이전 응답이 최신 검색 결과를 덮지 않는다', async () => {
  await page.unroute('**/api/candidates**');
  await page.evaluate(() => {
    const original = window.fetch;
    window.__j2Restore = () => { window.fetch = original; };
    window.fetch = (url, init) => original(url, {...init, signal:undefined});
  });
  let release;
  let started;
  const gate = new Promise(resolve => { release = resolve; });
  const arrived = new Promise(resolve => { started = resolve; });
  await page.route('**/api/candidates**', async route => {
    const q = new URL(route.request().url()).searchParams.get('q');
    if (q === 'first') { started(); await gate; return reply(route,payload([row({source_title:'오래된 가상 문헌'})])); }
    return reply(route,payload([row({source_title:'최신 가상 문헌'})]));
  });
  try {
    await page.getByLabel('통합 검색').fill('first');
    await page.getByRole('button',{name:'후보 검색'}).click();
    await arrived;
    await page.getByLabel('통합 검색').fill('second');
    await page.getByRole('button',{name:'후보 검색'}).click();
    await page.getByRole('button',{name:/최신 가상 문헌/}).waitFor();
    release();
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    assert.equal(await page.getByRole('button',{name:/오래된 가상 문헌/}).count(),0);
    assert.ok(await page.getByRole('button',{name:/최신 가상 문헌/}).isVisible());
  } finally { release(); await page.evaluate(() => window.__j2Restore()); }
});
test('자료 문자열은 HTML로 실행하지 않고 텍스트로만 표시한다', async () => {
  await page.unroute('**/api/candidates**');
  const text = '<img src=x onerror=alert(1)>';
  await page.route('**/api/candidates**', route => reply(route,payload([row({source_title:text})])));
  await page.getByRole('button',{name:'초기화'}).click();
  await page.getByRole('button',{name:/img src=x/}).waitFor();
  await page.getByRole('button',{name:/img src=x/}).click();
  assert.equal(await page.locator('img').count(),0);
  assert.equal(await page.getByRole('region',{name:'후보 상세'}).getByText(text,{exact:true}).count(),1);
});
test('외부 평가 대상·관계 방향·권리 원본과 후속 관찰을 분리한다', async () => {
  await page.unroute('**/api/candidates**');
  const source = row({attribution:'external_critique',tradition:null,community_role:'target',community_reference:'가상 대상',evaluated_subject:'가상 대상',speaker:null,
    rights:{store_excerpt:'unknown',browse:'conditional'}, rights_overrides:[{action:'store_excerpt',previous_decision:'unknown',new_decision:'conditional',evidence:'recorded'}],
    access_events:[{method:'search_only',result:'redacted_rights_unresolved',checked_at:'2026-01-01',note:'SECRET_ACCESS_NOTE'}],
    relationships:[{kind:'contrast',status:'pending',direction:'incoming',assessment:'pending_evidence_review',target_key:'d8:claims:2'}]});
  await page.route('**/api/candidates**', route => {
    const key = new URL(route.request().url()).searchParams.get('key');
    return reply(route,payload([key ? row({key:'d8:claims:2',source_title:'연결된 가상 문헌'}) : source]));
  });
  await page.getByRole('button',{name:'초기화'}).click();
  await page.getByRole('button',{name:/가상 문헌/}).waitFor();
  await page.getByRole('button',{name:/가상 문헌/}).click();
  await page.getByRole('region',{name:'후보 상세'}).getByRole('button',{name:'검증 정보 보기'}).click();
  const detail = page.getByRole('dialog',{name:'검증 정보'});
  assert.ok(await detail.getByText('외부 비평',{exact:true}).isVisible());
  assert.ok(await detail.getByText('평가 대상 · 가상 대상',{exact:true}).isVisible());
  assert.ok(await detail.getByText(/연결 대상 → 이 후보 · contrast · pending/).isVisible());
  assert.ok(await detail.getByText(/search_only · redacted_rights_unresolved · 2026-01-01/).isVisible());
  assert.ok(await detail.getByText('권리·형식 검토 전 표시 보류',{exact:true}).isVisible());
  assert.ok(await detail.getByText('확인 경로',{exact:true}).isVisible());
  assert.equal(await detail.getByText('SECRET_ACCESS_NOTE').count(),0);
  assert.ok(await detail.getByText(/unknown → conditional/).isVisible());
  assert.ok(await detail.getByText(/모든 이용은 허가하지 않습니다/).isVisible());
  await detail.getByRole('button',{name:'연결 대상 열기'}).click();
  await page.getByRole('dialog',{name:'연결 문헌'}).getByText('연결된 가상 문헌',{exact:true}).waitFor();
  await page.getByRole('dialog').getByRole('button',{name:'상세 닫기'}).click();
});
test('복수 판본의 권리 판단과 추가 관찰을 섞지 않는다', async () => {
  await page.unroute('**/api/candidates**');
  const source = row({record_kind:'source',rights_status:'multiple_editions',rights:{store_excerpt:'unmapped'},rights_overrides:[],
    edition_rights:[
      {key:'synthetic:edition:1',rights:{store_excerpt:'conditional',browse:'unknown'},rights_overrides:[{action:'store_excerpt',previous_decision:'unknown',new_decision:'conditional',evidence:'recorded'}]},
      {key:'synthetic:edition:2',rights:{store_excerpt:'unknown',browse:'conditional'},rights_overrides:[]},
    ]});
  await page.route('**/api/candidates**', route => reply(route,payload([source])));
  await page.getByRole('button',{name:'초기화'}).click();
  await page.getByRole('button',{name:/가상 문헌/}).waitFor();
  await page.getByRole('button',{name:/가상 문헌/}).click();
  await page.getByRole('region',{name:'후보 상세'}).getByRole('button',{name:'검증 정보 보기'}).click();
  const detail = page.getByRole('dialog',{name:'검증 정보'});
  const first = detail.getByRole('region',{name:'판본 1 권리'}), second = detail.getByRole('region',{name:'판본 2 권리'});
  assert.equal(await first.locator('dt').count(),9);
  assert.equal(await second.locator('dt').count(),9);
  assert.equal(await first.locator('.fact').filter({has:page.getByText('발췌 저장',{exact:true})}).locator('dd').textContent(),'conditional');
  assert.equal(await second.locator('.fact').filter({has:page.getByText('발췌 저장',{exact:true})}).locator('dd').textContent(),'unknown');
  assert.ok(await first.getByText(/unknown → conditional/).isVisible());
  assert.equal(await second.getByText(/unknown → conditional/).count(),0);
  assert.ok(await detail.getByText(/모든 이용은 허가하지 않습니다/).isVisible());
  await detail.getByRole('button',{name:'상세 닫기'}).click();
});
test('제목이 가려진 후보는 안전한 임시 좌표로 구별하고 원본 ID는 표시하지 않는다', async () => {
  await page.unroute('**/api/candidates**');
  const rows = [row({key:'d8:claims:1',source_title:null}),row({key:'SENSITIVE_ORIGINAL_ID',source_title:null})];
  await page.route('**/api/candidates**', route => reply(route,payload(rows)));
  await page.getByRole('button',{name:'초기화'}).click();
  const candidates = page.locator('.candidate');
  await candidates.first().waitFor();
  assert.ok(await candidates.nth(0).getByText('임시 참조 번호 · d8:claims:1',{exact:true}).isVisible());
  assert.ok(await candidates.nth(1).getByText('임시 참조 번호 · 미확인',{exact:true}).isVisible());
  assert.equal(await page.getByText('SENSITIVE_ORIGINAL_ID').count(),0);
  assert.equal(await page.locator('[data-key="SENSITIVE_ORIGINAL_ID"]').count(),0);
  await candidates.first().click();
  await page.getByRole('region',{name:'후보 상세'}).getByRole('button',{name:'검증 정보 보기'}).click();
  const detail = page.getByRole('dialog',{name:'검증 정보'});
  assert.ok(await detail.getByText('d8:claims:1',{exact:true}).isVisible());
  await detail.getByRole('button',{name:'상세 닫기'}).click();
});
test('주장 상세는 안전한 좌표의 문헌 후보로 이동하고 판본과 위치를 구분한다', async () => {
  await page.unroute('**/api/candidates**');
  const claim = row({key:'d8:claims:1',source_title:null,source_key:'d8:sources:4',edition_key:'d8:editions:2',locator_key:'d8:locators:3'});
  const source = row({key:'d8:sources:4',record_kind:'source',source_title:'연결된 가상 문헌'});
  await page.route('**/api/candidates**', route => {
    const key = new URL(route.request().url()).searchParams.get('key');
    return reply(route,payload([key === 'd8:sources:4' ? source : claim]));
  });
  await page.getByRole('button',{name:'초기화'}).click();
  await page.getByRole('button',{name:/서지 제목 표시 보류/}).waitFor();
  await page.getByRole('button',{name:/서지 제목 표시 보류/}).click();
  await page.getByRole('region',{name:'후보 상세'}).getByRole('button',{name:'검증 정보 보기'}).click();
  const detail = page.getByRole('dialog',{name:'검증 정보'});
  assert.ok(await detail.getByText('d8:editions:2',{exact:true}).isVisible());
  assert.ok(await detail.getByText('d8:locators:3',{exact:true}).isVisible());
  await detail.getByRole('button',{name:'연결된 문헌 후보 열기'}).click();
  await page.getByRole('dialog',{name:'연결 문헌'}).getByText('연결된 가상 문헌',{exact:true}).waitFor();
  await page.getByRole('dialog').getByRole('button',{name:'상세 닫기'}).click();
});
test('임의 URL이나 원본 ID는 문헌 좌표로 사용하지 않는다', async () => {
  await page.unroute('**/api/candidates**');
  const claim = row({source_key:'https://example.invalid/sources/4',edition_key:'RAW_EDITION_ID',locator_key:'RAW_LOCATOR_ID'});
  await page.route('**/api/candidates**', route => reply(route,payload([claim])));
  await page.getByRole('button',{name:'초기화'}).click();
  await page.getByRole('button',{name:/가상 문헌/}).waitFor();
  await page.getByRole('button',{name:/가상 문헌/}).click();
  await page.getByRole('region',{name:'후보 상세'}).getByRole('button',{name:'검증 정보 보기'}).click();
  const detail = page.getByRole('dialog',{name:'검증 정보'});
  assert.equal(await detail.getByRole('button',{name:'연결된 문헌 후보 열기'}).count(),0);
  assert.ok(await detail.getByText('연결된 문헌 후보 미확인').isVisible());
  assert.equal(await detail.getByText('RAW_EDITION_ID').count(),0);
  assert.equal(await detail.getByText('RAW_LOCATOR_ID').count(),0);
  assert.equal(await page.locator('a[href*="example.invalid"]').count(),0);
  await detail.getByRole('button',{name:'상세 닫기'}).click();
});
test('실제 합성 테스트 서버의 인증·필터 응답으로 후보를 검색한다', async () => {
  await page.unroute('**/api/candidates**');
  const ok = page.waitForResponse(r => r.url().includes('/api/candidates') && r.status() === 200);
  await page.getByRole('button',{name:'초기화'}).click(); await ok;
  await page.getByRole('button',{name:/가상 문헌 A/}).waitFor();
  await page.getByRole('button',{name:/가상 문헌 A/}).click();
  await page.getByRole('region',{name:'후보 상세'}).getByRole('button',{name:'검증 정보 보기'}).click();
  const detail = page.getByRole('dialog',{name:'검증 정보'});
  assert.ok(await detail.getByText('개인 의견',{exact:true}).isVisible());
  await detail.getByRole('button',{name:'상세 닫기'}).click();
  await page.getByLabel('문헌 작성자').fill('다른 연구자');
  const searched = page.waitForResponse(r => r.url().includes('/api/candidates') && new URL(r.url()).searchParams.get('researcher') === '다른 연구자');
  await page.getByRole('button',{name:'후보 검색'}).click(); await searched;
  await page.getByRole('button',{name:/가상 문헌 B/}).waitFor();
  assert.equal(await page.getByRole('button',{name:/가상 문헌 A/}).count(),0);
});
test('세션을 닫으면 결과와 메모리의 인증을 지운다', async () => {
  await page.getByRole('button',{name:'세션 닫기'}).click();
  assert.equal(await page.locator('.candidate').count(),0);
  assert.match(await page.getByRole('status').textContent(),/닫혔습니다/);
  await page.getByRole('button',{name:'후보 검색'}).click();
  assert.equal(await page.locator('.candidate').count(),0);
});
