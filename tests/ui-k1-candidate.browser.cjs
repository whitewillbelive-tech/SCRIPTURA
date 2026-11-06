// Synthetic K-1 browser tests. Never load or print a research archive.
const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const { spawn } = require('node:child_process');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const secret = 'synthetic-only-session-secret-123';
const synthetic = (overrides = {}) => ({
  key:'d10:sources:1', stage:'d10', record_kind:'source',
  source_title:'SYNTHETIC-UNAPPROVED-TITLE', source_creator:'SYNTHETIC-UNAPPROVED-CREATOR',
  source_doi:'SYNTHETIC-UNAPPROVED-DOI', source_year:'SYNTHETIC-UNAPPROVED-YEAR', locator:'SYNTHETIC-UNAPPROVED-LOCATOR',
  researcher:'SYNTHETIC-UNAPPROVED-RESEARCHER', speaker:'SYNTHETIC-UNAPPROVED-SPEAKER',
  tradition:'SYNTHETIC-UNAPPROVED-COMMUNITY', summary:'SYNTHETIC-UNAPPROVED-TEXT',
  field_eligibility:{source:{bibliography:'candidate_visible_local'}},
  field_policy:{source_title:'candidate_visible_local',source_creator:'candidate_visible_local'},
  ...overrides,
});
const payload = (records=[synthetic()], extra={}) => ({dataset:'D10',records,total:records.length,page_size:100,
  visibility_summary:{metadata_candidate:9,conditional_candidate:1,candidate_visible_local:0,unknown:1260,unmapped:0,total:1270}, ...extra});
const reply = (route, data=payload(), status=200) => route.fulfill({status,contentType:'application/json; charset=utf-8',body:JSON.stringify(data)});
let browser, page, server, base;
async function waitReady(proc) {
 return await new Promise((resolve,reject)=>{
  let output='', diagnostic='';
  const timer=setTimeout(()=>reject(new Error('synthetic server startup timed out')),15000);
  proc.stdout.on('data',chunk=>{output+=chunk;const m=output.match(/READY (http:\/\/127\.0\.0\.1:\d+)/);if(m){clearTimeout(timer);resolve(m[1]);}});
  proc.stderr.on('data',chunk=>{diagnostic+=chunk;});
  proc.once('exit',code=>{clearTimeout(timer);reject(new Error(`synthetic server exited ${code}: ${diagnostic}`));});
 });
}
before(async()=>{
 server=spawn(process.env.PYTHON||'python3',[path.join(root,'tests/j2_preview_test_server.py')],{cwd:root,env:{...process.env,SCRIPTURA_TEST_SECRET:secret},stdio:['ignore','pipe','pipe']});
 base=await waitReady(server);
 browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||undefined,args:['--no-sandbox']});
 page=await browser.newPage();await page.goto(base,{waitUntil:'networkidle'});
});
after(async()=>{if(browser)await browser.close();if(server)server.kill('SIGTERM');});

test('D10은 선택 자료와 조건부 후보를 표시하되 행의 승인 위조를 무시한다',async()=>{
 await page.route('**/api/candidates**',route=>reply(route));
 await page.getByLabel('세션 비밀').fill(secret);await page.getByRole('button',{name:'세션 열기'}).click();
 await page.getByText('임시 참조 번호 · d10:sources:1',{exact:true}).waitFor();
 assert.ok(await page.getByText(/D-10 연구 후보 · 선택한 로컬 자료/).isVisible());
 assert.ok(await page.getByText(/조건부 후보 1건 · 로컬 표시 승인 0건/).isVisible());
 assert.ok(await page.getByText(/조건부 후보는 표시 승인이 아닙니다/).isVisible());
 assert.equal(await page.getByText(/SYNTHETIC-UNAPPROVED/).count(),0);
 await page.locator('.candidate').first().click();
 assert.equal(await page.getByText(/SYNTHETIC-UNAPPROVED/).count(),0);
 const detail=page.getByRole('region',{name:'후보 상세'});
 await detail.getByText('필드별 표시 적격성 보기',{exact:true}).click();
 assert.ok(await detail.getByText('source · bibliography: 미확인 · 표시 승인 아님',{exact:true}).isVisible());
});

test('근거 없는 합계 1은 표시 승인으로 나타내지 않는다',async()=>{
 await page.unroute('**/api/candidates**');
 await page.route('**/api/candidates**',route=>reply(route,payload([synthetic()],{visibility_summary:{metadata_candidate:9,conditional_candidate:1,candidate_visible_local:1}})));
 await page.getByRole('button',{name:'초기화'}).click();
 await page.getByText('임시 참조 번호 · d10:sources:1',{exact:true}).waitFor();
 assert.ok(await page.getByText('표시 적격성 정보: 미확인',{exact:true}).isVisible());
 assert.equal(await page.getByText(/SYNTHETIC-UNAPPROVED/).count(),0);
});

test('D10에서 승인되지 않은 이름 검색을 명시적으로 보류한다',async()=>{
 let calls=0;await page.unroute('**/api/candidates**');
 await page.route('**/api/candidates**',route=>{calls++;return reply(route,payload([]));});
 await page.getByLabel('연구자 · 발화 주체').fill('SYNTHETIC-UNAPPROVED-RESEARCHER');
 const before=calls;await page.getByRole('button',{name:'후보 검색'}).click();
 assert.ok(await page.getByText('검색 보류',{exact:true}).isVisible());assert.equal(calls,before);
 await page.getByLabel('연구자 · 발화 주체').fill('');
 await page.getByLabel('자료 단계').selectOption('d10');
 await page.getByRole('button',{name:'후보 검색'}).click();await page.getByText('0개 후보',{exact:true}).waitFor();
 assert.ok(await page.getByText(/표시 보류된 필드의 일치 여부는 확인할 수 없습니다/).isVisible());
});

test('D10 세션에 D9 응답이 섞이지 않고 503 오류 시 이전 카드가 사라진다',async()=>{
 await page.unroute('**/api/candidates**');await page.route('**/api/candidates**',route=>reply(route));
 await page.getByRole('button',{name:'초기화'}).click();await page.getByText('임시 참조 번호 · d10:sources:1',{exact:true}).waitFor();
 await page.locator('.candidate').first().click();
 await page.unroute('**/api/candidates**');await page.route('**/api/candidates**',route=>reply(route,payload([],{dataset:'D9'})));
 await page.getByRole('button',{name:'초기화'}).click();await page.getByRole('region',{name:'검색 결과'}).getByRole('alert').waitFor();
 assert.equal(await page.locator('.candidate').count(),0);
 assert.equal(await page.getByRole('region',{name:'후보 상세'}).getByText('d10:sources:1',{exact:true}).count(),0);
 await page.unroute('**/api/candidates**');await page.route('**/api/candidates**',route=>reply(route,{},503));
 await page.getByRole('button',{name:'초기화'}).click();
 await page.getByRole('region',{name:'검색 결과'}).getByRole('alert').getByText(/자료를 불러오지 못했습니다/).waitFor();
 assert.equal(await page.locator('.candidate').count(),0);
});

test('연구 자료의 위조 제목은 HTML로도 렌더링되지 않는다',async()=>{
 await page.unroute('**/api/candidates**');
 const xss='<img src=x onerror="window.__k1_test_xss=true">';
 await page.route('**/api/candidates**',route=>reply(route,payload([synthetic({source_title:xss})])));
 await page.getByRole('button',{name:'초기화'}).click();await page.getByText('임시 참조 번호 · d10:sources:1',{exact:true}).waitFor();
 await page.locator('.candidate').first().click();
 assert.equal(await page.evaluate(()=>window.__k1_test_xss===true),false);
 assert.equal(await page.locator('img').count(),0);
 assert.equal(await page.getByText(xss,{exact:true}).count(),0);
});

test('합성 승인 예시의 제목은 실행 가능한 HTML이 아니라 텍스트다',async()=>{
 await page.getByRole('button',{name:'세션 닫기'}).click();
 await page.unroute('**/api/candidates**');
 const xss='<img src=x onerror="window.__k1_test_xss=true">';
 await page.route('**/api/candidates**',route=>reply(route,payload([synthetic({key:'d9:sources:2',source_title:xss})],{dataset:'synthetic'})));
 await page.getByLabel('세션 비밀').fill(secret);await page.getByRole('button',{name:'세션 열기'}).click();
 const candidate=page.locator('.candidate').first();await candidate.waitFor();
 assert.ok((await candidate.textContent()).includes(xss));
 await candidate.click();assert.ok((await page.getByRole('region',{name:'후보 상세'}).textContent()).includes(xss));
 assert.equal(await page.evaluate(()=>window.__k1_test_xss===true),false);
 assert.equal(await page.locator('img').count(),0);
});
