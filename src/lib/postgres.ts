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
const claimSelect = `SELECT cv.id,cv.claim_id,cv.revision_no,cv.statement,cv.language_code,cv.interpretive_method,cv.extraction_method,cv.review_status,cv.data_class,cv.created_at,
 COALESCE((SELECT jsonb_agg(jsonb_build_object('id',a.id,'claim_version_id',a.claim_version_id,'attribution_kind',a.attribution_kind,'attribution_status',a.attribution_status,'source_locator_id',a.source_locator_id,'agent',jsonb_build_object('id',ag.id,'display_name',ag.display_name,'agent_kind',ag.agent_kind)) ORDER BY a.id) FROM claim_attributions a JOIN agents ag ON ag.id=a.agent_id LEFT JOIN source_locators al ON al.id=a.source_locator_id LEFT JOIN sources srca ON srca.id=al.source_id WHERE (srca.id IS NULL OR srca.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed')) AND a.claim_version_id=cv.id AND ag.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed')),'[]'::jsonb) AS attributions,
 COALESCE((SELECT jsonb_agg(jsonb_build_object('id',e.id,'claim_version_id',e.claim_version_id,'evidence_role',e.evidence_role,'explanation',e.explanation,'review_status',e.review_status,'source_locator_id',e.source_locator_id,'locator',CASE WHEN l.id IS NULL THEN NULL ELSE jsonb_build_object('id',l.id,'source_id',l.source_id,'locator_type',l.locator_type,'locator_value',l.locator_value,'verification_status',l.verification_status,'verified_at',l.verified_at) END,'source',CASE WHEN s.id IS NULL THEN NULL ELSE jsonb_build_object('id',s.id,'title',s.title,'creator',s.creator,'storage_policy',s.storage_policy,'license_status',s.license_status,'data_class',s.data_class,'source_url',s.source_url,'doi',s.doi) END) ORDER BY e.id) FROM claim_evidence e LEFT JOIN source_locators l ON l.id=e.source_locator_id LEFT JOIN sources s ON s.id=l.source_id LEFT JOIN passages ep ON ep.id=e.passage_id LEFT JOIN claim_versions ec ON ec.id=e.related_claim_version_id WHERE (ep.id IS NULL OR ${validPassage('ep')}) AND (ec.id IS NULL OR ec.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed')) AND e.claim_version_id=cv.id AND (s.id IS NULL OR s.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed'))),'[]'::jsonb) AS evidence,
 COALESCE((SELECT jsonb_agg(DISTINCT af.tradition_id) FROM claim_attributions a JOIN agents ag ON ag.id=a.agent_id AND ag.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed') JOIN agent_affiliations af ON af.agent_id=a.agent_id JOIN traditions tr ON tr.id=af.tradition_id AND tr.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed') JOIN source_locators fl ON fl.id=af.source_locator_id AND fl.verification_status='checked' AND fl.verified_at IS NOT NULL JOIN sources fs ON fs.id=fl.source_id AND fs.data_class IN ('source_verified','scholarly_reviewed') WHERE (a.source_locator_id IS NULL OR EXISTS(SELECT 1 FROM source_locators sal JOIN sources sas ON sas.id=sal.source_id WHERE sal.id=a.source_locator_id AND sas.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed'))) AND a.claim_version_id=cv.id AND af.relation_type IN ('self_identified','officially_affiliated','historically_attributed')),'[]'::jsonb) AS tradition_ids
 FROM claim_versions cv`;
const filters = ` AND ($3::text IS NULL OR EXISTS(SELECT 1 FROM claim_attributions a JOIN agents ag ON ag.id=a.agent_id AND ag.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed') JOIN agent_affiliations af ON af.agent_id=a.agent_id JOIN traditions tr ON tr.id=af.tradition_id AND tr.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed') JOIN source_locators fl ON fl.id=af.source_locator_id AND fl.verification_status='checked' AND fl.verified_at IS NOT NULL JOIN sources fs ON fs.id=fl.source_id AND fs.data_class IN ('source_verified','scholarly_reviewed') WHERE (a.source_locator_id IS NULL OR EXISTS(SELECT 1 FROM source_locators sal JOIN sources sas ON sas.id=sal.source_id WHERE sal.id=a.source_locator_id AND sas.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed'))) AND a.claim_version_id=cv.id AND af.tradition_id=$3 AND af.relation_type IN ('self_identified','officially_affiliated','historically_attributed')))
 AND ($4::text IS NULL OR EXISTS(SELECT 1 FROM claim_attributions a JOIN agents ag ON ag.id=a.agent_id AND ag.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed') WHERE (a.source_locator_id IS NULL OR EXISTS(SELECT 1 FROM source_locators sal JOIN sources sas ON sas.id=sal.source_id WHERE sal.id=a.source_locator_id AND sas.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed'))) AND a.claim_version_id=cv.id AND ag.agent_kind=$4))
 AND ($5::text IS NULL OR EXISTS(SELECT 1 FROM claim_attributions a JOIN agents ag ON ag.id=a.agent_id AND ag.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed') WHERE (a.source_locator_id IS NULL OR EXISTS(SELECT 1 FROM source_locators sal JOIN sources sas ON sas.id=sal.source_id WHERE sal.id=a.source_locator_id AND sas.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed'))) AND a.claim_version_id=cv.id AND a.agent_id=$5))
 AND ($6::text IS NULL OR EXISTS(SELECT 1 FROM claim_attributions a JOIN agents ag ON ag.id=a.agent_id AND ag.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed') WHERE (a.source_locator_id IS NULL OR EXISTS(SELECT 1 FROM source_locators sal JOIN sources sas ON sas.id=sal.source_id WHERE sal.id=a.source_locator_id AND sas.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed'))) AND a.claim_version_id=cv.id AND a.attribution_kind=$6))`;
function f(url: URL) { return [url.searchParams.get('tradition_id'),url.searchParams.get('agent_kind'),url.searchParams.get('agent_id'),url.searchParams.get('attribution_kind')]; }
export async function getClaims(id: string | null, include: boolean, url: URL, byPassage = true, mode: Mode = 'research') {
  const condition = byPassage ? `EXISTS(SELECT 1 FROM claim_passages cp JOIN passages p ON p.id=cp.passage_id AND ${validPassage('p')} WHERE cp.claim_version_id=cv.id AND cp.passage_id=$2)` : 'cv.id=$2';
  return queryFor(mode)(`${claimSelect} WHERE ${visible} AND ($2::text IS NULL OR ${condition}) ${filters} ORDER BY cv.id LIMIT 500`, [include,id,...f(url)]);
}
export async function pgRead(path: string[], url: URL, mode: Mode = 'research'): Promise<{ body: object; status?: number }> {
  const inc = url.searchParams.get('include_unverified') === 'true';
  const rows = queryFor(mode);
  if (path.length===1 && path[0]==='corpora') return { body:{ corpora:await rows(`SELECT id,name,corpus_kind,description,data_class FROM corpora WHERE data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed') ORDER BY id LIMIT 500`) } };
  if (path.length===1 && path[0]==='traditions') return { body:{ traditions:await rows(`SELECT id,name,classification_kind,CASE WHEN EXISTS(SELECT 1 FROM traditions parent WHERE parent.id=traditions.parent_id AND parent.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed')) THEN parent_id ELSE NULL END AS parent_id,active_period,data_class FROM traditions WHERE data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed') ORDER BY id LIMIT 500`) } };
  if (path.length===1 && path[0]==='agents') return { body:{ agents:await rows(`SELECT id,display_name,agent_kind,name_disambiguator,data_class FROM agents WHERE data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed') ORDER BY id LIMIT 500`) } };
  if (path.length===1 && path[0]==='reference-schemes') return { body:{ reference_schemes:await rows(`SELECT id,corpus_id,scheme_name,normative_uri,data_class FROM reference_schemes WHERE data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed') AND EXISTS(SELECT 1 FROM corpora pc WHERE pc.id=reference_schemes.corpus_id AND pc.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed')) AND ($1::text IS NULL OR corpus_id=$1) ORDER BY id LIMIT 500`,[url.searchParams.get('corpus_id')]) } };
  if (path.length===1 && path[0]==='passages') return { body:{ passages:await rows(`SELECT id,corpus_id,work_id,scheme_id,external_ref,granularity,location_expression,indexing_status FROM passages p WHERE ${validPassage('p')} AND ($1::text IS NULL OR scheme_id=$1) AND ($2::text IS NULL OR external_ref=$2) AND ($3::text IS NULL OR work_id=$3) ORDER BY id LIMIT 500`,[url.searchParams.get('scheme_id'),url.searchParams.get('ref'),url.searchParams.get('work_id')]) } };
  if (path[0]==='passages' && path.length>=2) {
    const passage=(await rows(`SELECT id,corpus_id,work_id,scheme_id,external_ref,granularity,location_expression,indexing_status FROM passages p WHERE ${validPassage('p')} AND id=$1`,[path[1]]))[0];
    if (!passage) return {body:{error:'Not found'},status:404};
    if (path.length===2) return { body:{ passage } };
    if (path.length===3 && path[2]==='interpretations') return { body:{ passage_id:path[1],interpretations:await getClaims(path[1],inc,url,true,mode) } };
    if (path.length===3 && path[2]==='alignments') return { body:{ alignments:await rows(`SELECT pa.*, CASE WHEN pa.review_status='verified' AND (l.verification_status IS DISTINCT FROM 'checked' OR l.verified_at IS NULL OR length(btrim(l.locator_value))=0 OR s.data_class NOT IN ('source_verified','scholarly_reviewed') OR s.data_class IS NULL) THEN 'proposed' ELSE pa.review_status END AS review_status, to_jsonb(fp) AS from_passage,to_jsonb(tp) AS to_passage, CASE WHEN l.id IS NULL THEN NULL ELSE jsonb_build_object('id',l.id,'source_id',l.source_id,'locator_type',l.locator_type,'locator_value',l.locator_value,'verification_status',l.verification_status,'verified_at',l.verified_at) END AS locator,CASE WHEN s.id IS NULL THEN NULL ELSE jsonb_build_object('id',s.id,'title',s.title,'license_status',s.license_status,'storage_policy',s.storage_policy,'data_class',s.data_class) END AS source FROM passage_alignments pa JOIN passages fp ON fp.id=pa.from_passage_id JOIN passages tp ON tp.id=pa.to_passage_id LEFT JOIN source_locators l ON l.id=pa.source_locator_id LEFT JOIN sources s ON s.id=l.source_id WHERE ${validPassage('fp')} AND ${validPassage('tp')} AND (pa.from_passage_id=$1 OR pa.to_passage_id=$1) AND ($2 OR (pa.review_status='verified' AND l.verification_status='checked' AND l.verified_at IS NOT NULL AND length(btrim(l.locator_value))>0 AND s.data_class IN ('source_verified','scholarly_reviewed'))) AND (s.id IS NULL OR s.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed')) ORDER BY pa.id LIMIT 500`,[path[1],inc]) } };
  }
  if (path[0]==='claims' && path.length===2) {const claim=(await getClaims(path[1],inc,url,false,mode))[0];return claim ? {body:{claim}} : {body:{error:'Not found'},status:404};}
  if (path[0]==='sources' && path.length===2) {const source=(await rows(`SELECT id,title,creator,publication_year,source_kind,source_url,doi,edition_or_version,storage_policy,license_status,license_identifier,license_url,data_class FROM sources WHERE id=$1 AND data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed')`,[path[1]]))[0];return source?{body:{source}}:{body:{error:'Not found'},status:404};}
  if (path[0]==='graph' && path.length===1) {
    const id=url.searchParams.get('passage_id'); if (!id) return {body:{error:'passage_id required'},status:400};
    if (!(await rows(`SELECT p.id FROM passages p WHERE p.id=$1 AND ${validPassage('p')}`,[id])).length) return {body:{error:'Not found'},status:404};
    const claims=await getClaims(id,inc,url,true,mode); const ids=claims.map(c=>c.id);
    const relations=ids.length ? await rows(`SELECT r.*, CASE WHEN r.review_status='verified' AND (l.verification_status IS DISTINCT FROM 'checked' OR l.verified_at IS NULL OR length(btrim(l.locator_value))=0 OR s.data_class NOT IN ('source_verified','scholarly_reviewed') OR s.data_class IS NULL) THEN 'proposed' ELSE r.review_status END AS review_status, CASE WHEN l.id IS NULL THEN NULL ELSE jsonb_build_object('id',l.id,'source_id',l.source_id,'locator_type',l.locator_type,'locator_value',l.locator_value,'verification_status',l.verification_status,'verified_at',l.verified_at) END AS locator, CASE WHEN s.id IS NULL THEN NULL ELSE jsonb_build_object('id',s.id,'title',s.title,'license_status',s.license_status,'storage_policy',s.storage_policy,'data_class',s.data_class) END AS source FROM claim_relations r LEFT JOIN source_locators l ON l.id=r.source_locator_id LEFT JOIN sources s ON s.id=l.source_id WHERE (r.from_version_id=ANY($1::text[]) OR r.to_version_id=ANY($1::text[])) AND ($2 OR (r.review_status='verified' AND l.verification_status='checked' AND l.verified_at IS NOT NULL AND length(btrim(l.locator_value))>0 AND s.data_class IN ('source_verified','scholarly_reviewed'))) AND (s.id IS NULL OR s.data_class IN ('scholarly_candidate','source_verified','scholarly_reviewed')) ORDER BY r.id LIMIT 500`,[ids,inc]):[];
    const neighborIds=[...new Set(relations.flatMap(r=>[r.from_version_id,r.to_version_id]))];
    const neighbors = neighborIds.length ? await rows(`${claimSelect} WHERE ${visible} AND cv.id=ANY($2::text[]) ${filters} ORDER BY cv.id LIMIT 500`,[inc,neighborIds,...f(url)]) : [];
    const nodeMap = new Map([...claims,...neighbors].map(c=>[c.id,c]));
    const allowed = new Set(nodeMap.keys());
    const nodes=[...nodeMap.values()].map(c=>({...c,type:'claim'}));
    const edges: object[] = relations.filter(r=>allowed.has(r.from_version_id)&&allowed.has(r.to_version_id)).map(r=>({...r,type:'claim_relation'}));
    for (const claim of nodeMap.values()) for (const e of claim.evidence) { if (!inc && e.review_status!=='verified') continue; nodes.push({...e,type:'evidence'}); edges.push({id:`evidence:${e.id}`,type:'evidence',from_version_id:claim.id,to_version_id:e.id,relation_type:e.evidence_role,review_status:e.review_status,source_locator_id:e.source_locator_id,locator:e.locator,source:e.source,rationale:e.explanation}); }
    const passageRelations = await rows(`SELECT pr.*, fp.id AS from_id, tp.id AS to_id,
      CASE WHEN pr.review_status='verified' AND (l.verification_status IS DISTINCT FROM 'checked' OR l.verified_at IS NULL OR length(btrim(l.locator_value))=0 OR s.data_class NOT IN ('source_verified','scholarly_reviewed') OR s.data_class IS NULL) THEN 'proposed' ELSE pr.review_status END AS review_status,
      CASE WHEN l.id IS NULL THEN NULL ELSE jsonb_build_object('id',l.id,'source_id',l.source_id,'locator_type',l.locator_type,'locator_value',l.locator_value,'verification_status',l.verification_status,'verified_at',l.verified_at) END AS locator,
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
