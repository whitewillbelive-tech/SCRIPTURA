// Synthetic-only K-1.3 UI tests: no research archives, values or screenshots.
const {test, before, after} = require('node:test');
const assert = require('node:assert/strict');
const {chromium} = require('playwright');
const {spawn} = require('node:child_process');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const secret = 'synthetic-only-session-secret-123';
const marker = 'k1.3-local-candidate';
const blocked = 'SYNTHETIC-RESTRICTED-SECRET';
const xss = '<img src=x onerror="window.__candidate_xss=true">';
const row = (extra = {}) => ({
  key:'d10:sources:1',stage:'d10',record_kind:'source',
  source_title:'SYNTHETIC-RAW-TITLE', source_creator:'SYNTHETIC-RAW-AUTHOR',
  tradition:'SYNTHETIC-RAW-COMMUNITY',source_doi:'SYNTHETIC-RAW-DOI',summary:'SYNTHETIC-RAW-PROTECTED',
  attribution:'individual_opinion',community_role:'target',source_verification_status:'unconfirmed',
  verification_status:'source_checked',authority_status:'pending_authority',independent_review_status:'pending',
  candidate_metadata:{
    source_title:{value:'합성 후보 문헌',status:'recorded_unverified'},
    source_creator:{value:'합성 후보 저자',status:'recorded_unverified'},
    source_publisher:{value:blocked,status:'restricted',reason:'explicit_restriction'},
    source_year:{value:'2024',status:'source_confirmed'},
    community_name:{value:blocked,status:'missing_or_unmapped'},
  }, ...extra,
});
const payload = (records=[row()],extra={}) => ({dataset:'D10',metadata_projection:marker,
  records,total:records.length,page_size:100,
  metadata_coverage:{source_title:2,source_creator:2,source_publisher:0,source_year:1,community_name:0},
  visibility_summary:{metadata_candidate:8,conditional_candidate:1,candidate_visible_local:0,unknown:751,unmapped:510,total:1270},
  candidate_restriction_summary:{cards:{source_title:{explicit_restriction:1},source_creator:{sensitive_or_personal:2}},sources:{source_title:{explicit_restriction:1}}},
  local_visibility:'private_local_candidate',publication_status:'not_granted',...extra});
const reply = (route,data=payload(),status=200) => route.fulfill({status,
  contentType:'application/json; charset=utf-8',body:JSON.stringify(data)});
let browser,page,server,base;
async function waitReady(proc) {
 return await new Promise((resolve,reject)=>{
  let out='',err='';const timer=setTimeout(()=>reject(new Error('synthetic server timeout')),15000);
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

test('원본 서지 후보는 상태·공식성·학술 상태와 분리된다',async()=>{
 await page.route('**/api/candidates**',route=>reply(route));
 await page.getByLabel('세션 비밀').fill(secret);await page.getByRole('button',{name:'세션 열기'}).click();
 const candidate=page.locator('.candidate').first();await candidate.waitFor();
 const card=await candidate.textContent();
 for(const text of ['합성 후보 문헌','합성 후보 저자','원본 기록 · 독립 확인 전']) assert.ok(card.includes(text));
 assert.ok((await page.locator('#metadata-coverage').textContent()).includes('로컬 후보 필드 검색 범위'));
 assert.ok((await page.locator('#visibility-status').textContent()).includes('공개·재배포 승인이 아닙니다'));
 assert.ok(await page.getByLabel('문헌 작성자',{exact:true}).isVisible());
 assert.equal(await page.getByLabel('연구자 · 발화 주체',{exact:true}).count(),0);
 await page.locator('.research-metadata > summary').click();
 await page.locator('#candidate-limits summary').click();
 assert.ok((await page.locator('#candidate-limits').textContent()).includes('명시적 이용 제한 1건'));
 assert.ok((await page.locator('#candidate-limits').textContent()).includes('민감정보 또는 개인정보 2건'));
 await page.locator('.research-metadata > summary').click();
 await candidate.click();await page.getByRole('region',{name:'후보 상세'}).getByRole('button',{name:'검증 정보 보기'}).click();const detail=page.locator('#research-drawer');const text=await detail.textContent();
 for(const expected of ['문헌 제목 표시 상태','원본 기록 · 독립 확인 전','출처 대조 완료','표시 제한','명시적 이용 제한','누락 또는 연결 미확인','비공개 로컬 연구 후보','공개 · 재배포','별도 승인 필요']) assert.ok(text.includes(expected));
 assert.equal(await page.getByText(blocked,{exact:true}).count(),0);
 assert.equal(await page.getByText(/SYNTHETIC-RAW/).count(),0);
 await page.locator('#drawer-close').click();
});

test('표시 가능한 후보 제목과 저자는 서버의 검색으로 전달된다',async()=>{
 let seen='';await page.unroute('**/api/candidates**');
 await page.route('**/api/candidates**',route=>{seen=route.request().url();return reply(route,payload([]));});
 await page.getByLabel('통합 검색').fill('합성 후보 문헌');await page.getByRole('button',{name:'후보 검색'}).click();
 await page.getByText('0개 후보',{exact:true}).waitFor();assert.equal(new URL(seen).searchParams.get('q'),'합성 후보 문헌');
 await page.getByLabel('통합 검색').fill('');await page.getByLabel('문헌 작성자',{exact:true}).fill('합성 후보 저자');
 await page.getByRole('button',{name:'후보 검색'}).click();await page.getByText('0개 후보',{exact:true}).waitFor();
 assert.equal(new URL(seen).searchParams.get('researcher'),'합성 후보 저자');
});

test('제한·누락·알 수 없는 상태와 위조 원본 필드는 출력하지 않는다',async()=>{
 await page.unroute('**/api/candidates**');
 const fields={source_title:{value:blocked,status:'restricted'},source_creator:{value:blocked,status:'missing_or_unmapped'},
  source_publisher:{value:blocked,status:'made_up_approved',reason:blocked},source_year:{value:'2222',status:'restricted'},community_name:{value:blocked,status:'restricted'}};
 await page.route('**/api/candidates**',route=>reply(route,payload([row({candidate_metadata:fields})])));
 await page.getByRole('button',{name:'초기화'}).click();await page.getByText('서지 제목 표시 보류',{exact:true}).waitFor();
 await page.locator('.candidate').first().click();
 assert.equal(await page.getByText(blocked,{exact:true}).count(),0);assert.equal(await page.getByText(/SYNTHETIC-RAW/).count(),0);
 assert.equal(await page.getByText('2222',{exact:true}).count(),0);
});

test('응답 투영 표식 없이 위조된 후보 메타데이터는 숨긴다',async()=>{
 await page.unroute('**/api/candidates**');await page.route('**/api/candidates**',route=>reply(route,payload([row()],{metadata_projection:undefined})));
 await page.getByRole('button',{name:'초기화'}).click();await page.getByText('서지 제목 표시 보류',{exact:true}).waitFor();
 assert.equal(await page.getByText('합성 후보 문헌',{exact:true}).count(),0);
});

test('후보 값의 HTML은 실행하지 않고 텍스트로 표시한다',async()=>{
 await page.unroute('**/api/candidates**');const fields={source_title:{value:xss,status:'recorded_unverified'}};
 await page.route('**/api/candidates**',route=>reply(route,payload([row({candidate_metadata:fields})])));
 await page.getByRole('button',{name:'초기화'}).click();const candidate=page.locator('.candidate').first();await candidate.waitFor();
 assert.ok((await candidate.textContent()).includes(xss));await candidate.click();
 assert.equal(await page.evaluate(()=>window.__candidate_xss===true),false);assert.equal(await page.locator('img').count(),0);
 assert.ok((await page.getByRole('region',{name:'후보 상세'}).textContent()).includes(xss));
});

test('공동체 표시 가능 값이 없으면 이름 검색을 보류한다',async()=>{
 let calls=0;await page.unroute('**/api/candidates**');
 await page.route('**/api/candidates**',route=>{calls++;return reply(route,payload([]));});
 await page.getByRole('button',{name:'초기화'}).click();await page.getByText('0개 후보',{exact:true}).waitFor();const before=calls;
 if (!(await page.locator('#advanced-filters').evaluate(e=>e.open))) await page.locator('#advanced-filters summary').click();
 await page.getByLabel('종교 · 교단 · 단체').fill('합성 미확인 공동체');await page.getByRole('button',{name:'후보 검색'}).click();
 assert.ok(await page.getByText('검색 보류',{exact:true}).isVisible());assert.equal(calls,before);
 assert.ok(await page.getByText(/보류는 일치하는 자료가 없다는 뜻이 아닙니다/).isVisible());
});

test('503 또는 필터 변경 시 기존 후보 카드와 상세가 남지 않는다',async()=>{
 await page.unroute('**/api/candidates**');await page.route('**/api/candidates**',route=>reply(route));
 await page.getByRole('button',{name:'초기화'}).click();await page.locator('.candidate').first().waitFor();await page.locator('.candidate').first().click();
 await page.unroute('**/api/candidates**');await page.route('**/api/candidates**',route=>reply(route,{},503));
 await page.getByRole('button',{name:'후보 검색'}).click();await page.getByRole('region',{name:'검색 결과'}).getByRole('alert').waitFor();
 assert.equal(await page.locator('.candidate').count(),0);
 assert.equal(await page.getByRole('region',{name:'후보 상세'}).getByText('합성 후보 문헌',{exact:true}).count(),0);
});

test('명시된 공동체 자기 설명과 평가 대상 역할을 뒤섞지 않는다',async()=>{
 await page.unroute('**/api/candidates**');
 const selfFields={...row().candidate_metadata,community_name:{value:'합성 공동체',status:'recorded_unverified',relationship_role:'self'}};
 await page.route('**/api/candidates**',route=>reply(route,payload([row({community_role:'target',candidate_metadata:selfFields})])));
 await page.getByRole('button',{name:'초기화'}).click();await page.locator('.candidate').first().waitFor();await page.locator('.candidate').first().click();
 await page.getByRole('region',{name:'후보 상세'}).getByRole('button',{name:'검증 정보 보기'}).click();
 let detail=page.locator('#research-drawer');
 assert.ok((await detail.textContent()).includes('합성 공동체'));
 assert.equal(await detail.locator('.fact').filter({has:page.getByText('공동체 참조의 역할',{exact:true})}).locator('dd').textContent(),'자기 설명');
 await page.locator('#drawer-close').click();
 await page.unroute('**/api/candidates**');
 const targetFields={...selfFields,community_name:{value:'합성 평가 대상',status:'recorded_unverified',relationship_role:'target'}};
 await page.route('**/api/candidates**',route=>reply(route,payload([row({community_role:'self',candidate_metadata:targetFields})])));
 await page.getByRole('button',{name:'초기화'}).click();await page.locator('.candidate').first().waitFor();await page.locator('.candidate').first().click();
 await page.getByRole('region',{name:'후보 상세'}).getByRole('button',{name:'검증 정보 보기'}).click();
 detail=page.locator('#research-drawer');
 assert.ok((await detail.textContent()).includes('합성 평가 대상'));
 assert.equal(await detail.locator('.fact').filter({has:page.getByText('공동체 참조의 역할',{exact:true})}).locator('dd').textContent(),'평가 대상');
 await page.locator('#drawer-close').click();
});

test('공동체 역할이 없거나 허용되지 않으면 위조된 이름과 원본 역할을 가린다',async()=>{
 for(const role of [undefined,'speaker','self_and_target']) {
  await page.unroute('**/api/candidates**');
  const fields={...row().candidate_metadata,community_name:{value:'SYNTHETIC-UNLINKED-COMMUNITY',status:'recorded_unverified',relationship_role:role}};
  await page.route('**/api/candidates**',route=>reply(route,payload([row({community_role:'target',candidate_metadata:fields})])));
  await page.getByRole('button',{name:'초기화'}).click();await page.locator('.candidate').first().waitFor();await page.locator('.candidate').first().click();
  await page.getByRole('region',{name:'후보 상세'}).getByRole('button',{name:'검증 정보 보기'}).click();
  const detail=page.locator('#research-drawer');
  assert.equal(await page.getByText('SYNTHETIC-UNLINKED-COMMUNITY',{exact:true}).count(),0);
  assert.equal(await detail.locator('.fact').filter({has:page.getByText('공동체 참조의 역할',{exact:true})}).locator('dd').textContent(),'역할 미확인');
  assert.ok((await detail.textContent()).includes('공동체의 발화·대상 역할 미확인'));
  await page.locator('#drawer-close').click();
 }
});

test('후보 필드의 수신기 길이 한도를 화면에도 동일하게 적용한다',async()=>{
 const longTitle='제'.repeat(1024), longCreator='자'.repeat(512);
 await page.unroute('**/api/candidates**');
 const allowed={...row().candidate_metadata,source_title:{value:longTitle,status:'recorded_unverified'},source_creator:{value:longCreator,status:'recorded_unverified'}};
 await page.route('**/api/candidates**',route=>reply(route,payload([row({candidate_metadata:allowed})])));
 await page.getByRole('button',{name:'초기화'}).click();const candidate=page.locator('.candidate').first();await candidate.waitFor();
 const text=await candidate.textContent();assert.ok(text.includes(longTitle));assert.ok(text.includes(longCreator));
 await page.unroute('**/api/candidates**');
 const invalid={...allowed,source_title:{value:longTitle+'제',status:'recorded_unverified'},source_creator:{value:longCreator+'자',status:'recorded_unverified'}};
 await page.route('**/api/candidates**',route=>reply(route,payload([row({candidate_metadata:invalid})])));
 await page.getByRole('button',{name:'초기화'}).click();await page.getByText('서지 제목 표시 보류',{exact:true}).waitFor();
 assert.ok(!(await page.locator('.candidate').first().textContent()).includes(longCreator));
});
