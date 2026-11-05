// Integration data are fictional test assumptions in a freshly created, disposable schema.
// No records below describe actual people, publications, traditions, or scholarly claims.
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { randomBytes } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { createServer } from 'node:net';
import { spawn } from 'node:child_process';
import pg from 'pg';

const originalUrl = process.env.DATABASE_URL;
if (!originalUrl) throw new Error('DATABASE_URL must point to a disposable PostgreSQL database where test schemas can be created');
const schema = `scriptura_test_${randomBytes(8).toString('hex')}`;
const schemaUrl = new URL(originalUrl);
schemaUrl.searchParams.set('options', `-c search_path=${schema}`);
const suffix = randomBytes(8).toString('hex');
const readRole = `scriptura_read_${suffix}`, reviewRole = `scriptura_review_${suffix}`;
const password = randomBytes(32).toString('hex');
const readUrl = new URL(schemaUrl), reviewUrl = new URL(schemaUrl);
readUrl.username = readRole; readUrl.password = password;
reviewUrl.username = reviewRole; reviewUrl.password = password;
const admin = new pg.Pool({ connectionString: originalUrl });
const db = new pg.Pool({ connectionString: schemaUrl.toString() });
const token = 'local-only-integration-test-token';
const headers = { authorization: `Bearer ${token}`, 'content-type': 'application/json' };
let server, base, schemaCreated = false, readRoleCreated = false, reviewRoleCreated = false;
async function api(path, options = {}) {
  const response = await fetch(`${base}/api/v1/${path}`, options);
  return { status: response.status, body: await response.json() };
}
const review = (id, decision = 'approve_source') => ({ method:'POST',headers,body:JSON.stringify({claim_version_id:id,decision,rationale:'Fictional test review'}) });
before(async () => {
  await admin.query(`CREATE SCHEMA "${schema}"`); schemaCreated = true;
  for (const migration of ['001_schema.sql','002_append_only.sql','003_research_integrity.sql']) await db.query(await readFile(`db/${migration}`, 'utf8'));
  await db.query(`
    INSERT INTO corpora(id,name,corpus_kind,data_class) VALUES ('c','Fictional corpus','other','scholarly_candidate'), ('cs','Synthetic corpus','other','synthetic');
    INSERT INTO works(id,corpus_id,title,data_class) VALUES ('w','c','Fictional work','scholarly_candidate'), ('ws','cs','Synthetic work','synthetic'), ('wmix','c','Synthetic mixed work','synthetic');
    INSERT INTO reference_schemes(id,corpus_id,scheme_name,data_class) VALUES ('rs','c','Fictional scheme','scholarly_candidate'), ('rss','cs','Synthetic scheme','synthetic'), ('rsmix','c','Synthetic mixed scheme','synthetic');
    INSERT INTO passages(id,corpus_id,work_id,scheme_id,external_ref,granularity,data_class) VALUES ('p','c','w','rs','1.1','verse','scholarly_candidate'), ('p2','c','w','rs','1.2','verse','scholarly_candidate'), ('ps','cs','ws','rss','S.1','verse','synthetic'), ('ps2','cs','ws','rss','S.2','verse','synthetic'), ('pm-work','c','wmix','rs','M.1','verse','scholarly_candidate'), ('pm-scheme','c','w','rsmix','M.2','verse','scholarly_candidate');
    INSERT INTO traditions(id,name,classification_kind,data_class) VALUES ('t','Fictional school','school','scholarly_candidate'), ('ts','Synthetic school','school','synthetic');
    INSERT INTO agents(id,display_name,agent_kind,data_class) VALUES ('a','Fictional researcher','person','scholarly_candidate'), ('reviewer','Fictional reviewer','person','scholarly_candidate'), ('as','Synthetic researcher','person','synthetic');
    INSERT INTO sources(id,title,source_kind,storage_policy,license_status,data_class) VALUES ('s','Fictional source','other','metadata_only','unknown','source_verified'),('ss','Synthetic source','other','metadata_only','unknown','synthetic');
    INSERT INTO source_locators(id,source_id,locator_type,locator_value,verification_status,verified_at) VALUES ('l','s','section','fictional location','checked',NOW()),('un','s','section','unchecked location','unverified',NULL),('ls','ss','section','synthetic location','unverified',NULL);
    INSERT INTO agent_affiliations(id,agent_id,tradition_id,relation_type,source_locator_id) VALUES ('aff','a','t','self_identified','l');
    INSERT INTO claims(id) VALUES ('claim_good'),('claim_other'),('claim_bad'),('claim_synthetic');
    INSERT INTO claim_versions(id,claim_id,revision_no,statement,extraction_method,review_status,revision_reason,data_class) VALUES ('good','claim_good',1,'Fictional candidate A','human','extracted','test','scholarly_candidate'),('other','claim_other',1,'Fictional candidate B','human','extracted','test','scholarly_candidate'),('bad','claim_bad',1,'Fictional unsupported candidate','human','extracted','test','scholarly_candidate'),('synthetic','claim_synthetic',1,'Synthetic only','human','extracted','test','synthetic');
    INSERT INTO claim_passages(id,claim_version_id,passage_id,link_kind) VALUES ('cp1','good','p','interpretation_of'),('cp2','other','p','interpretation_of'),('cp3','bad','p','interpretation_of'),('cp4','synthetic','ps','interpretation_of'),('cross','synthetic','p','interpretation_of');
    INSERT INTO claim_attributions(id,claim_version_id,agent_id,attribution_kind,source_locator_id,attribution_status) VALUES ('a1','good','a','individual_opinion','l','verified'),('a2','other','a','individual_opinion','l','verified');
    INSERT INTO claim_evidence(id,claim_version_id,source_locator_id,evidence_role,explanation,review_status) VALUES ('e1','good','l','context','Fictional evidence','verified'),('e2','other','l','context','Fictional evidence','verified');
    INSERT INTO passage_alignments(id,from_passage_id,to_passage_id,alignment_type,review_status,source_locator_id,rationale) VALUES ('aligned','p','p2','partial','verified','l','Fictional alignment'),('unconfirmed','p2','p','uncertain','proposed','un','Fictional proposed alignment');
    INSERT INTO passage_relations(id,from_passage_id,to_passage_id,relation_type,source_locator_id,review_status,rationale) VALUES ('pr','p','p2','parallel','l','verified','Fictional passage relation'),('pr-unchecked','p2','p','parallel','un','proposed','Fictional unverified passage relation'),('pr-synthetic','ps','ps2','parallel','ls','proposed','Synthetic passage relation'),('pr-cross','p','ps','parallel','un','proposed','Fictional cross-group link');
    INSERT INTO claim_relations(id,from_version_id,to_version_id,relation_type,review_status,source_locator_id,rationale) VALUES ('r','good','other','rebuts','verified','l','Fictional relation');
    SELECT scriptura_review_claim('other','reviewer','approve_source','Fictional test review','initial-review','initial-provenance');
  `);
  await admin.query(`CREATE ROLE "${readRole}" LOGIN PASSWORD '${password}'`); readRoleCreated = true;
  await admin.query(`CREATE ROLE "${reviewRole}" LOGIN PASSWORD '${password}'`); reviewRoleCreated = true;
  await db.query(`GRANT USAGE ON SCHEMA "${schema}" TO "${readRole}", "${reviewRole}"`);
  await db.query(`GRANT SELECT ON corpora,works,reference_schemes,passages,traditions,agents,sources,source_locators,passage_alignments,agent_affiliations,claims,claim_versions,claim_attributions,claim_passages,claim_evidence,claim_relations,passage_relations TO "${readRole}"`);
  await db.query(`GRANT SELECT ON review_events,provenance_events TO "${reviewRole}"`);
  await db.query(`GRANT EXECUTE ON FUNCTION scriptura_review_claim(text,text,text,text,text,text) TO "${reviewRole}"`);
  const probe = createServer();
  await new Promise((resolve, reject) => { probe.once('error',reject); probe.listen(0,'127.0.0.1',resolve); });
  const port = probe.address().port;
  await new Promise((resolve, reject) => probe.close(error => error ? reject(error) : resolve()));
  base = `http://127.0.0.1:${port}`;
  server = spawn(process.execPath,['node_modules/next/dist/bin/next','dev','-H','127.0.0.1','-p',String(port)], {
    env:{...process.env,DATABASE_URL:readUrl.toString(),SCRIPTURA_REVIEW_DATABASE_URL:reviewUrl.toString(),SCRIPTURA_ADMIN_TOKEN:token,SCRIPTURA_REVIEWER_AGENT_ID:'reviewer',NEXT_TELEMETRY_DISABLED:'1'},stdio:'ignore'
  });
  const deadline = Date.now()+60000;
  while(Date.now()<deadline){
    if(server.exitCode!==null) throw new Error(`server exited ${server.exitCode}`);
    try { if ((await fetch(base+'/api/v1/passages',{signal:AbortSignal.timeout(5000)})).ok) return; } catch { /* wait for server */ }
    await new Promise(resolve=>setTimeout(resolve,200));
  }
  throw new Error('server startup timeout');
});
after(async () => {
  if (server && server.exitCode === null) {
    server.kill('SIGTERM');
    await new Promise(resolve=>{server.once('exit',resolve);setTimeout(resolve,3000).unref();});
  }
  await db.end();
  if(schemaCreated) await admin.query(`DROP SCHEMA "${schema}" CASCADE`);
  if(readRoleCreated) await admin.query(`DROP ROLE "${readRole}"`);
  if(reviewRoleCreated) await admin.query(`DROP ROLE "${reviewRole}"`);
  await admin.end();
});

test('database results hide candidates by default and isolate synthetic records', async () => {
  const r=await api('passages/p/interpretations?dataset=database');
  assert.equal(r.status,200); assert.equal(r.body.dataset_kind,'database');
  assert.deepEqual(r.body.interpretations.map(x=>x.id),['other']);
  const expanded=await api('passages/p/interpretations?dataset=database&include_unverified=true');
  assert.deepEqual(expanded.body.interpretations.map(x=>x.id).sort(),['bad','good','other']);
  assert.equal((await api('claims/synthetic?dataset=database&include_unverified=true')).status,404);
  const passages=await api('passages?dataset=database');
  assert.ok(!passages.body.passages.some(p=>['ps','pm-work','pm-scheme'].includes(p.id)));
  assert.equal((await api('passages/pm-work?dataset=database')).status,404);
  assert.equal((await api('passages/pm-scheme?dataset=database')).status,404);
  assert.equal((await api('graph?dataset=database&passage_id=pm-work')).status,404);
  assert.equal((await api('passages/ps?dataset=database')).status,404);
  const demo=await api('passages'); assert.equal(demo.body.dataset_kind,'synthetic'); assert.match(demo.body.warning,/합성/);
});
test('explicit PostgreSQL synthetic mode never mixes either dataset and hides unverified by default', async () => {
  const research=await api('passages?dataset=database');
  assert.equal(research.status,200); assert.ok(research.body.passages.some(x=>x.id==='p')); assert.ok(!research.body.passages.some(x=>x.id==='ps'));
  const demo=await api('passages?dataset=database&data_mode=synthetic');
  assert.equal(demo.status,200); assert.equal(demo.body.dataset_kind,'synthetic'); assert.match(demo.body.warning,/합성/);
  assert.ok(demo.body.passages.some(x=>x.id==='ps')); assert.ok(!demo.body.passages.some(x=>x.id==='p'));
  const closed=await api('passages/ps/interpretations?dataset=database&data_mode=synthetic');
  assert.equal(closed.status,200); assert.deepEqual(closed.body.interpretations,[]);
  const open=await api('passages/ps/interpretations?dataset=database&data_mode=synthetic&include_unverified=true');
  assert.equal(open.status,200); assert.deepEqual(open.body.interpretations.map(x=>x.id),['synthetic']);
  assert.equal((await api('claims/good?dataset=database&data_mode=synthetic&include_unverified=true')).status,404);
  assert.equal((await api('claims/synthetic?dataset=database&include_unverified=true')).status,404);
  const syntheticGraph = await api('graph?dataset=database&data_mode=synthetic&passage_id=ps&include_unverified=true');
  assert.equal(syntheticGraph.status,200);
  assert.ok(syntheticGraph.body.edges.some(x=>x.id==='pr-synthetic'));
  assert.ok(!syntheticGraph.body.edges.some(x=>x.id==='pr-cross'));
});
test('filters preserve attribution and supported affiliation evidence', async () => {
  const r=await api('passages/p/interpretations?dataset=database&include_unverified=true&tradition_id=t&agent_id=a');
  assert.deepEqual(r.body.interpretations.map(x=>x.id).sort(),['good','other']);
  assert.equal(r.body.interpretations[0].attributions[0].attribution_kind,'individual_opinion');
  assert.equal((await api('passages/p/interpretations?dataset=database&include_unverified=true&tradition_id=absent')).body.interpretations.length,0);
});
test('read and review roles are distinct and limited to necessary database privileges', async () => {
  const read = new pg.Pool({connectionString:readUrl.toString()});
  const reviewDb = new pg.Pool({connectionString:reviewUrl.toString()});
  try {
    assert.equal((await read.query('SELECT current_user')).rows[0].current_user,readRole);
    assert.equal((await reviewDb.query('SELECT current_user')).rows[0].current_user,reviewRole);
    await assert.rejects(read.query("SELECT scriptura_review_claim('good','reviewer','approve_source','test','forged-review','forged-provenance')"), /permission denied/);
    await assert.rejects(read.query('SELECT * FROM review_events'), /permission denied/);
    await assert.rejects(reviewDb.query("UPDATE claim_versions SET statement='tampered' WHERE id='good'"), /permission denied/);
    await assert.rejects(reviewDb.query("DELETE FROM review_events"), /permission denied/);
  } finally { await read.end(); await reviewDb.end(); }
});
test('approval is authenticated, verifies prerequisites, and appends immutable audit events', async () => {
  assert.equal((await api('admin/reviews?dataset=database',{...review('good'),headers:{'content-type':'application/json'}})).status,401);
  assert.equal((await api('admin/audit?dataset=database&entity_id=good')).status,401);
  const forged = { ...review('good'), body: JSON.stringify({claim_version_id:'good',decision:'approve_source',rationale:'Fictional test',reviewer_agent_id:'a'}) };
  assert.equal((await api('admin/reviews?dataset=database',forged)).status,400);
  assert.equal((await api('admin/reviews?dataset=database',review('bad'))).status,400);
  let events=await api('admin/audit?dataset=database&entity_id=bad',{headers});
  assert.deepEqual(events.body.reviews,[]); assert.deepEqual(events.body.provenance,[]);
  assert.equal((await api('admin/reviews?dataset=database',review('synthetic'))).status,400);
  assert.equal((await api('admin/reviews?dataset=database',review('good'))).status,201);
  const claim=await api('claims/good?dataset=database');
  assert.equal(claim.body.claim.review_status,'source_verified'); assert.equal(claim.body.claim.data_class,'source_verified');
  events=await api('admin/audit?dataset=database&entity_id=good',{headers});
  assert.equal(events.body.reviews.length,1); assert.equal(events.body.reviews[0].reviewer_agent_id,'reviewer'); assert.equal(events.body.provenance.length,1);
  await assert.rejects(db.query("UPDATE review_events SET rationale='tampered' WHERE target_entity_id='good'"), /append-only/);
  await assert.rejects(db.query("DELETE FROM provenance_events WHERE target_entity_id='good'"), /append-only/);
});
test('alignments and rebuttal graph include checked locations and hide proposed data by default', async () => {
  const good = await db.query("SELECT review_status FROM claim_versions WHERE id='good'");
  if (good.rows[0].review_status !== 'source_verified') await db.query("SELECT scriptura_review_claim('good','reviewer','approve_source','Fictional graph setup','graph-review','graph-provenance')");
  const align=await api('passages/p/alignments?dataset=database');
  assert.equal(align.status,200); assert.deepEqual(align.body.alignments.map(x=>x.id),['aligned']);
  assert.equal(align.body.alignments[0].locator.verification_status,'checked'); assert.ok(align.body.alignments[0].locator.verified_at);
  const more=await api('passages/p/alignments?dataset=database&include_unverified=true');
  assert.deepEqual(more.body.alignments.map(x=>x.id).sort(),['aligned','unconfirmed']);
  const graph=await api('graph?dataset=database&passage_id=p'); assert.equal(graph.status,200);
  assert.ok(graph.body.nodes.some(x=>x.id==='p' && x.type==='passage'));
  assert.ok(graph.body.nodes.some(x=>x.id==='p2' && x.type==='passage'));
  assert.ok(graph.body.edges.some(x=>x.id==='pr' && x.locator?.verification_status==='checked'));
  assert.ok(!graph.body.edges.some(x=>x.id==='pr-unchecked' || x.id==='pr-cross'));
  const expandedGraph=await api('graph?dataset=database&passage_id=p&include_unverified=true');
  assert.ok(expandedGraph.body.edges.some(x=>x.id==='pr-unchecked'));
  assert.ok(!expandedGraph.body.edges.some(x=>x.id==='pr-cross'));
  const rel=graph.body.edges.find(x=>x.id==='r'); assert.equal(rel.relation_type,'rebuts'); assert.equal(rel.locator.verification_status,'checked'); assert.ok(rel.locator.verified_at);
  assert.ok(graph.body.nodes.some(x=>x.type==='evidence')); assert.ok(graph.body.edges.some(x=>x.type==='evidence'&&x.locator?.verified_at));
});
