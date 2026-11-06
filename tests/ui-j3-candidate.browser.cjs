// Synthetic-only J-3 browser regression; never opens a research archive.
const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const { spawn } = require('node:child_process');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const secret = 'synthetic-only-session-secret-123';
let browser, page, server, base;
const row = (extra = {}) => ({key:'d9:claims:1',stage:'d9',record_kind:'claim',attribution:'external_critique',
  source_title:'SYNTHETIC-UNAPPROVED-TITLE',source_creator:'SYNTHETIC-UNAPPROVED-AUTHOR',researcher:'SYNTHETIC-UNAPPROVED-AUTHOR',
  speaker:'SYNTHETIC-UNAPPROVED-SPEAKER',tradition:'SYNTHETIC-UNAPPROVED-GROUP',community_reference:'SYNTHETIC-UNAPPROVED-GROUP',
  evaluated_subject:'SYNTHETIC-UNAPPROVED-GROUP',community_role:'target',verification_status:'source_checked',authority_status:'pending_authority',
  quotation_status:'unchecked',argument_status:'not_assessed',independent_review_status:'pending',rights_status:'unresolved',
  source_key:'d9:sources:1',edition_key:'d9:editions:1',locator_key:'d9:locators:1',summary:'SYNTHETIC-UNAPPROVED-TEXT',
  source_url:'https://example.invalid/private',evidence:[{kind:'support',status:'pending'}],
  relationships:[{kind:'contrast',status:'pending',direction:'outgoing',target_key:'d9:claims:2'}],unmapped:['statement_ko','SYNTHETIC_PRIVATE_IDENTIFIER'],...extra});
const payload = (records = [row()], extra = {}) => ({dataset:'D9',records,total:records.length,page_size:100,
  visibility_summary:{metadata_candidate:9,candidate_visible_local:0,unknown:1261,unmapped:0,total:1270},
  unmapped_summary:{d9:{claims:{input_count:6,mapping:'partial'},sources:{input_count:14,mapping:'partial'}}},...extra});
const reply = (route, data = payload(), status = 200) => route.fulfill({status,contentType:'application/json; charset=utf-8',body:JSON.stringify(data)});
async function waitReady(proc) {
 return await new Promise((resolve,reject) => {
  let text='', diagnostics='';const timer=setTimeout(()=>reject(new Error('synthetic server startup timed out')),15000);
  proc.stderr.on('data',chunk=>{diagnostics+=chunk.toString();});
  proc.stdout.on('data',chunk=>{text+=chunk.toString();const m=text.match(/READY (http:\/\/127\.0\.0\.1:\d+)/);if(m){clearTimeout(timer);resolve(m[1]);}});
  proc.once('exit',code=>{clearTimeout(timer);reject(new Error(`synthetic server exited ${code}: ${diagnostics}`));});
  proc.once('error',err=>{clearTimeout(timer);reject(err);});
 });
}
before(async()=>{
 server=spawn(process.env.PYTHON||'python3',[path.join(root,'tests/j2_preview_test_server.py')],{cwd:root,env:{...process.env,SCRIPTURA_TEST_SECRET:secret},stdio:['ignore','pipe','pipe']});
 base=await waitReady(server);
 browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||undefined,args:['--no-sandbox']});
 page=await browser.newPage();await page.goto(base,{waitUntil:'networkidle'});
});
after(async()=>{if(browser)await browser.close();if(server)server.kill('SIGTERM');});

test('D9 후보 상태는 승인 0과 미승인 이름을 분리한다',async()=>{
 await page.route('**/api/candidates**',route=>reply(route));
 await page.getByLabel('세션 비밀').fill(secret);await page.getByRole('button',{name:'세션 열기'}).click();
 await page.getByText('임시 참조 번호 · d9:claims:1',{exact:true}).waitFor();
 assert.ok(await page.getByText(/D-9 연구 후보 · 선택한 로컬 자료/).isVisible());
 assert.ok(await page.getByText(/검토 후보 9건 · 로컬 표시 승인 0건/).isVisible());
 assert.equal(await page.getByText('SYNTHETIC-UNAPPROVED-TITLE').count(),0);
 assert.equal(await page.getByText('SYNTHETIC-UNAPPROVED-AUTHOR').count(),0);
 assert.equal(await page.getByText('SYNTHETIC-UNAPPROVED-GROUP').count(),0);
 const selected=page.locator('.candidate').first();await selected.click();
 const detail=page.getByRole('region',{name:'후보 상세'});
 assert.ok(await detail.getByText('d9:claims:1',{exact:true}).isVisible());
 assert.ok(await detail.getByText('d9:editions:1',{exact:true}).isVisible());
 assert.ok(await detail.getByText('d9:locators:1',{exact:true}).isVisible());
  await detail.getByText('대응되지 않은 필드 이름 보기',{exact:true}).click();
  assert.ok(await detail.getByText('statement_ko',{exact:true}).isVisible());
  assert.equal(await detail.getByText('SYNTHETIC_PRIVATE_IDENTIFIER',{exact:true}).count(),0);
 assert.equal(await detail.getByText('SYNTHETIC-UNAPPROVED-TEXT').count(),0);
 assert.equal(await page.locator('a[href*="example.invalid"]').count(),0);
});

test('근거 없는 승인 플래그는 표시 승인으로 나타내지 않는다',async()=>{
 await page.unroute('**/api/candidates**');
 const forged=row({field_eligibility:{source:{bibliography:'candidate_visible_local'}},field_policy:{source_title:'candidate_visible_local'}});
 await page.route('**/api/candidates**',route=>reply(route,payload([forged],{visibility_summary:{metadata_candidate:9,candidate_visible_local:1}})));
 await page.getByRole('button',{name:'초기화'}).click();
 await page.getByText('임시 참조 번호 · d9:claims:1',{exact:true}).waitFor();
 assert.ok(await page.getByText('표시 적격성 정보: 미확인',{exact:true}).isVisible());
 assert.equal(await page.getByText('SYNTHETIC-UNAPPROVED-TITLE').count(),0);
 await page.locator('.candidate').first().click();
 const detail=page.getByRole('region',{name:'후보 상세'});
 await detail.getByText('필드별 표시 적격성 보기',{exact:true}).click();
 assert.ok(await detail.getByText('source · bibliography: 미확인 · 표시 승인 아님',{exact:true}).isVisible());
});

test('명시적 이름 검색 보류와 다른 조건의 0건을 구분한다',async()=>{
 let calls=0;await page.unroute('**/api/candidates**');
 await page.route('**/api/candidates**',route=>{calls++;return reply(route,payload([]));});
 await page.getByLabel('연구자 · 발화 주체').fill('SYNTHETIC-UNAPPROVED-AUTHOR');
 const before=calls;await page.getByRole('button',{name:'후보 검색'}).click();
 assert.ok(await page.getByText('검색 보류',{exact:true}).isVisible());
 assert.ok(await page.getByText(/보류는 일치하는 자료가 없다는 뜻이 아닙니다/).isVisible());
 assert.equal(calls,before);
 await page.getByLabel('연구자 · 발화 주체').fill('');await page.getByLabel('자료 단계').selectOption('d9');
 await page.getByRole('button',{name:'후보 검색'}).click();
 await page.getByText('0개 후보',{exact:true}).waitFor();
 assert.ok(await page.getByText(/표시 보류된 필드의 일치 여부는 확인할 수 없습니다/).isVisible());
 assert.notEqual(await page.getByText('검색 보류',{exact:true}).count(),1);
});

test('다른 데이터셋 응답은 목록이나 상세에 혼합하지 않는다',async()=>{
 await page.unroute('**/api/candidates**');
 await page.route('**/api/candidates**',route=>reply(route,payload([row({key:'d8:claims:3',source_title:'SYNTHETIC-OTHER-DATASET'})],{dataset:'D8'})));
 await page.getByRole('button',{name:'초기화'}).click();
 await page.getByRole('region',{name:'검색 결과'}).getByRole('alert').waitFor();
 assert.equal(await page.locator('.candidate').count(),0);
 assert.equal(await page.getByText('SYNTHETIC-OTHER-DATASET').count(),0);
 await page.unroute('**/api/candidates**');
 await page.route('**/api/candidates**',route=>{
  const key=new URL(route.request().url()).searchParams.get('key');
  return key ? reply(route,payload([row({key:'d8:sources:3',source_title:'SYNTHETIC-OTHER-DATASET'})],{dataset:'D8'})) : reply(route);
 });
 await page.getByRole('button',{name:'초기화'}).click();await page.getByText('임시 참조 번호 · d9:claims:1',{exact:true}).waitFor();
 await page.locator('.candidate').first().click();
 const detail=page.getByRole('region',{name:'후보 상세'});
 await detail.getByRole('button',{name:'연결된 문헌 후보 열기'}).click();
  await detail.getByText('선택한 자료 버전과 응답이 일치하지 않습니다.').waitFor();
 assert.equal(await page.getByText('SYNTHETIC-OTHER-DATASET').count(),0);
});

test('D9 후속 관찰을 기존 D8의 원본 권리·검증 상태와 합치지 않는다',async()=>{
 await page.unroute('**/api/candidates**');
 const older=row({key:'d8:claims:1',stage:'d8',verification_status:'source_checked',rights:{browse:'unknown'},
  d9_observations:[{kind:'audit',status:'pending',method:'direct',direction:'outgoing',target_key:'d9:claims:1',note:'SYNTHETIC-PRIVATE-NOTE'},
    {kind:'relationship',status:'source_checked',method:'unknown',direction:'incoming',relation_type:'same_community_similar_interpretation'}],
  d9_rights_observations:[{edition_key:'d8:editions:1',action:'browse',decision:'conditional',note:'SYNTHETIC-PRIVATE-NOTE'}]});
 await page.route('**/api/candidates**',route=>reply(route,payload([older])));
 await page.getByRole('button',{name:'초기화'}).click();await page.getByText('임시 참조 번호 · d8:claims:1',{exact:true}).waitFor();
 await page.locator('.candidate').first().click();
 const detail=page.getByRole('region',{name:'후보 상세'});
 assert.ok(await detail.getByText('D-9 후속 관찰 · 원본 상태 변경 없음',{exact:true}).isVisible());
 assert.ok(await detail.getByText(/관찰 · audit · pending · direct · 이 후보 → 연결 대상/).isVisible());
  assert.ok(await detail.getByText(/관찰 · relationship · source_checked · unknown · 연결 대상 → 이 후보 · 같은 공동체의 유사 해석/).isVisible());
  assert.equal(await detail.getByText(/직접 반박/).count(),0);
 assert.ok(await detail.getByText(/권리 추가 관찰 · 판본 d8:editions:1 · browse · conditional · 적용 대기/).isVisible());
 assert.ok(await detail.getByText('source_checked',{exact:true}).isVisible());
 const originalRights=detail.getByRole('region',{name:'연결된 판본 권리'});
 assert.equal(await originalRights.locator('.fact').filter({has:page.getByText('열람',{exact:true})}).locator('dd').textContent(),'unknown');
 assert.equal(await detail.getByText('SYNTHETIC-PRIVATE-NOTE').count(),0);
});

test('D9의 503은 이전 카드·상세를 지우고 초기화로 복구한다',async()=>{
 await page.unroute('**/api/candidates**');
 await page.route('**/api/candidates**',route=>reply(route));
 await page.getByRole('button',{name:'초기화'}).click();await page.getByText('임시 참조 번호 · d9:claims:1',{exact:true}).waitFor();
 await page.locator('.candidate').first().click();
 await page.unroute('**/api/candidates**');
 const fail=route=>reply(route,{},503);await page.route('**/api/candidates**',fail);
 const response=page.waitForResponse(r=>r.url().includes('/api/candidates')&&r.status()===503);
 await page.getByRole('button',{name:'초기화'}).click();await response;
 await page.getByRole('region',{name:'검색 결과'}).getByRole('alert').getByText(/자료를 불러오지 못했습니다/).waitFor();
 assert.equal(await page.locator('.candidate').count(),0);
 assert.equal(await page.getByRole('region',{name:'후보 상세'}).getByText('d9:claims:1',{exact:true}).count(),0);
 await page.unroute('**/api/candidates**',fail);await page.route('**/api/candidates**',route=>reply(route));
 await page.getByRole('button',{name:'초기화'}).click();await page.getByText('임시 참조 번호 · d9:claims:1',{exact:true}).waitFor();
});

test('늦은 D9 응답이 최신 D9 검색을 덮지 않는다',async()=>{
 await page.unroute('**/api/candidates**');
 await page.evaluate(()=>{const original=window.fetch;window.__j3Restore=()=>{window.fetch=original;};window.fetch=(url,init)=>original(url,{...init,signal:undefined});});
 let release,start;const gate=new Promise(resolve=>{release=resolve;});const arrived=new Promise(resolve=>{start=resolve;});
 await page.route('**/api/candidates**',async route=>{
  const q=new URL(route.request().url()).searchParams.get('q');
  if(q==='old'){start();await gate;return reply(route,payload([row({key:'d9:claims:4'})]));}
  return reply(route,payload([row({key:'d9:claims:5'})]));
 });
 try {
  await page.getByLabel('통합 검색').fill('old');await page.getByRole('button',{name:'후보 검색'}).click();await arrived;
  await page.getByLabel('통합 검색').fill('new');await page.getByRole('button',{name:'후보 검색'}).click();
  await page.getByText('임시 참조 번호 · d9:claims:5',{exact:true}).waitFor();
  const oldResponse=page.waitForResponse(r=>new URL(r.url()).searchParams.get('q')==='old'&&r.status()===200);
  release();await oldResponse;await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  assert.equal(await page.getByText('임시 참조 번호 · d9:claims:4',{exact:true}).count(),0);
  assert.ok(await page.getByText('임시 참조 번호 · d9:claims:5',{exact:true}).isVisible());
 } finally { release();await page.evaluate(()=>window.__j3Restore()); }
});

test('세션 종료 후 새 D8 세션을 열 수 있고 이전 D9 결과는 없다',async()=>{
 await page.getByRole('button',{name:'세션 닫기'}).click();
 await page.getByRole('button',{name:'초기화'}).click();
 await page.unroute('**/api/candidates**');
 await page.route('**/api/candidates**',route=>reply(route,payload([row({key:'d8:claims:8',stage:'d8'})],{dataset:'D8'})));
 await page.getByLabel('세션 비밀').fill(secret);await page.getByRole('button',{name:'세션 열기'}).click();
 await page.getByText('임시 참조 번호 · d8:claims:8',{exact:true}).waitFor();
 assert.ok(await page.getByText(/D-8 연구 후보 · 선택한 로컬 자료/).isVisible());
 assert.equal(await page.getByText('임시 참조 번호 · d9:claims:1',{exact:true}).count(),0);
 await page.locator('.candidate').first().click();
 assert.equal(await page.getByText('D-9 후속 관찰 · 원본 상태 변경 없음',{exact:true}).count(),0);
});

test('명시 승인된 표시 예시는 합성 모드에서만 표시한다',async()=>{
 await page.getByRole('button',{name:'세션 닫기'}).click();await page.getByRole('button',{name:'초기화'}).click();
 await page.unroute('**/api/candidates**');
 const synthetic=row({source_title:'가상 승인 예시',field_eligibility:{source:{bibliography:'candidate_visible_local'}}});
 await page.route('**/api/candidates**',route=>reply(route,payload([synthetic],{dataset:'synthetic'})));
 await page.getByLabel('세션 비밀').fill(secret);await page.getByRole('button',{name:'세션 열기'}).click();
 await page.getByRole('button',{name:/가상 승인 예시/}).waitFor();await page.getByRole('button',{name:/가상 승인 예시/}).click();
 const detail=page.getByRole('region',{name:'후보 상세'});await detail.getByText('필드별 표시 적격성 보기',{exact:true}).click();
 assert.ok(await detail.getByText('source · bibliography: candidate_visible_local · 합성 시험용 승인',{exact:true}).isVisible());
 assert.ok(await page.getByText('합성 시험 자료 / 실제 연구 데이터 아님.').isVisible());
});
