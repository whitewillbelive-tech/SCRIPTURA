// Synthetic-only session selection tests. Never opens a research archive.
const {test,before,after}=require('node:test');
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
const {spawn}=require('node:child_process');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const secret='synthetic-only-session-secret-123';
let page,browser,server,base;
const selected={corpus:'synthetic-corpus',scheme:'synthetic-scheme',reference:'synthetic-address'};
const passages=[{...selected,claim_count:4},{corpus:'other-corpus',scheme:'other-scheme',reference:'other-address',claim_count:1}];
const fields=(n)=>({source_title:{value:`SYNTHETIC-TITLE-${n}`,status:'recorded_unverified'},source_creator:{value:`SYNTHETIC-CREATOR-${n}`,status:'recorded_unverified'}});
const claims=Array.from({length:4},(_,i)=>({key:`d12:claims:${i+1}`,stage:'d12',record_kind:'claim',source_key:`d12:sources:${i+1}`,candidate_metadata:fields(i+1),summary:'SYNTHETIC-UNAPPROVED-SUMMARY',summary_status:'pending_review'}));
claims[0].source_key='d12:sources:5'; claims[0].passages=[selected];
const source={key:'d12:sources:5',stage:'d12',record_kind:'source',candidate_metadata:fields(5)};
const candidatePayload={dataset:'D12',metadata_projection:'k1.3-local-candidate',records:[claims[2],claims[0],claims[1],claims[3],source],total:5,page_size:100,metadata_coverage:{source_title:5,source_creator:5,source_publisher:0,source_year:0,community_name:0}};
const reply=(route,data)=>route.fulfill({status:200,contentType:'application/json; charset=utf-8',body:JSON.stringify(data)});
before(async()=>{
  server=spawn('python3',[path.join(root,'tests/j2_preview_test_server.py')],{cwd:root,env:{...process.env,SCRIPTURA_TEST_SECRET:secret},stdio:['ignore','pipe','pipe']});
  base=await new Promise((resolve,reject)=>{let out='';const timer=setTimeout(()=>reject(Error('synthetic server timeout')),15000);server.stdout.on('data',chunk=>{out+=chunk;const m=out.match(/READY (http:\/\/127\.0\.0\.1:\d+)/);if(m){clearTimeout(timer);resolve(m[1]);}});server.on('exit',()=>reject(Error('synthetic server failed')));});
  browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||undefined,args:['--no-sandbox']});page=await browser.newPage();
  await page.route('**/api/candidates**',r=>{const p=new URL(r.request().url()).searchParams;return reply(r,p.has('source_key')?{...candidatePayload,records:[claims[0],claims[1]],total:1}:candidatePayload);});
  await page.route('**/api/comparison**',r=>{const p=new URL(r.request().url()).searchParams;return reply(r,p.has('reference')?{dataset:'D12',metadata_projection:'k1.3-local-candidate',passages,selected,claims}:{dataset:'D12',passages,selected:null,claims:[]});});
  await page.goto(base);await page.getByLabel('세션 비밀').fill(secret);await page.getByRole('button',{name:'세션 열기'}).click();await page.locator('.candidate').first().waitFor();
});
after(async()=>{if(browser)await browser.close();if(server)server.kill('SIGTERM');});
test('현재 페이지만 표시된 서지로 정렬하며 선택한 상세는 유지한다',async()=>{
  await page.locator('.candidate').first().click();assert.match(await page.locator('#detail').textContent(),/SYNTHETIC-CREATOR-3/);
  await page.getByLabel('현재 페이지 정렬').selectOption('title');assert.match(await page.locator('.candidate').first().textContent(),/SYNTHETIC-TITLE-1/);assert.match(await page.locator('#detail').textContent(),/SYNTHETIC-CREATOR-3/);assert.match(await page.locator('.candidate[aria-pressed="true"]').textContent(),/SYNTHETIC-TITLE-3/);
  await page.getByLabel('현재 페이지 정렬').selectOption('original');assert.match(await page.locator('.candidate').first().textContent(),/SYNTHETIC-TITLE-3/);
});
test('2~3개를 선택해 해당 카드만 보며 숨긴 요지는 노출하지 않는다',async()=>{
  await page.getByRole('button',{name:'본문 비교',exact:true}).click();await page.getByText(/본문 주소 2개/).waitFor();
  assert.match(await page.locator('#comparison-status').textContent(),/복수 해석 주소 1개 · 본문 연결 5건/);
  await page.locator('#comparison-corpus').selectOption(selected.corpus);await page.locator('#comparison-scheme').selectOption(selected.scheme);await page.locator('#comparison-reference').selectOption(selected.reference);await page.getByRole('button',{name:'해석 비교',exact:true}).click();await page.locator('.comparison-card').nth(3).waitFor();
  const boxes=page.getByLabel('이 해석을 비교 대상으로 선택');const action=page.getByRole('button',{name:'선택한 해석만 보기'});
  assert.equal(await action.isDisabled(),true);await boxes.nth(0).check();await boxes.nth(1).check();await boxes.nth(2).check();assert.equal(await boxes.nth(3).isDisabled(),true);
  await action.click();assert.equal(await page.locator('.comparison-card:visible').count(),3);assert.equal(await page.getByText('SYNTHETIC-UNAPPROVED-SUMMARY').count(),0);
  await page.getByRole('button',{name:'전체 해석 보기'}).click();assert.equal(await page.locator('.comparison-card:visible').count(),4);
});
test('다른 화면을 열었다 돌아와도 선택과 본문 위치를 보존한다',async()=>{
  await page.getByRole('button',{name:'후보 탐색',exact:true}).click();await page.getByRole('button',{name:'본문 비교',exact:true}).click();
  assert.equal(await page.locator('#comparison-reference').inputValue(),selected.reference);assert.equal(await page.getByLabel('이 해석을 비교 대상으로 선택').nth(0).isChecked(),true);assert.equal(await page.locator('.comparison-card').count(),4);
});
test('문헌에서 연결된 본문으로 이동하며 다른 출처의 주장은 거른다',async()=>{
  await page.getByRole('button',{name:'후보 탐색',exact:true}).click();
  await page.locator('.candidate').filter({hasText:'SYNTHETIC-TITLE-5'}).click();
  await page.getByRole('button',{name:'이 문헌의 관련 해석 보기'}).click();
  const drawer=page.locator('#research-drawer');await drawer.getByText(/관련 해석 1건/).waitFor();
  assert.equal(await drawer.getByRole('button',{name:'해석 상세 보기'}).count(),1);
  await drawer.getByRole('button',{name:'이 본문 비교하기'}).click();
  await page.getByText('선택한 본문의 연구 후보 4건',{exact:true}).waitFor();
  assert.equal(await page.locator('#comparison-reference').inputValue(),selected.reference);
  await page.waitForFunction(()=>document.activeElement===document.querySelector('#comparison-corpus'));
});
test('선택 지우기·본문 변경·세션 종료 시 이전 선택과 결과를 비운다',async()=>{
  await page.getByLabel('이 해석을 비교 대상으로 선택').nth(0).focus();
  await page.keyboard.press('Space');assert.equal(await page.getByLabel('이 해석을 비교 대상으로 선택').nth(0).isChecked(),true);
  await page.getByRole('button',{name:'선택 지우기'}).click();assert.equal(await page.getByLabel('이 해석을 비교 대상으로 선택').nth(0).isChecked(),false);
  await page.getByLabel('이 해석을 비교 대상으로 선택').nth(0).check();await page.locator('#comparison-corpus').selectOption('other-corpus');assert.equal(await page.locator('.comparison-card').count(),0);assert.equal(await page.locator('#comparison-selection').isHidden(),true);
  await page.getByRole('button',{name:'세션 닫기'}).click();assert.equal(await page.locator('#comparison-corpus').inputValue(),'');
});
