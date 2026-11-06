import { Pool } from 'pg';
import { randomUUID } from 'node:crypto';

// PostgreSQL mode is opt-in and fails closed when configuration or queries fail.
let pool: Pool | undefined;
let reviewPool: Pool | undefined;
function database() {
  if (!process.env.DATABASE_URL) throw new Error('DATABASE_URL is required for database mode');
  if (!pool) pool = new Pool({ connectionString: process.env.DATABASE_URL, max: 5, connectionTimeoutMillis: 5000 });
  return pool;
}
function reviewDatabase() {
  const readUrl = process.env.DATABASE_URL;
  const reviewUrl = process.env.SCRIPTURA_REVIEW_DATABASE_URL;
  if (!readUrl || !reviewUrl) throw new Error('Separate database credentials required');
  const read = new URL(readUrl), review = new URL(reviewUrl);
  if (!read.username || !review.username || decodeURIComponent(read.username) === decodeURIComponent(review.username) || read.hostname !== review.hostname || (read.port || '5432') !== (review.port || '5432') || read.pathname !== review.pathname) throw new Error('Separate database roles on the same database required');
  if (!reviewPool) reviewPool = new Pool({ connectionString: reviewUrl, max: 2, connectionTimeoutMillis: 5000 });
  return reviewPool;
}
export const dbWarning = '연구 후보 자료입니다. 각 출처의 검증 상태와 이용 권리를 확인하세요. 출처 검증은 주장의 진실성을 보증하지 않습니다.';
type Mode = 'research' | 'synthetic';
function queryFor(mode: Mode) {
  return async (sql: string, args: unknown[] = []) => {
    if (mode === 'synthetic') {
      sql = sql.replaceAll("data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed')", "data_class = 'synthetic'").replaceAll("data_class IN ('source_verified','scholarly_reviewed')", "data_class = 'synthetic'").replaceAll("data_class NOT IN ('source_verified','scholarly_reviewed')", "data_class <> 'synthetic'");
    }
    return (await database().query(sql, args)).rows;
  };
}
const rows = queryFor('research');
const validPassage = (alias: string) => `(${alias}.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed') AND EXISTS (SELECT 1 FROM corpora vc WHERE vc.id=${alias}.corpus_id AND vc.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed')) AND EXISTS (SELECT 1 FROM works vw WHERE vw.id=${alias}.work_id AND vw.corpus_id=${alias}.corpus_id AND vw.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed')) AND EXISTS (SELECT 1 FROM reference_schemes vs WHERE vs.id=${alias}.scheme_id AND vs.corpus_id=${alias}.corpus_id AND vs.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed')))`;
const visible = `(cv.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed') AND ($1::boolean OR (cv.data_class IN ('source_verified','scholarly_reviewed') AND cv.review_status IN ('source_verified','scholarly_reviewed'))))`;
const claimSelect = `SELECT cv.id,cv.claim_id,cv.revision_no,CASE WHEN cv.data_class='synthetic' THEN cv.statement ELSE '[권리 검토 전 내용 숨김]' END AS statement,cv.language_code,CASE WHEN cv.data_class='synthetic' THEN cv.interpretive_method ELSE NULL END AS interpretive_method,cv.extraction_method,cv.review_status,cv.data_class,cv.created_at,
 COALESCE((SELECT jsonb_agg(jsonb_build_object('id',a.id,'claim_version_id',a.claim_version_id,'attribution_kind',CASE WHEN a.attribution_kind='official_doctrine' THEN 'unconfirmed_authority' ELSE a.attribution_kind END,'attribution_status',a.attribution_status,'source_locator_id',a.source_locator_id,'agent',jsonb_build_object('id',ag.id,'display_name',ag.display_name,'agent_kind',ag.agent_kind)) ORDER BY a.id) FROM claim_attributions a JOIN agents ag ON ag.id=a.agent_id LEFT JOIN source_locators al ON al.id=a.source_locator_id LEFT JOIN sources srca ON srca.id=al.source_id WHERE (srca.id IS NULL OR srca.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed')) AND a.claim_version_id=cv.id AND ag.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed')),'[]'::jsonb) AS attributions,
 COALESCE((SELECT jsonb_agg(jsonb_build_object('id',e.id,'claim_version_id',e.claim_version_id,'evidence_role',e.evidence_role,'explanation',CASE WHEN cv.data_class='synthetic' THEN e.explanation ELSE NULL END,'review_status',e.review_status,'source_locator_id',e.source_locator_id,'locator',CASE WHEN l.id IS NULL THEN NULL ELSE jsonb_build_object('id',l.id,'source_id',l.source_id,'locator_type',l.locator_type,'locator_value',CASE WHEN s.data_class='synthetic' THEN l.locator_value ELSE NULL END,'verification_status',l.verification_status,'verified_at',l.verified_at) END,'source',CASE WHEN s.id IS NULL THEN NULL ELSE jsonb_build_object('id',s.id,'title',s.title,'creator',s.creator,'storage_policy',s.storage_policy,'license_status',s.license_status,'data_class',s.data_class,'source_url',s.source_url,'doi',s.doi) END) ORDER BY e.id) FROM claim_evidence e LEFT JOIN source_locators l ON l.id=e.source_locator_id LEFT JOIN sources s ON s.id=l.source_id LEFT JOIN passages ep ON ep.id=e.passage_id LEFT JOIN claim_versions ec ON ec.id=e.related_claim_version_id WHERE (ep.id IS NULL OR ${validPassage('ep')}) AND (ec.id IS NULL OR ec.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed')) AND e.claim_version_id=cv.id AND (s.id IS NULL OR s.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed'))),'[]'::jsonb) AS evidence,
 COALESCE((SELECT jsonb_agg(DISTINCT af.tradition_id) FROM claim_attributions a JOIN agents ag ON ag.id=a.agent_id AND ag.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed') JOIN agent_affiliations af ON af.agent_id=a.agent_id JOIN traditions tr ON tr.id=af.tradition_id AND tr.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed') JOIN source_locators fl ON fl.id=af.source_locator_id AND fl.verification_status='checked' AND fl.verified_at IS NOT NULL JOIN sources fs ON fs.id=fl.source_id AND fs.data_class IN ('source_verified','scholarly_reviewed') WHERE (a.source_locator_id IS NULL OR EXISTS(SELECT 1 FROM source_locators sal JOIN sources sas ON sas.id=sal.source_id WHERE sal.id=a.source_locator_id AND sas.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed'))) AND a.claim_version_id=cv.id AND af.relation_type IN ('self_identified','officially_affiliated','historically_attributed')),'[]'::jsonb) AS tradition_ids
 FROM claim_versions cv`;
const filters = ` AND ($3::text IS NULL OR EXISTS(SELECT 1 FROM claim_attributions a JOIN agents ag ON ag.id=a.agent_id AND ag.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed') JOIN agent_affiliations af ON af.agent_id=a.agent_id JOIN traditions tr ON tr.id=af.tradition_id AND tr.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed') JOIN source_locators fl ON fl.id=af.source_locator_id AND fl.verification_status='checked' AND fl.verified_at IS NOT NULL JOIN sources fs ON fs.id=fl.source_id AND fs.data_class IN ('source_verified','scholarly_reviewed') WHERE (a.source_locator_id IS NULL OR EXISTS(SELECT 1 FROM source_locators sal JOIN sources sas ON sas.id=sal.source_id WHERE sal.id=a.source_locator_id AND sas.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed'))) AND a.claim_version_id=cv.id AND af.tradition_id=$3 AND af.relation_type IN ('self_identified','officially_affiliated','historically_attributed')))
 AND ($4::text IS NULL OR EXISTS(SELECT 1 FROM claim_attributions a JOIN agents ag ON ag.id=a.agent_id AND ag.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed') WHERE (a.source_locator_id IS NULL OR EXISTS(SELECT 1 FROM source_locators sal JOIN sources sas ON sas.id=sal.source_id WHERE sal.id=a.source_locator_id AND sas.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed'))) AND a.claim_version_id=cv.id AND ag.agent_kind=$4))
 AND ($5::text IS NULL OR EXISTS(SELECT 1 FROM claim_attributions a JOIN agents ag ON ag.id=a.agent_id AND ag.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed') WHERE (a.source_locator_id IS NULL OR EXISTS(SELECT 1 FROM source_locators sal JOIN sources sas ON sas.id=sal.source_id WHERE sal.id=a.source_locator_id AND sas.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed'))) AND a.claim_version_id=cv.id AND a.agent_id=$5))
 AND ($6::text IS NULL OR EXISTS(SELECT 1 FROM claim_attributions a JOIN agents ag ON ag.id=a.agent_id AND ag.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed') WHERE (a.source_locator_id IS NULL OR EXISTS(SELECT 1 FROM source_locators sal JOIN sources sas ON sas.id=sal.source_id WHERE sal.id=a.source_locator_id AND sas.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed'))) AND a.claim_version_id=cv.id AND (CASE WHEN a.attribution_kind='official_doctrine' THEN 'unconfirmed_authority' ELSE a.attribution_kind END)=$6))`;
function f(url: URL) { return [url.searchParams.get('tradition_id'),url.searchParams.get('agent_kind'),url.searchParams.get('agent_id'),url.searchParams.get('attribution_kind')]; }
export async function getClaims(id: string | null, include: boolean, url: URL, byPassage = true, mode: Mode = 'research') {
  const condition = byPassage ? `EXISTS(SELECT 1 FROM claim_passages cp JOIN passages p ON p.id=cp.passage_id AND ${validPassage('p')} WHERE cp.claim_version_id=cv.id AND cp.passage_id=$2)` : 'cv.id=$2';
  return queryFor(mode)(`${claimSelect} WHERE ${visible} AND ($2::text IS NULL OR ${condition}) ${filters} ORDER BY cv.id LIMIT 500`, [include,id,...f(url)]);
}
export async function pgRead(path: string[], url: URL, mode: Mode = 'research'): Promise<{ body: object; status?: number }> {
  const inc = url.searchParams.get('include_unverified') === 'true';
  const rows = queryFor(mode);
  if (path.length===1 && path[0]==='corpora') return { body:{ corpora:await rows(`SELECT id,name,corpus_kind,CASE WHEN data_class='synthetic' THEN description ELSE NULL END AS description,data_class FROM corpora WHERE data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed') ORDER BY id LIMIT 500`) } };
  if (path.length===1 && path[0]==='traditions') return { body:{ traditions:await rows(`SELECT id,name,classification_kind,CASE WHEN EXISTS(SELECT 1 FROM traditions parent WHERE parent.id=traditions.parent_id AND parent.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed')) THEN parent_id ELSE NULL END AS parent_id,active_period,data_class FROM traditions WHERE data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed') ORDER BY id LIMIT 500`) } };
  if (path.length===1 && path[0]==='agents') return { body:{ agents:await rows(`SELECT id,display_name,agent_kind,name_disambiguator,data_class FROM agents WHERE data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed') ORDER BY id LIMIT 500`) } };
  if (path.length===1 && path[0]==='reference-schemes') return { body:{ reference_schemes:await rows(`SELECT id,corpus_id,scheme_name,normative_uri,data_class FROM reference_schemes WHERE data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed') AND EXISTS(SELECT 1 FROM corpora pc WHERE pc.id=reference_schemes.corpus_id AND pc.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed')) AND ($1::text IS NULL OR corpus_id=$1) ORDER BY id LIMIT 500`,[url.searchParams.get('corpus_id')]) } };
  if (path.length===1 && path[0]==='passages') return { body:{ passages:await rows(`SELECT id,corpus_id,work_id,scheme_id,external_ref,granularity,CASE WHEN p.data_class='synthetic' THEN p.location_expression ELSE NULL END AS location_expression,indexing_status FROM passages p WHERE ${validPassage('p')} AND ($1::text IS NULL OR scheme_id=$1) AND ($2::text IS NULL OR external_ref=$2) AND ($3::text IS NULL OR work_id=$3) ORDER BY id LIMIT 500`,[url.searchParams.get('scheme_id'),url.searchParams.get('ref'),url.searchParams.get('work_id')]) } };
  if (path[0]==='passages' && path.length>=2) {
    const passage=(await rows(`SELECT id,corpus_id,work_id,scheme_id,external_ref,granularity,CASE WHEN p.data_class='synthetic' THEN p.location_expression ELSE NULL END AS location_expression,indexing_status FROM passages p WHERE ${validPassage('p')} AND id=$1`,[path[1]]))[0];
    if (!passage) return {body:{error:'Not found'},status:404};
    if (path.length===2) return { body:{ passage } };
    if (path.length===3 && path[2]==='interpretations') return { body:{ passage_id:path[1],interpretations:await getClaims(path[1],inc,url,true,mode) } };
    if (path.length===3 && path[2]==='alignments') return { body:{ alignments:await rows(`SELECT pa.id,pa.from_passage_id,pa.to_passage_id,pa.alignment_type,pa.source_locator_id,CASE WHEN fp.data_class='synthetic' THEN pa.rationale ELSE NULL END AS rationale, CASE WHEN pa.review_status='verified' AND (l.verification_status IS DISTINCT FROM 'checked' OR l.verified_at IS NULL OR length(btrim(l.locator_value))=0 OR s.data_class NOT IN ('source_verified','scholarly_reviewed') OR s.data_class IS NULL) THEN 'proposed' ELSE pa.review_status END AS review_status, jsonb_build_object('id',fp.id,'corpus_id',fp.corpus_id,'work_id',fp.work_id,'scheme_id',fp.scheme_id,'external_ref',fp.external_ref,'granularity',fp.granularity,'location_expression',CASE WHEN fp.data_class='synthetic' THEN fp.location_expression ELSE NULL END,'indexing_status',fp.indexing_status,'data_class',fp.data_class) AS from_passage,jsonb_build_object('id',tp.id,'corpus_id',tp.corpus_id,'work_id',tp.work_id,'scheme_id',tp.scheme_id,'external_ref',tp.external_ref,'granularity',tp.granularity,'location_expression',CASE WHEN tp.data_class='synthetic' THEN tp.location_expression ELSE NULL END,'indexing_status',tp.indexing_status,'data_class',tp.data_class) AS to_passage, CASE WHEN l.id IS NULL THEN NULL ELSE jsonb_build_object('id',l.id,'source_id',l.source_id,'locator_type',l.locator_type,'locator_value',CASE WHEN s.data_class='synthetic' THEN l.locator_value ELSE NULL END,'verification_status',l.verification_status,'verified_at',l.verified_at) END AS locator,CASE WHEN s.id IS NULL THEN NULL ELSE jsonb_build_object('id',s.id,'title',s.title,'license_status',s.license_status,'storage_policy',s.storage_policy,'data_class',s.data_class) END AS source FROM passage_alignments pa JOIN passages fp ON fp.id=pa.from_passage_id JOIN passages tp ON tp.id=pa.to_passage_id LEFT JOIN source_locators l ON l.id=pa.source_locator_id LEFT JOIN sources s ON s.id=l.source_id WHERE ${validPassage('fp')} AND ${validPassage('tp')} AND (pa.from_passage_id=$1 OR pa.to_passage_id=$1) AND ($2 OR (pa.review_status='verified' AND l.verification_status='checked' AND l.verified_at IS NOT NULL AND length(btrim(l.locator_value))>0 AND s.data_class IN ('source_verified','scholarly_reviewed'))) AND (s.id IS NULL OR s.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed')) ORDER BY pa.id LIMIT 500`,[path[1],inc]) } };
  }
  if (path[0]==='claims' && path.length===2) {const claim=(await getClaims(path[1],inc,url,false,mode))[0];return claim ? {body:{claim}} : {body:{error:'Not found'},status:404};}
  if (path[0]==='sources' && path.length===2) {const source=(await rows(`SELECT id,title,creator,publication_year,source_kind,source_url,doi,edition_or_version,storage_policy,license_status,license_identifier,license_url,data_class FROM sources WHERE id=$1 AND data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed')`,[path[1]]))[0];return source?{body:{source}}:{body:{error:'Not found'},status:404};}
  if (path[0]==='graph' && path.length===1) {
    const id=url.searchParams.get('passage_id'); if (!id) return {body:{error:'passage_id required'},status:400};
    if (!(await rows(`SELECT p.id FROM passages p WHERE p.id=$1 AND ${validPassage('p')}`,[id])).length) return {body:{error:'Not found'},status:404};
    const claims=await getClaims(id,inc,url,true,mode); const ids=claims.map(c=>c.id);
    const relations=ids.length ? await rows(`SELECT r.id,r.from_version_id,r.to_version_id,r.relation_type,r.source_locator_id,CASE WHEN s.data_class='synthetic' THEN r.rationale ELSE NULL END AS rationale, CASE WHEN r.review_status='verified' AND (l.verification_status IS DISTINCT FROM 'checked' OR l.verified_at IS NULL OR length(btrim(l.locator_value))=0 OR s.data_class NOT IN ('source_verified','scholarly_reviewed') OR s.data_class IS NULL) THEN 'proposed' ELSE r.review_status END AS review_status, CASE WHEN l.id IS NULL THEN NULL ELSE jsonb_build_object('id',l.id,'source_id',l.source_id,'locator_type',l.locator_type,'locator_value',CASE WHEN s.data_class='synthetic' THEN l.locator_value ELSE NULL END,'verification_status',l.verification_status,'verified_at',l.verified_at) END AS locator, CASE WHEN s.id IS NULL THEN NULL ELSE jsonb_build_object('id',s.id,'title',s.title,'license_status',s.license_status,'storage_policy',s.storage_policy,'data_class',s.data_class) END AS source FROM claim_relations r LEFT JOIN source_locators l ON l.id=r.source_locator_id LEFT JOIN sources s ON s.id=l.source_id WHERE (r.from_version_id=ANY($1::text[]) OR r.to_version_id=ANY($1::text[])) AND ($2 OR (r.review_status='verified' AND l.verification_status='checked' AND l.verified_at IS NOT NULL AND length(btrim(l.locator_value))>0 AND s.data_class IN ('source_verified','scholarly_reviewed'))) AND (s.id IS NULL OR s.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed')) ORDER BY r.id LIMIT 500`,[ids,inc]):[];
    const neighborIds=[...new Set(relations.flatMap(r=>[r.from_version_id,r.to_version_id]))];
    const neighbors = neighborIds.length ? await rows(`${claimSelect} WHERE ${visible} AND cv.id=ANY($2::text[]) ${filters} ORDER BY cv.id LIMIT 500`,[inc,neighborIds,...f(url)]) : [];
    const nodeMap = new Map([...claims,...neighbors].map(c=>[c.id,c]));
    const allowed = new Set(nodeMap.keys());
    const nodes=[...nodeMap.values()].map(c=>({...c,type:'claim'}));
    const edges: object[] = relations.filter(r=>allowed.has(r.from_version_id)&&allowed.has(r.to_version_id)).map(r=>({...r,type:'claim_relation'}));
    for (const claim of nodeMap.values()) for (const e of claim.evidence) { if (!inc && e.review_status!=='verified') continue; nodes.push({...e,type:'evidence'}); edges.push({id:`evidence:${e.id}`,type:'evidence',from_version_id:claim.id,to_version_id:e.id,relation_type:e.evidence_role,review_status:e.review_status,source_locator_id:e.source_locator_id,locator:e.locator,source:e.source,rationale:e.explanation}); }
    const passageRelations = await rows(`SELECT pr.id,pr.from_passage_id,pr.to_passage_id,pr.relation_type,pr.asserted_by_agent_id,pr.source_locator_id,CASE WHEN fp.data_class='synthetic' THEN pr.rationale ELSE NULL END AS rationale, fp.id AS from_id, tp.id AS to_id,
      CASE WHEN pr.review_status='verified' AND (l.verification_status IS DISTINCT FROM 'checked' OR l.verified_at IS NULL OR length(btrim(l.locator_value))=0 OR s.data_class NOT IN ('source_verified','scholarly_reviewed') OR s.data_class IS NULL) THEN 'proposed' ELSE pr.review_status END AS review_status,
      CASE WHEN l.id IS NULL THEN NULL ELSE jsonb_build_object('id',l.id,'source_id',l.source_id,'locator_type',l.locator_type,'locator_value',CASE WHEN s.data_class='synthetic' THEN l.locator_value ELSE NULL END,'verification_status',l.verification_status,'verified_at',l.verified_at) END AS locator,
      CASE WHEN s.id IS NULL THEN NULL ELSE jsonb_build_object('id',s.id,'title',s.title,'license_status',s.license_status,'storage_policy',s.storage_policy,'data_class',s.data_class) END AS source
      FROM passage_relations pr JOIN passages fp ON fp.id=pr.from_passage_id JOIN passages tp ON tp.id=pr.to_passage_id
      LEFT JOIN source_locators l ON l.id=pr.source_locator_id LEFT JOIN sources s ON s.id=l.source_id
      LEFT JOIN agents aa ON aa.id=pr.asserted_by_agent_id
      WHERE ${validPassage('fp')} AND ${validPassage('tp')}
      AND (aa.id IS NULL OR aa.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed'))
      AND (pr.from_passage_id=$1 OR pr.to_passage_id=$1) AND (s.id IS NULL OR s.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed'))
      AND ($2 OR (pr.review_status='verified' AND l.verification_status='checked' AND l.verified_at IS NOT NULL AND length(btrim(l.locator_value))>0 AND s.data_class IN ('source_verified','scholarly_reviewed'))) ORDER BY pr.id LIMIT 500`,[id,inc]);
    const passageIds=[...new Set([id,...passageRelations.flatMap(r=>[r.from_id,r.to_id])])];
    const passageNodes=await rows(`SELECT id,external_ref,scheme_id,work_id,granularity,data_class FROM passages p WHERE id=ANY($1::text[]) AND ${validPassage('p')} ORDER BY id`,[passageIds]);
    nodes.push(...passageNodes.map(p=>({...p,type:'passage'})));
    edges.push(...passageRelations.map(r=>({...r,type:'passage_relation',from_version_id:r.from_id,to_version_id:r.to_id})));
    return {body:{nodes,edges}};
  }
  return {body:{error:'Not found'},status:404};
}
export async function pgReview(body: Record<string,unknown>) {
  const reviewer = process.env.SCRIPTURA_REVIEWER_AGENT_ID;
  if (!reviewer) throw new Error('SCRIPTURA_REVIEWER_AGENT_ID required');
  if (typeof body.claim_version_id !== 'string' || typeof body.rationale !== 'string' || !body.rationale.trim() || typeof body.decision !== 'string' || !['approve_source','approve_scholarly','request_changes','reject','mark_disputed'].includes(body.decision) || Object.keys(body).some(k=>!['claim_version_id','decision','rationale'].includes(k))) throw new Error('Invalid review');
  const result = await reviewDatabase().query('SELECT scriptura_review_claim($1,$2,$3,$4,$5,$6) AS result',[body.claim_version_id,reviewer,body.decision,body.rationale,randomUUID(),randomUUID()]);
  return result.rows[0];
}
export async function pgAudit(id: string | null) {
  const rows = async (sql: string, args: unknown[]) => (await reviewDatabase().query(sql, args)).rows;
  if (!id) throw new Error('entity_id required');
  return {reviews:await rows(`SELECT id,target_entity_type,target_entity_id,reviewer_agent_id,decision,rationale,source_locator_id,reviewed_at FROM review_events WHERE target_entity_id=$1 ORDER BY reviewed_at,id LIMIT 500`,[id]),provenance:await rows(`SELECT id,event_type,target_entity_type,target_entity_id,actor_agent_id,source_id,recorded_at,metadata FROM provenance_events WHERE target_entity_id=$1 ORDER BY recorded_at,id LIMIT 500`,[id])};
}

/** Dedicated view-only authority credential. Never use broad legacy read credentials. */
let authorityPool: Pool | undefined;
function authorityDatabase() {
  const authorityUrl=process.env.DATABASE_AUTHORITY_URL;
  const readUrl=process.env.DATABASE_URL;
  const reviewUrl=process.env.SCRIPTURA_REVIEW_DATABASE_URL;
  if (!authorityUrl || !readUrl) throw new Error('Dedicated authority database credentials required');
  const authority=new URL(authorityUrl), read=new URL(readUrl);
  const sameDB=(a: URL,b: URL) => a.hostname===b.hostname && (a.port || '5432')===(b.port || '5432') && a.pathname===b.pathname;
  const username=(u: URL) => decodeURIComponent(u.username);
  if (!username(authority) || !username(read) || username(authority)===username(read) || !sameDB(authority,read)) throw new Error('Distinct authority role on same database required');
  if (reviewUrl) { const review=new URL(reviewUrl); if (username(authority)===username(review) || !sameDB(authority,review)) throw new Error('Authority role must differ from review role'); }
  if (!authorityPool) authorityPool=new Pool({connectionString:authorityUrl,max:3,connectionTimeoutMillis:5000});
  return authorityPool;
}

/** Read only a redacted view; require a role without raw authority access. */
export async function pgAuthority(url: URL, mode: Mode = 'research') {
  const asOf = url.searchParams.get('as_of') || new Date().toISOString().slice(0,10);
  const include = url.searchParams.get('include_unverified') === 'true';
  const db=authorityDatabase();
  const permissions=await db.query(`SELECT r.rolsuper,r.rolcreatedb,r.rolcreaterole,r.rolbypassrls,r.rolreplication,
    has_table_privilege(current_user,'authority_safe_readings','SELECT') AS can_safe,
    has_table_privilege(current_user,'authority_readings','SELECT') AS can_raw_view,
    has_table_privilege(current_user,'authority_attestations','SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') AS can_raw_attestations,
    has_table_privilege(current_user,'authority_documents','SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') AS can_raw_documents,
    (SELECT bool_or(has_any_column_privilege(current_user,x.relid,'SELECT')) FROM unnest(ARRAY[
      'authority_attestations'::regclass,'authority_documents'::regclass,'authority_readings'::regclass,
      'claim_versions'::regclass,'claim_evidence'::regclass,'claim_relations'::regclass,
      'passage_relations'::regclass,'passage_alignments'::regclass,'source_locators'::regclass
    ]) AS x(relid)) AS can_raw_columns,
    pg_has_role(current_user::regrole::oid,(SELECT relowner FROM pg_class WHERE oid='authority_safe_readings'::regclass),'MEMBER') AS owns_view,
    has_schema_privilege(current_user, (SELECT relnamespace FROM pg_class WHERE oid='authority_safe_readings'::regclass), 'CREATE') AS can_create_schema,
    EXISTS (SELECT 1 FROM pg_auth_members WHERE member=current_user::regrole::oid) AS has_membership
    FROM pg_roles r WHERE r.rolname=current_user`);
  const privilege=permissions.rows[0];
  if (!privilege || privilege.rolsuper || privilege.rolcreatedb || privilege.rolcreaterole || privilege.rolbypassrls || privilege.rolreplication || !privilege.can_safe || privilege.can_raw_view || privilege.can_raw_attestations || privilege.can_raw_documents || privilege.can_raw_columns || privilege.owns_view || privilege.can_create_schema || privilege.has_membership) throw new Error('Authority role exceeds view-only scope');
  const classes=mode==='synthetic' ? ['synthetic'] : ['scholarly_candidate','source_verified','scholarly_reviewed'];
  const result=(await db.query(`SELECT id,tradition_id,authority_kind,position_scope,perspective,
    effective_quotation_status,effective_authority_status,effective_argument_status,effective_independent_review_status,
    official_proof_sufficient,proof_directness,jurisdiction,as_of::text,valid_from::text,valid_until::text,
    statement,representativity,uncertainty,locator_value,published_on::text,revised_on::text,edition_label,language_code,issuer_name
    FROM authority_safe_readings
    WHERE NOT is_superseded AND NOT is_retraction AND classification_consistent
      AND data_class=ANY($3::text[]) AND claim_data_class=ANY($3::text[])
      AND ($1::boolean OR ((data_class IN ('source_verified','scholarly_reviewed') OR data_class='synthetic') AND claim_review_status IN ('source_verified','scholarly_reviewed')))
      AND ($2::text IS NULL OR tradition_id=$2)
    ORDER BY id LIMIT 500`,[include,url.searchParams.get('tradition_id'),classes])).rows;
  const labels: Record<string,string> = {
    normative_adopted:'공식 채택 문헌', official_institutional_guidance:'기관의 설명',
    historical_organizational_publication:'과거 간행물', individual_insider_view:'개인 의견',
    external_description_or_criticism:'외부 설명·비판', scholarly_individual_analysis:'학술 분석',
    plural_or_unresolved:'미확정·다원성',
  };
  const actions = ['browse','collect_metadata','store_raw','store_excerpt','index_fulltext','embed','send_to_model','redistribute','public_link'];
  const positions = result.map((row) => {
    let kind: string = row.authority_kind;
    let status: string = row.effective_authority_status;
    const inWindow = !!(row.valid_from && row.valid_until && row.valid_from <= asOf && asOf <= row.valid_until && row.published_on && row.published_on <= asOf && row.revised_on && row.revised_on <= asOf);
    const official = kind === 'normative_adopted' && row.official_proof_sufficient === true && status === 'adoption_documented' && inWindow;
    if (kind === 'normative_adopted' && !official) { kind = 'plural_or_unresolved'; status = 'unknown'; }
    if (kind === 'official_institutional_guidance' && (status !== 'issuer_documented' || !inWindow)) { kind = 'plural_or_unresolved'; status = 'unknown'; }
    if (kind === 'historical_organizational_publication' && (status !== 'historical_only' || !row.published_on || row.published_on > asOf)) { kind = 'plural_or_unresolved'; status = 'unknown'; }
    if ((kind === 'individual_insider_view' || kind === 'scholarly_individual_analysis') && status !== 'individual_only') status = 'unknown';
    if (kind === 'external_description_or_criticism') status = 'unknown';
    const uncertain = kind === 'plural_or_unresolved' || status === 'unknown' || row.effective_quotation_status === 'unchecked';
    return { id:row.id, label:labels[kind] || labels.plural_or_unresolved, summary:row.statement,
      tradition_id:row.tradition_id, issuer:row.issuer_name ?? null, kind, authority_kind:kind,
      position_scope:kind === 'plural_or_unresolved' ? 'insufficient_evidence' : row.position_scope,
      quotation_status:row.effective_quotation_status, authority_status:status, argument_status:row.effective_argument_status,
      independent_review_status:row.effective_independent_review_status, as_of:row.as_of, requested_as_of:asOf, as_of_basis:url.searchParams.has('as_of') ? 'requested' : 'current_utc',
      published_at:row.published_on, revised_on:row.revised_on, effective_from:row.valid_from,effective_until:row.valid_until,
      edition:row.edition_label, language:row.language_code, jurisdiction:row.jurisdiction,
      exact_locator:row.locator_value, representativity:row.representativity ?? (official ? '해당 범위의 채택 근거가 기록됨' : '공식 채택을 추정할 근거 없음'),
      proof_directness:row.proof_directness, verification_path:row.proof_directness,
      uncertainty:(row.uncertainty ?? '원문 이용 권리와 적용 범위를 별도로 검토해야 합니다.') + ' 기록되지 않은 후속 철회 여부는 자동 확인할 수 없습니다.',
      assessment:uncertain ? 'insufficient_evidence' : 'documented', rights:Object.fromEntries(actions.map(action => [action,false])),
    };
  });
  const kind = url.searchParams.get('kind');
  return kind ? positions.filter(position => position.kind === kind) : positions;
}
