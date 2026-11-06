// Fictional records only. Uses a disposable schema and separate temporary roles.
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { randomBytes } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { createServer } from 'node:net';
import { spawn } from 'node:child_process';
import pg from 'pg';

const original=process.env.DATABASE_URL;
if (!original) throw new Error('DATABASE_URL must identify a disposable test DB with role/schema creation rights');
const suffix=randomBytes(8).toString('hex');
const schema=`i2_api_${suffix}`, legacyRole=`i2_legacy_${suffix}`, viewRole=`i2_view_${suffix}`;
const password=randomBytes(32).toString('hex');
const schemaUrl=new URL(original);schemaUrl.searchParams.set('options',`-c search_path=${schema}`);
const legacyUrl=new URL(schemaUrl);legacyUrl.username=legacyRole;legacyUrl.password=password;
const viewUrl=new URL(schemaUrl);viewUrl.username=viewRole;viewUrl.password=password;
const admin=new pg.Pool({connectionString:original}), db=new pg.Pool({connectionString:schemaUrl.toString()});
let server,base,schemaCreated=false,legacyCreated=false,viewCreated=false;
async function api(path) { const res=await fetch(`${base}/api/v1/${path}`);return {status:res.status,body:await res.json()}; }
before(async()=>{
  await admin.query(`CREATE SCHEMA "${schema}"`);schemaCreated=true;
  for(const file of ['001_schema.sql','002_append_only.sql','003_research_integrity.sql','006_authority_evidence.sql']) { let sql=await readFile(`db/${file}`,'utf8'); if(file==='003_research_integrity.sql') sql=sql.replaceAll('SET search_path = pg_catalog, public', `SET search_path = pg_catalog, "${schema}"`); await db.query(sql); }
  await db.query(`
    INSERT INTO corpora(id,name,corpus_kind,data_class) VALUES ('c','Fictional','other','scholarly_candidate'),('cs','Synthetic','other','synthetic');
    INSERT INTO works(id,corpus_id,title,data_class) VALUES ('w','c','Fictional','scholarly_candidate'),('ws','cs','Synthetic','synthetic');
    INSERT INTO reference_schemes(id,corpus_id,scheme_name,data_class) VALUES ('rs','c','Fictional','scholarly_candidate'),('rss','cs','Synthetic','synthetic');
    INSERT INTO passages(id,corpus_id,work_id,scheme_id,external_ref,granularity,data_class) VALUES ('p','c','w','rs','1.1','verse','scholarly_candidate'),('p2','c','w','rs','1.2','verse','scholarly_candidate');
    UPDATE corpora SET description='I2_SECRET_SENTINEL_CORPUS' WHERE id='c';
    UPDATE passages SET location_expression='"I2_SECRET_SENTINEL_LOCATION"'::jsonb;
    INSERT INTO traditions(id,name,classification_kind,data_class) VALUES ('t','Fictional tradition','school','scholarly_candidate'),('ts','Synthetic tradition','school','synthetic');
    INSERT INTO agents(id,display_name,agent_kind,data_class) VALUES ('org','Fictional org','institution','scholarly_candidate');
    INSERT INTO sources(id,title,source_kind,storage_policy,license_status,data_class) VALUES ('s','Fictional source','other','metadata_only','unknown','scholarly_candidate');
    INSERT INTO source_locators(id,source_id,locator_type,locator_value) VALUES ('l','s','section','I2_SECRET_SENTINEL_LOCATOR');
    INSERT INTO claims(id) VALUES ('c1'),('c2'),('cs');
    INSERT INTO claim_versions(id,claim_id,revision_no,statement,interpretive_method,extraction_method,review_status,revision_reason,data_class) VALUES
      ('v1','c1',1,'I2_SECRET_SENTINEL_CLAIM','I2_SECRET_SENTINEL_METHOD','human','extracted','test','scholarly_candidate'),
      ('v2','c2',1,'I2_SECRET_SENTINEL_OTHER',NULL,'human','extracted','test','scholarly_candidate'),
      ('vs','cs',1,'Fictional synthetic claim',NULL,'human','extracted','test','synthetic');
    INSERT INTO claim_passages(id,claim_version_id,passage_id,link_kind) VALUES ('cp1','v1','p','discusses'),('cp2','v2','p','discusses');
    INSERT INTO claim_attributions(id,claim_version_id,agent_id,attribution_kind,attribution_status) VALUES ('attr','v1','org','official_doctrine','unverified');
    INSERT INTO claim_evidence(id,claim_version_id,source_locator_id,evidence_role,explanation,review_status) VALUES ('e','v1','l','context','I2_SECRET_SENTINEL_EVIDENCE','proposed');
    INSERT INTO passage_alignments(id,from_passage_id,to_passage_id,alignment_type,source_locator_id,rationale) VALUES ('pa','p','p2','partial','l','I2_SECRET_SENTINEL_ALIGNMENT');
    INSERT INTO passage_relations(id,from_passage_id,to_passage_id,relation_type,source_locator_id,rationale) VALUES ('pr','p','p2','parallel','l','I2_SECRET_SENTINEL_PASSAGE_REL');
    INSERT INTO claim_relations(id,from_version_id,to_version_id,relation_type,source_locator_id,rationale) VALUES ('cr','v1','v2','supports','l','I2_SECRET_SENTINEL_CLAIM_REL');
    INSERT INTO authority_attestations(id,claim_version_id,tradition_id,authority_kind,position_scope,perspective,quotation_status,authority_status,statement,uncertainty,data_class) VALUES
      ('unsafe','v1','t','normative_adopted','documented_group_position','unknown','unchecked','unknown','I2_SECRET_SENTINEL_AUTHORITY','I2_SECRET_SENTINEL_UNCERTAINTY','scholarly_candidate'),
      ('synth','vs','ts','plural_or_unresolved','insufficient_evidence','unknown','unchecked','unknown','Synthetic fictional sample','Synthetic uncertainty','synthetic');
  `);
  // Reuse the independently exercised DB fixture, without its mutation tests or transaction.
  const fullSeed=await readFile('tests/i2_authority_db.sql','utf8');
  const verifiedSeed=fullSeed.slice(fullSeed.indexOf('INSERT INTO traditions'),fullSeed.indexOf('CREATE FUNCTION pg_temp.rejected')).replaceAll("'org'", "'verified_org'").replaceAll("'attr'", "'verified_attr'");
  await db.query(verifiedSeed + '\nINSERT INTO authority_attestations SELECT * FROM probe;');
  await admin.query(`CREATE ROLE "${legacyRole}" LOGIN PASSWORD '${password}'`);legacyCreated=true;
  await admin.query(`CREATE ROLE "${viewRole}" LOGIN PASSWORD '${password}'`);viewCreated=true;
  await db.query(`GRANT USAGE ON SCHEMA "${schema}" TO "${legacyRole}","${viewRole}"`);
  await db.query(`GRANT SELECT ON corpora,works,reference_schemes,passages,traditions,agents,sources,source_locators,passage_alignments,agent_affiliations,claims,claim_versions,claim_attributions,claim_passages,claim_evidence,claim_relations,passage_relations TO "${legacyRole}"`);
  await db.query(`GRANT SELECT ON authority_safe_readings TO "${viewRole}"`);
  await db.query(`GRANT EXECUTE ON FUNCTION authority_safe_rows() TO "${viewRole}"`);
  const probe=createServer();await new Promise((resolve,reject)=>{probe.once('error',reject);probe.listen(0,'127.0.0.1',resolve);});
  const port=probe.address().port;await new Promise((resolve,reject)=>probe.close(e=>e?reject(e):resolve()));
  base=`http://127.0.0.1:${port}`;
  const environment={...process.env,DATABASE_URL:legacyUrl.toString(),DATABASE_AUTHORITY_URL:viewUrl.toString(),NEXT_TELEMETRY_DISABLED:'1'};
  delete environment.SCRIPTURA_REVIEW_DATABASE_URL;
  server=spawn(process.execPath,['node_modules/next/dist/bin/next','dev','-H','127.0.0.1','-p',String(port)],{env:environment,stdio:'ignore'});
  const deadline=Date.now()+60000;
  while(Date.now()<deadline){ if(server.exitCode!==null)throw new Error(`server exited ${server.exitCode}`);try{if((await fetch(base+'/api/v1/passages',{signal:AbortSignal.timeout(3000)})).ok)return;}catch{} await new Promise(r=>setTimeout(r,200)); }
  throw new Error('server startup timeout');
});
after(async()=>{
  if(server&&server.exitCode===null){server.kill('SIGTERM');await new Promise(r=>{server.once('exit',r);setTimeout(r,3000).unref();});}
  await db.end();if(schemaCreated)await admin.query(`DROP SCHEMA "${schema}" CASCADE`);
  if(legacyCreated)await admin.query(`DROP ROLE "${legacyRole}"`);if(viewCreated)await admin.query(`DROP ROLE "${viewRole}"`);await admin.end();
});

test('separate view-only authority role cannot read or alter raw records',async()=>{
  const c=new pg.Pool({connectionString:viewUrl.toString()});try{
    assert.equal((await c.query('SELECT count(*)::int AS n FROM authority_safe_readings')).rows[0].n,3);
    await assert.rejects(c.query('SELECT * FROM authority_attestations'),/permission denied/);
    await assert.rejects(c.query('SELECT * FROM authority_documents'),/permission denied/);
    await assert.rejects(c.query('SELECT * FROM authority_readings'),/permission denied/);
    await assert.rejects(c.query("UPDATE authority_attestations SET statement='bad'"),/permission denied/);
  }finally{await c.end();}
});
test('research authority response downgrades raw official labels and masks free text',async()=>{
  const r=await api('authority?dataset=database&include_unverified=true');assert.equal(r.status,200);assert.equal(r.body.positions.length,1);
  const p=r.body.positions[0];assert.equal(p.kind,'plural_or_unresolved');assert.equal(p.authority_status,'unknown');assert.equal(p.assessment,'insufficient_evidence');
  assert.ok(Object.values(p.rights).every(v=>v===false));assert.doesNotMatch(JSON.stringify(r.body),/I2_SECRET_SENTINEL/);
  const f=await api('authority?dataset=database&include_unverified=true&kind=normative_adopted');assert.equal(f.status,200);assert.deepEqual(f.body.positions,[]);
});
test('synthetic database mode is explicit and cannot mix real and synthetic records',async()=>{
  const r=await api('authority?dataset=database&data_mode=synthetic&include_unverified=true');assert.equal(r.status,200);assert.equal(r.body.dataset_kind,'synthetic');
  assert.deepEqual(r.body.positions.map(p=>p.id),['original','synth']);assert.match(r.body.warning,/합성/);assert.equal(r.body.positions.find(p=>p.id==='synth').summary,'Synthetic fictional sample');
});
test('legacy claim, search, graph and alignment paths redact unapproved free text and unproven official classification',async()=>{
  const one=await api('claims/v1?dataset=database&include_unverified=true');assert.equal(one.status,200);assert.equal(one.body.claim.attributions[0].attribution_kind,'unconfirmed_authority');assert.doesNotMatch(JSON.stringify(one.body),/I2_SECRET_SENTINEL/);
  const listed=await api('passages/p/interpretations?dataset=database&include_unverified=true&attribution_kind=official_doctrine');assert.equal(listed.status,200);assert.deepEqual(listed.body.interpretations,[]);
  const graph=await api('graph?dataset=database&passage_id=p&include_unverified=true');assert.equal(graph.status,200);assert.doesNotMatch(JSON.stringify(graph.body),/I2_SECRET_SENTINEL/);
  const corpora=await api('corpora?dataset=database');assert.equal(corpora.status,200);assert.doesNotMatch(JSON.stringify(corpora.body),/I2_SECRET_SENTINEL/);
  const passage=await api('passages/p?dataset=database');assert.equal(passage.status,200);assert.doesNotMatch(JSON.stringify(passage.body),/I2_SECRET_SENTINEL/);
  const passages=await api('passages?dataset=database');assert.equal(passages.status,200);assert.doesNotMatch(JSON.stringify(passages.body),/I2_SECRET_SENTINEL/);
  const align=await api('passages/p/alignments?dataset=database&include_unverified=true');assert.equal(align.status,200);assert.doesNotMatch(JSON.stringify(align.body),/I2_SECRET_SENTINEL/);
});
test('invalid authority filters fail closed',async()=>{
  assert.equal((await api('authority?as_of=2025-02-30')).status,400);
  assert.equal((await api('authority?kind=official_doctrine')).status,400);
});
test('a view role with a raw column-level grant is rejected by the API',async()=>{
  await db.query(`GRANT SELECT (statement) ON authority_attestations TO "${viewRole}"`);
  try { const r=await api('authority?dataset=database&include_unverified=true');assert.equal(r.status,503); }
  finally { await db.query(`REVOKE SELECT (statement) ON authority_attestations FROM "${viewRole}"`); }
  const restored=await api('authority?dataset=database&include_unverified=true');assert.equal(restored.status,200);
});

test('a view role with role membership is rejected even when privileges are not inherited',async()=>{
  await admin.query(`ALTER ROLE "${viewRole}" NOINHERIT`);
  await admin.query(`GRANT "${legacyRole}" TO "${viewRole}"`);
  try { const r=await api('authority?dataset=database&include_unverified=true');assert.equal(r.status,503); }
  finally { await admin.query(`REVOKE "${legacyRole}" FROM "${viewRole}"`); }
  assert.equal((await api('authority?dataset=database&include_unverified=true')).status,200);
});

test('documented synthetic adoption respects the requested date and a later retraction',async()=>{
  const url='authority?dataset=database&data_mode=synthetic&include_unverified=true&as_of=';
  const valid=await api(url+'2020-01-01');assert.equal(valid.status,200);
  assert.equal(valid.body.positions.find(p=>p.id==='original').authority_status,'adoption_documented');
  const later=await api(url+'2040-01-01');assert.equal(later.body.positions.find(p=>p.id==='original').authority_status,'unknown');
  await db.query(`INSERT INTO authority_attestations SELECT (jsonb_populate_record(NULL::authority_attestations,to_jsonb(a)||'{"id":"api_retraction","supersedes_id":"original","is_retraction":true,"authority_status":"disputed"}'::jsonb)).* FROM authority_attestations a WHERE id='original'`);
  const retracted=await api(url+'2020-01-01');assert.equal(retracted.body.positions.some(p=>p.id==='original'||p.id==='api_retraction'),false);
});
