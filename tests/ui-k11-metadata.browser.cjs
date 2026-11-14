// Synthetic K-1.1 browser tests: no research archive, records, or screenshots.
const {test, before, after} = require('node:test');
const assert = require('node:assert/strict');
const {chromium} = require('playwright');
const {spawn} = require('node:child_process');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const secret = 'synthetic-only-session-secret-123';
const marker = 'k1.1-verified';
const xss = '<img src=x onerror="window.__synthetic_metadata_xss=true">';
const row = (extra = {}) => ({
  key:'d10:sources:1', stage:'d10', record_kind:'source',
  source_title:'SYNTHETIC-RAW-TITLE', source_creator:'SYNTHETIC-RAW-CREATOR',
  tradition:'SYNTHETIC-RAW-COMMUNITY', source_doi:'SYNTHETIC-RAW-DOI',
  summary:'SYNTHETIC-RAW-PROTECTED', authority_status:'pending_authority',
  source_verification_status:'verified_fields_only', verification_status:'source_checked', independent_review_status:'pending',
  verified_metadata:{source_title:'합성 검증 문헌',source_creator:'합성 저자',
    source_publisher:'합성 발행기관',source_year:2024,community_name:'합성 공동체'},
  ...extra,
});
const payload = (records=[row()], extra={}) => ({dataset:'D10',metadata_projection:marker,
  records,total:records.length,page_size:100,
  metadata_coverage:{source_title:3,source_creator:2,source_publisher:1,source_year:1,community_name:1},
  visibility_summary:{metadata_candidate:9,
    conditional_candidate:1,candidate_visible_local:0,unknown:1260,unmapped:0,total:1270},...extra});
const reply = (route,data=payload(),status=200) => route.fulfill({status,
  contentType:'application/json; charset=utf-8',body:JSON.stringify(data)});
let browser,page,server,base;
async function waitReady(proc) {
 return await new Promise((resolve,reject)=>{
  let out='',err=''; const timer=setTimeout(()=>reject(new Error('synthetic startup timeout')),15000);
  proc.stdout.on('data',c=>{out+=c;const m=out.match(/READY (http:\/\/127\.0\.0\.1:\d+)/);if(m){clearTimeout(timer);resolve(m[1]);}});
  proc.stderr.on('data',c=>{err+=c;});
  proc.once('exit',code=>{clearTimeout(timer);reject(new Error(`synthetic server exit ${code}: ${err}`));});
 });
}
before(async()=>{
 server=spawn(process.env.PYTHON||'python3',[path.join(root,'tests/j2_preview_test_server.py')],
   {cwd:root,env:{...process.env,SCRIPTURA_TEST_SECRET:secret},stdio:['ignore','pipe','pipe']});
 base=await waitReady(server);
 browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||undefined,args:['--no-sandbox']});
 page=await browser.newPage();await page.goto(base,{waitUntil:'networkidle'});
});
after(async()=>{if(browser)await browser.close();if(server)server.kill('SIGTERM');});

test('확인된 서지 필드와 미확정 공식성 및 학술 심사는 별도로 표시된다',async()=>{
 await page.route('**/api/candidates**',route=>reply(route));
 await page.getByLabel('세션 비밀').fill(secret);await page.getByRole('button',{name:'세션 열기'}).click();
 const candidate=page.locator('.candidate').first();await candidate.waitFor();
 await page.locator('.research-metadata > summary').click();
 assert.ok(await page.getByText(/문헌명 3건 · 저자 2건 · 발행기관 1건 · 출판 연도 1건 · 공동체명 1건/).isVisible());
 await page.locator('.research-metadata > summary').click();
 assert.ok((await candidate.textContent()).includes('합성 검증 문헌'));
 await candidate.click();const detail=page.getByRole('region',{name:'후보 상세'});
 await detail.getByRole('button',{name:'검증 정보 보기'}).click();
 const verification=page.locator('#research-drawer');
 for(const text of ['합성 검증 문헌','합성 저자','합성 발행기관','합성 공동체','2024','source_checked','pending_authority','pending']) {
   assert.ok((await verification.textContent()).includes(text));
 }
 assert.equal(await page.getByText(/SYNTHETIC-RAW/).count(),0);
 await page.locator('#drawer-close').click();
});

test('주장 입력 확인과 문헌 출처 확인을 혼동하지 않는다',async()=>{
 await page.unroute('**/api/candidates**');
 await page.route('**/api/candidates**',route=>reply(route,payload([row({verified_metadata:{},
   source_verification_status:'unconfirmed',verification_status:'source_checked'})])));
 await page.getByRole('button',{name:'초기화'}).click();const candidate=page.locator('.candidate').first();await candidate.waitFor();
 await candidate.click();
 await page.getByRole('region',{name:'후보 상세'}).getByRole('button',{name:'검증 정보 보기'}).click();
 const detail=page.locator('#research-drawer');
 assert.equal(await detail.locator('.fact').filter({has:page.getByText('출처 확인 상태',{exact:true})}).locator('dd').textContent(),'미확인');
 assert.equal(await detail.locator('.fact').filter({has:page.getByText('입력 검증 상태',{exact:true})}).locator('dd').textContent(),'source_checked');
 await page.locator('#drawer-close').click();
});

test('확인된 이름 검색을 전송하고 검색 범위 제한을 설명한다',async()=>{
 let seen='';await page.unroute('**/api/candidates**');
 await page.route('**/api/candidates**',route=>{seen=route.request().url();return reply(route,payload([]));});
 await page.getByLabel('문헌 작성자').fill('합성 저자');
 await page.getByRole('button',{name:'후보 검색'}).click();
 await page.getByText('0개 후보',{exact:true}).waitFor();
 assert.equal(new URL(seen).searchParams.get('researcher'),'합성 저자');
 assert.ok(await page.getByText(/표시 보류된 필드의 일치 여부는 확인할 수 없습니다/).isVisible());
 await page.getByLabel('문헌 작성자').fill('');
 await page.locator('#advanced-filters summary').click();
 await page.getByLabel('종교 · 교단 · 단체').fill('합성 공동체');
 await page.getByRole('button',{name:'후보 검색'}).click();
 await page.getByText('0개 후보',{exact:true}).waitFor();
 assert.equal(new URL(seen).searchParams.get('community'),'합성 공동체');
 await page.getByLabel('종교 · 교단 · 단체').fill('');
 await page.getByLabel('통합 검색').fill('합성 검증 문헌');
 await page.getByRole('button',{name:'후보 검색'}).click();
 await page.getByText('0개 후보',{exact:true}).waitFor();
 assert.equal(new URL(seen).searchParams.get('q'),'합성 검증 문헌');
});

test('원본의 위조 필드와 정책 플래그는 표시하지 않는다',async()=>{
 await page.unroute('**/api/candidates**');
 await page.route('**/api/candidates**',route=>reply(route,payload([row({verified_metadata:{},
   field_policy:{source_title:'candidate_visible_local'},source_year:'SYNTHETIC-RAW-YEAR'})])));
 await page.getByRole('button',{name:'초기화'}).click();
 await page.getByText('서지 제목 표시 보류',{exact:true}).waitFor();
 await page.locator('.candidate').first().click();
 assert.equal(await page.getByText(/SYNTHETIC-RAW/).count(),0);
});

test('검색 가능한 이름이 없으면 0건이 아니라 검색 보류로 표시한다',async()=>{
 let calls=0;await page.unroute('**/api/candidates**');
 await page.route('**/api/candidates**',route=>{calls++;return reply(route,payload([],{
   metadata_coverage:{source_title:0,source_creator:0,source_publisher:0,source_year:0,community_name:0}}));});
 await page.getByRole('button',{name:'초기화'}).click();await page.getByText('0개 후보',{exact:true}).waitFor();
 const before=calls;await page.getByLabel('문헌 작성자').fill('합성 미확인 이름');
 await page.getByRole('button',{name:'후보 검색'}).click();
 assert.ok(await page.getByText('검색 보류',{exact:true}).isVisible());assert.equal(calls,before);
 assert.ok(await page.getByText(/보류는 일치하는 자료가 없다는 뜻이 아닙니다/).isVisible());
});

test('서버 투영 표식이 없으면 위조된 metadata 객체도 가린다',async()=>{
 await page.unroute('**/api/candidates**');
 await page.route('**/api/candidates**',route=>reply(route,payload([row()],{metadata_projection:undefined})));
 await page.getByRole('button',{name:'초기화'}).click();
 await page.getByText('서지 제목 표시 보류',{exact:true}).waitFor();
 assert.equal(await page.getByText('합성 검증 문헌',{exact:true}).count(),0);
});

test('허용된 합성 제목의 HTML 문자는 실행되지 않고 텍스트로 표시된다',async()=>{
 await page.unroute('**/api/candidates**');
 await page.route('**/api/candidates**',route=>reply(route,payload([row({verified_metadata:{source_title:xss}})])));
 await page.getByRole('button',{name:'초기화'}).click();
 const candidate=page.locator('.candidate').first();await candidate.waitFor();
 assert.ok((await candidate.textContent()).includes(xss));await candidate.click();
 assert.equal(await page.evaluate(()=>window.__synthetic_metadata_xss===true),false);
 assert.equal(await page.locator('img').count(),0);
 assert.ok((await page.getByRole('region',{name:'후보 상세'}).textContent()).includes(xss));
});
