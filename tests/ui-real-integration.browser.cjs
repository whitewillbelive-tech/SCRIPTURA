// Synthetic-only D16 integration tests: no research data or archives.
const {test,before,after}=require('node:test');
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
const {spawn}=require('node:child_process');
const path=require('node:path');
const root=path.resolve(__dirname,'..'),secret='synthetic-only-session-secret-123';
const selected={corpus:'synthetic-corpus',scheme:'synthetic-scheme',reference:'synthetic-address'};
const sets=[{key:'d16:comparison_sets:1',...selected,claim_count:2,status:'recorded_unverified'},
 {key:'d16:comparison_sets:2',corpus:'other',scheme:'other',reference:'other',claim_count:2,status:'pending'}];
const metadata={source_title:{value:'SYNTHETIC-TITLE',status:'recorded_unverified'},source_creator:{value:'SYNTHETIC-AUTHOR',status:'recorded_unverified'}};
const row={key:'d14:claims:1',stage:'d14',record_kind:'claim',source_key:'d14:sources:1',candidate_metadata:metadata,
 summary:'SYNTHETIC-SUMMARY',summary_status:'recorded_unverified',reasoning:'SYNTHETIC-REASONING',reasoning_status:'recorded_unverified',subject:'SYNTHETIC-SUBJECT',subject_status:'source_confirmed',reported_speaker:'<img src=x onerror=alert(1)>',reported_speaker_status:'recorded_unverified'};
let browser,page,server,base,query;
const reply=(route,data)=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(data)});
before(async()=>{
 server=spawn(process.env.PYTHON||'python3',[path.join(root,'tests/j2_preview_test_server.py')],{cwd:root,env:{...process.env,SCRIPTURA_TEST_SECRET:secret},stdio:['ignore','pipe','pipe']});
 base=await new Promise((resolve,reject)=>{let out='';const timer=setTimeout(()=>reject(Error('synthetic server timeout')),15000);server.stdout.on('data',x=>{out+=x;const m=out.match(/READY (http:\/\/127\.0\.0\.1:\d+)/);if(m){clearTimeout(timer);resolve(m[1]);}});server.once('exit',()=>reject(Error('synthetic server exited')));});
 browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||undefined,args:['--no-sandbox']});page=await browser.newPage();
 await page.route('**/api/candidates**',r=>reply(r,{dataset:'D16',metadata_projection:'k1.3-local-candidate',records:[row],total:1,page_size:100}));
 await page.route('**/api/comparison**',r=>{const p=new URL(r.request().url()).searchParams;query=p;const payload={dataset:'D16',passages:[{...selected,claim_count:2}],comparison_sets:sets,claims:[]};
  if(p.has('reference'))Object.assign(payload,{selected,claims:[row],metadata_projection:'k1.3-local-candidate',summary_projection:'k2-reviewed-summary',reasoning_projection:'k37-reviewed-reasoning',subject_projection:'k37-reviewed-subject',reported_speaker_projection:'k37-recorded-speaker'});return reply(r,payload);});
 await page.goto(base,{waitUntil:'networkidle'});await page.getByLabel('세션 비밀').fill(secret);await page.getByRole('button',{name:'세션 열기'}).click();await page.locator('.candidate').first().waitFor();
});
after(async()=>{if(browser)await browser.close();if(server)server.kill('SIGTERM');});
test('1280×720에서 비교 결과와 상세 버튼을 마우스로 접근한다',async()=>{
 const p=await browser.newPage({viewport:{width:1280,height:720}});
 try {
  await p.route('**/api/candidates**',r=>reply(r,{dataset:'D16',metadata_projection:'k1.3-local-candidate',records:[row],total:1,page_size:100}));
  await p.route('**/api/comparison**',r=>{const query=new URL(r.request().url()).searchParams;
   const data={dataset:'D16',passages:[{...selected,claim_count:2}],comparison_sets:sets,claims:[]};
   if(query.has('reference'))Object.assign(data,{selected,claims:[row,{...row,key:'d14:claims:2'}],metadata_projection:'k1.3-local-candidate',summary_projection:'k2-reviewed-summary',reasoning_projection:'k37-reviewed-reasoning',subject_projection:'k37-reviewed-subject',reported_speaker_projection:'k37-recorded-speaker'});
   return reply(r,data);
  });
  await p.goto(base,{waitUntil:'networkidle'});await p.getByLabel('세션 비밀').fill(secret);await p.getByRole('button',{name:'세션 열기'}).click();await p.locator('.candidate').first().waitFor();
  await p.getByRole('button',{name:'본문 비교',exact:true}).click();await p.getByText(/본문 주소 1개/).waitFor();
  await p.locator('#comparison-corpus').selectOption(selected.corpus);await p.locator('#comparison-scheme').selectOption(selected.scheme);await p.locator('#comparison-reference').selectOption(selected.reference);
  await p.getByRole('button',{name:'해석 비교',exact:true}).click();await p.locator('.comparison-card').nth(1).waitFor();
  assert.ok(await p.locator('#comparison-results').evaluate(e=>e.clientHeight>=100));
  await p.locator('.comparison-card').first().getByRole('button',{name:'검증 정보 보기'}).click({timeout:5000});
  assert.equal(await p.locator('#research-drawer').evaluate(e=>e.open),true);
 } finally {await p.close()}
});
test('D16 단계 및 정확 주소의 안전 비교 묶음만 선택한다',async()=>{
 await page.getByRole('button',{name:'본문 비교',exact:true}).click();await page.getByText(/본문 주소 1개/).waitFor();
 await page.locator('#comparison-corpus').selectOption(selected.corpus);await page.locator('#comparison-scheme').selectOption(selected.scheme);await page.locator('#comparison-reference').selectOption(selected.reference);
 assert.equal(await page.locator('#comparison-set option').count(),2);
 await page.locator('#comparison-set').selectOption('d16:comparison_sets:1');await page.getByRole('button',{name:'해석 비교',exact:true}).click();
 await page.getByText('선택한 본문의 연구 후보 1건',{exact:true}).waitFor();assert.equal(query.get('comparison_set'),'d16:comparison_sets:1');
 assert.ok((await page.locator('.comparison-card').textContent()).includes('SYNTHETIC-REASONING'));
 assert.ok((await page.locator('.comparison-card').textContent()).includes('SYNTHETIC-SUBJECT'));
 assert.ok((await page.locator('.comparison-card').textContent()).includes('원본 발화자 표기 · 귀속 미확인: <img src=x onerror=alert(1)>'));
 assert.equal(await page.locator('.comparison-card img').count(),0);
});
test('검증 표시 없는 논거와 주체는 위조해도 가려진다',async()=>{
 await page.unroute('**/api/comparison**');
 await page.route('**/api/comparison**',r=>reply(r,{dataset:'D16',passages:[{...selected,claim_count:1}],selected,claims:[row],metadata_projection:'k1.3-local-candidate'}));
 await page.getByRole('button',{name:'해석 비교',exact:true}).click();await page.getByText('선택한 본문의 연구 후보 1건',{exact:true}).waitFor();
 const content=await page.locator('.comparison-card').textContent();
 assert.ok(content.includes('논거 확인 대기'));assert.ok(content.includes('해석 주체 미확인'));
 assert.ok(!content.includes('SYNTHETIC-REASONING'));assert.ok(!content.includes('SYNTHETIC-SUBJECT'));assert.ok(!content.includes('onerror=alert(1)'));
});
test('다른 코퍼스 선택시 이전 묶음을 지운다',async()=>{
 await page.locator('#comparison-corpus').selectOption('');assert.equal(await page.locator('#comparison-set option').count(),1);assert.equal(await page.locator('.comparison-card').count(),0);
});
test('봉인된 전통 라벨만 공동체 필터 검색을 허용한다',async()=>{
 await page.unroute('**/api/candidates**');let requests=0;let marker=true;
 await page.route('**/api/candidates**',r=>{requests++;return reply(r,{dataset:'D16',metadata_projection:'k1.3-local-candidate',tradition_projection:marker?'k2-reviewed-tradition':null,metadata_coverage:{community_name:0,source_creator:1,tradition:1},records:[row],total:1,page_size:100});});
 await page.reload();await page.getByLabel('세션 비밀').fill(secret);await page.getByRole('button',{name:'세션 열기'}).click();await page.locator('.candidate').first().waitFor();
 await page.locator('#advanced-filters summary').click();await page.locator('input[name="community"]').fill('SYNTHETIC-TRADITION');
 const before=requests;await page.getByRole('button',{name:'후보 검색'}).click();await page.waitForResponse(r=>r.url().includes('community=SYNTHETIC-TRADITION'));assert.equal(requests,before+1);
 marker=false;await page.reload();await page.getByLabel('세션 비밀').fill(secret);await page.getByRole('button',{name:'세션 열기'}).click();await page.locator('.candidate').first().waitFor();
 await page.locator('#advanced-filters summary').click();await page.locator('input[name="community"]').fill('SYNTHETIC-TRADITION');const blocked=requests;
 await page.getByRole('button',{name:'후보 검색'}).click();await page.getByText('검색 보류',{exact:true}).waitFor();assert.equal(requests,blocked);
});
