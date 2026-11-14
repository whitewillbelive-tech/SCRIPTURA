// Synthetic-only comparison tests; no research archive or values.
const {test,before,after} = require('node:test');
const assert = require('node:assert/strict');
const {chromium} = require('playwright');
const {spawn} = require('node:child_process');
const path = require('node:path');
const root = path.resolve(__dirname,'..');
const secret = 'synthetic-only-session-secret-123';
const fields = (title, creator) => ({
  source_title:{value:title,status:'recorded_unverified'},
  source_creator:{value:creator,status:'recorded_unverified'},
  source_publisher:{value:null,status:'missing_or_unmapped'},
  source_year:{value:null,status:'missing_or_unmapped'},
  community_name:{value:null,status:'missing_or_unmapped'},
});
const row = (n, attribution, title, creator) => ({
  key:`d12:claims:${n}`,stage:'d12',record_kind:'claim',source_key:`d12:sources:${n}`,attribution,
  candidate_metadata:fields(title,creator),source_verification_status:'unconfirmed',
  authority_status:'pending_authority',verification_status:'source_checked',
  independent_review_status:'pending',argument_status:'not_assessed',
  summary:'SYNTHETIC-PROTECTED-SUMMARY',summary_status:'pending_review',
});
const claims = [row(1,'community_self_explanation','합성 문헌 1','합성 작성자 1'),
                row(2,'external_critique','합성 문헌 2','합성 작성자 2')];
const selected={corpus:'synthetic-corpus',scheme:'synthetic-scheme',reference:'synthetic-address'};
const passages=[{...selected,claim_count:2},{corpus:'other-corpus',scheme:'other-scheme',reference:'other-address',claim_count:1},{corpus:'other-corpus',scheme:'other-scheme',reference:'empty-address',claim_count:0}];
const candidatePayload = {dataset:'D12',metadata_projection:'k1.3-local-candidate',records:[claims[0]],total:1,page_size:100,
 metadata_coverage:{source_title:1,source_creator:1,source_publisher:0,source_year:0,community_name:0}};
let browser,page,server,base;
async function waitReady(proc) {return new Promise((resolve,reject)=>{let out='',err='';const timer=setTimeout(()=>reject(new Error('synthetic server timeout')),15000);
 proc.stdout.on('data',c=>{out+=c;const match=out.match(/READY (http:\/\/127\.0\.0\.1:\d+)/);if(match){clearTimeout(timer);resolve(match[1]);}});
 proc.stderr.on('data',c=>{err+=c;});proc.once('exit',code=>{clearTimeout(timer);reject(new Error(`synthetic server exited ${code}: ${err}`));});});}
const reply = (route,data,status=200) => route.fulfill({status,contentType:'application/json; charset=utf-8',body:JSON.stringify(data)});
before(async()=>{
 server=spawn(process.env.PYTHON||'python3',[path.join(root,'tests/j2_preview_test_server.py')],{cwd:root,env:{...process.env,SCRIPTURA_TEST_SECRET:secret},stdio:['ignore','pipe','pipe']});
 base=await waitReady(server);browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||undefined,args:['--no-sandbox']});
 page=await browser.newPage();await page.goto(base,{waitUntil:'networkidle'});
 await page.route('**/api/candidates**',route=>reply(route,candidatePayload));
 await page.getByLabel('세션 비밀').fill(secret);await page.getByRole('button',{name:'세션 열기'}).click();
 await page.locator('.candidate').first().waitFor();
});
after(async()=>{if(browser)await browser.close();if(server)server.kill('SIGTERM');});
async function choose() {
 await page.locator('#comparison-corpus').selectOption(selected.corpus);
 await page.locator('#comparison-scheme').selectOption(selected.scheme);
 await page.locator('#comparison-reference').selectOption(selected.reference);
 await page.getByRole('button',{name:'해석 비교',exact:true}).click();
}
test('코퍼스·장절체계·주소를 선택해 두 해석을 나란히 본다',async()=>{
 let selectedQuery;
 await page.route('**/api/comparison**',route=>{const url=new URL(route.request().url());if(url.searchParams.has('reference')){selectedQuery=url.searchParams;return reply(route,{dataset:'D12',metadata_projection:'k1.3-local-candidate',passages,selected,claims});}return reply(route,{dataset:'D12',passages,selected:null,claims:[]});});
 await page.getByRole('button',{name:'본문 비교',exact:true}).click();
 await page.getByText(/본문 주소 3개/).waitFor();await choose();
 await page.getByText('선택한 본문의 연구 후보 2건',{exact:true}).waitFor();
 assert.equal(selectedQuery.get('stage'),'d12');assert.equal(selectedQuery.get('corpus'),selected.corpus);assert.equal(selectedQuery.get('scheme'),selected.scheme);assert.equal(selectedQuery.get('reference'),selected.reference);
 const cards=page.locator('.comparison-card');assert.equal(await cards.count(),2);
 for(const phrase of ['합성 문헌 1','합성 작성자 1','해석 주체 미확인','핵심 해석','논거 확인 대기','표시 보류']) assert.ok((await cards.nth(0).textContent()).includes(phrase));
 await cards.nth(0).getByRole('button',{name:'검증 정보 보기'}).click();
 for(const phrase of ['공동체 자기 설명','출처 확인','공식성','논증 검토','독립 학술 심사','별도 승인 필요']) assert.ok((await page.locator('#research-drawer').textContent()).includes(phrase));
 await page.locator('#drawer-close').click();
 await cards.nth(1).getByRole('button',{name:'검증 정보 보기'}).click();assert.ok((await page.locator('#research-drawer').textContent()).includes('외부 비평'));await page.locator('#drawer-close').click();
 assert.equal(await page.getByText('SYNTHETIC-PROTECTED-SUMMARY',{exact:true}).count(),0);
 assert.ok((await page.getByLabel('본문별 해석 비교').textContent()).includes('직접 반박의 근거가 아닙니다'));
});
test('비교 카드에서 연결된 문헌 상세로 이동할 수 있다',async()=>{
 const source={...claims[0],key:'d12:sources:1',record_kind:'source'};
 await page.unroute('**/api/candidates**');
 await page.route('**/api/candidates**',route=>reply(route,{...candidatePayload,records:[source]}));
 await page.locator('.comparison-card').first().getByRole('button',{name:'연결 문헌 보기'}).click();
 await page.locator('#research-drawer').getByText('합성 문헌 1',{exact:true}).first().waitFor();
 await page.locator('#drawer-close').click();
 await page.getByText('선택한 본문의 연구 후보 2건',{exact:true}).waitFor();
});
test('자료 범위를 전체로 바꾸면 단계 필터 없이 본문을 조회한다',async()=>{
 await page.unroute('**/api/comparison**');let requested;
 await page.route('**/api/comparison**',route=>{requested=new URL(route.request().url()).searchParams;return reply(route,{dataset:'D12',passages,selected:null,claims:[]});});
 await page.locator('#comparison-stage').selectOption('');
 await page.getByText(/본문 주소 3개/).waitFor();assert.equal(requested.has('stage'),false);
 await page.locator('#comparison-stage').selectOption('d12');
 await page.getByText(/본문 주소 3개/).waitFor();
 await page.locator('#comparison-corpus').selectOption(selected.corpus);
 await page.locator('#comparison-scheme').selectOption(selected.scheme);
 await page.locator('#comparison-reference').selectOption(selected.reference);
});
test('주장이 없는 본문도 보이고 선택 시 0건을 표시한다',async()=>{
 await page.unroute('**/api/comparison**');
 const emptySelected={corpus:'other-corpus',scheme:'other-scheme',reference:'empty-address'};
 await page.route('**/api/comparison**',route=>reply(route,{dataset:'D12',passages,selected:emptySelected,claims:[]}));
 await page.locator('#comparison-corpus').selectOption(emptySelected.corpus);
 await page.locator('#comparison-scheme').selectOption(emptySelected.scheme);
 await page.locator('#comparison-reference').selectOption(emptySelected.reference);
 await page.getByRole('button',{name:'해석 비교',exact:true}).click();
 await page.getByText('선택한 본문에 표시할 연구 후보가 없습니다.',{exact:true}).waitFor();
 assert.equal(await page.locator('.comparison-card').count(),0);
 await page.locator('#comparison-corpus').selectOption(selected.corpus);
 await page.locator('#comparison-scheme').selectOption(selected.scheme);
 await page.locator('#comparison-reference').selectOption(selected.reference);
});
test('불일치한 선택이나 다른 데이터셋의 응답을 표시하지 않는다',async()=>{
 await page.unroute('**/api/comparison**');await page.route('**/api/comparison**',route=>reply(route,{dataset:'D9',passages,selected,claims}));
 await page.getByRole('button',{name:'해석 비교',exact:true}).click();
 await page.getByText(/본문 비교를 불러오지 못했습니다/).waitFor();assert.equal(await page.locator('.comparison-card').count(),0);
});
test('검토된 요지 표식과 상태가 모두 있는 경우만 텍스트로 표시한다',async()=>{
 const unsafe='<img src=x onerror="window.__k2xss=true">';
 const first={...claims[0],summary:unsafe,summary_status:'recorded_unverified'};
 const second={...claims[1],summary:'SYNTHETIC-RESTRICTED-SUMMARY',summary_status:'pending_review'};
 await page.unroute('**/api/comparison**');
 await page.route('**/api/comparison**',route=>reply(route,{dataset:'D12',metadata_projection:'k1.3-local-candidate',summary_projection:'k2-reviewed-summary',passages,selected,claims:[first,second]}));
 await page.getByRole('button',{name:'해석 비교',exact:true}).click();
 await page.getByText('선택한 본문의 연구 후보 2건',{exact:true}).waitFor();
 const cards=page.locator('.comparison-card');
 assert.ok((await cards.nth(0).textContent()).includes(unsafe));
 assert.ok((await cards.nth(0).textContent()).includes('원본 기록 · 독립 확인 전'));
 assert.equal(await page.getByText('SYNTHETIC-RESTRICTED-SUMMARY',{exact:true}).count(),0);
 assert.equal(await page.evaluate(()=>window.__k2xss === true),false);
 assert.equal(await page.locator('#comparison-results img').count(),0);
});
test('안전 투영된 원본 전통 라벨만 표시·필터하고 공식 귀속으로 단정하지 않는다',async()=>{
 const tradition='합성 전통';let chosen;
 const projected=[{...claims[0],tradition_candidate:{value:tradition,status:'recorded_unverified'}}];
 await page.unroute('**/api/comparison**');
 await page.route('**/api/comparison**',route=>{
  const params=new URL(route.request().url()).searchParams;
  if(params.has('reference')){chosen=params.get('tradition');return reply(route,{dataset:'D12',metadata_projection:'k1.3-local-candidate',tradition_projection:'k2-reviewed-tradition',passages,selected,claims:projected});}
  return reply(route,{dataset:'D12',tradition_projection:'k2-reviewed-tradition',traditions:[{value:tradition,claim_count:1}],passages,selected:null,claims:[]});
 });
 await page.getByRole('button',{name:'본문 비교',exact:true}).click();
 await page.getByText(/본문 주소 3개/).waitFor();
 await page.locator('#comparison-corpus').selectOption(selected.corpus);
 await page.locator('#comparison-scheme').selectOption(selected.scheme);
 await page.locator('#comparison-reference').selectOption(selected.reference);
 await page.locator('#comparison-tradition').selectOption(tradition);
 await page.getByRole('button',{name:'해석 비교',exact:true}).click();
 await page.getByText('선택한 본문의 연구 후보 1건',{exact:true}).waitFor();
 assert.equal(chosen,tradition);
 await page.locator('.comparison-card').first().getByRole('button',{name:'검증 정보 보기'}).click();
 const card=await page.locator('#research-drawer').textContent();
 assert.ok(card.includes(tradition));assert.ok(card.includes('귀속 및 공식성 미확인'));await page.locator('#drawer-close').click();
 await page.unroute('**/api/comparison**');
 await page.route('**/api/comparison**',route=>reply(route,{dataset:'D12',metadata_projection:'k1.3-local-candidate',passages,selected,claims:projected}));
 await page.getByRole('button',{name:'해석 비교',exact:true}).click();
 await page.getByText('선택한 본문의 연구 후보 1건',{exact:true}).waitFor();
 assert.equal(await page.locator('.comparison-card').getByText(tradition,{exact:true}).count(),0);
 await page.locator('#comparison-tradition').selectOption('');
});
test('선택 변경과 지연 응답은 기존 비교 결과를 지운다',async()=>{
 await page.unroute('**/api/comparison**');let release;
 await page.route('**/api/comparison**',async route=>{await new Promise(resolve=>{release=resolve});try{await reply(route,{dataset:'D12',metadata_projection:'k1.3-local-candidate',passages,selected,claims});}catch{}});
 await page.getByRole('button',{name:'해석 비교',exact:true}).click();
 for(let i=0;i<50&&!release;i++) await page.waitForTimeout(20);
 assert.equal(typeof release,'function');
 await page.locator('#comparison-corpus').selectOption('other-corpus');release();
 await page.waitForTimeout(100);assert.equal(await page.locator('.comparison-card').count(),0);
});
test('세션 닫기 후 비교 결과와 선택값을 지운다',async()=>{
 await page.getByRole('button',{name:'세션 닫기'}).click();
 assert.equal(await page.locator('.comparison-card').count(),0);
 assert.equal(await page.locator('#comparison-corpus').inputValue(),'');
});
