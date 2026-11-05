import { NextResponse } from 'next/server';
import { data, warning, claimDetails, interpretations, graph } from '../../../../lib/demo';
import { authorized, createSample, listAudit, listSamples, addReview } from '../../../../lib/admin';
import { pgRead, pgReview, pgAudit, dbWarning } from '../../../../lib/postgres';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
type Context = { params: Promise<{ path: string[] }> };
function respond(body: object, status = 200) {
  return NextResponse.json({ dataset_kind: 'synthetic', warning, ...body }, { status, headers: { 'Cache-Control': 'no-store' } });
}
export async function GET(request: Request, context: Context) {
  const { path } = await context.params;
  const url = new URL(request.url);
  const include = url.searchParams.get('include_unverified') === 'true';
  const dataset = url.searchParams.get('dataset');
  if (dataset && dataset !== 'database' && dataset !== 'synthetic') return respond({ error: 'Invalid dataset' }, 400);
  if (dataset === 'database') {
    const mode = url.searchParams.get('data_mode');
    if (mode && mode !== 'synthetic' && mode !== 'research') return respond({ dataset_kind:'database', warning:dbWarning, error:'Invalid data_mode' },400);
    const synthetic = mode === 'synthetic';
    const dbMeta = { dataset_kind: synthetic ? 'synthetic' : 'database', warning: synthetic ? warning : dbWarning };
    try {
      if (path[0] === 'admin') {
        if (Buffer.byteLength(process.env.SCRIPTURA_ADMIN_TOKEN || '') < 32 || !authorized(request)) return respond({ dataset_kind:'database', warning:dbWarning, error:'Unauthorized' }, 401);
        if (path.length === 2 && path[1] === 'audit') return respond({ dataset_kind:'database', warning:dbWarning, ...(await pgAudit(url.searchParams.get('entity_id'))) });
        return respond({ dataset_kind:'database', warning:dbWarning, error:'Not found' },404);
      }
      const result = await pgRead(path,url,synthetic ? 'synthetic' : 'research');
      return respond({ ...dbMeta, ...result.body },result.status);
    } catch { return respond({ ...dbMeta, error:'Database unavailable or request invalid' },503); }
  }
  if (path[0] === 'admin') {
    if (!authorized(request)) return respond({ error: 'Unauthorized' }, 401);
    if (path.length === 2 && path[1] === 'claims') return respond({ samples: listSamples() });
    if (path.length === 3 && path[1] === 'claims') { const sample = listSamples().find((row) => row.id === path[2]); return sample ? respond({ sample, claim: claimDetails(String(sample.fixture_version_id), true) }) : respond({ error: 'Not found' }, 404); }
    if (path.length === 2 && path[1] === 'audit') return respond({ events: listAudit(url.searchParams.get('entity_id')) });
    return respond({ error: 'Not found' }, 404);
  }
  if (path.length === 1 && path[0] === 'corpora') return respond({ corpora: data.corpora });
  if (path.length === 1 && path[0] === 'traditions') return respond({ traditions: data.traditions });
  if (path.length === 1 && path[0] === 'reference-schemes') return respond({ reference_schemes: data.reference_schemes.filter((s) => !url.searchParams.has('corpus_id') || s.corpus_id === url.searchParams.get('corpus_id')) });
  if (path.length === 1 && path[0] === 'passages') return respond({ passages: data.passages.filter((p) => (!url.searchParams.has('scheme_id') || p.scheme_id === url.searchParams.get('scheme_id')) && (!url.searchParams.has('ref') || p.external_ref === url.searchParams.get('ref'))) });
  if (path[0] === 'passages' && path.length === 2) { const passage = data.passages.find((p) => p.id === path[1]); return passage ? respond({ passage }) : respond({ error: 'Not found' }, 404); }
  if (path[0] === 'passages' && path.length === 3 && path[2] === 'interpretations') {
    if (!data.passages.some((p) => p.id === path[1])) return respond({ error: 'Not found' }, 404);
    return respond({ passage_id: path[1], interpretations: interpretations(path[1], include, url.searchParams.get('tradition_id')), notice: '합성 fixture에는 주장과 전통의 연결이 없습니다.' });
  }
  if (path[0] === 'passages' && path.length === 3 && path[2] === 'alignments') {
    if (!data.passages.some((p) => p.id === path[1])) return respond({ error: 'Not found' }, 404);
    return respond({ alignments: [], notice: 'fixture에 주소 정렬 정보가 없습니다.' });
  }
  if (path[0] === 'claims' && path.length === 2) { const claim = claimDetails(path[1], include); return claim ? respond({ claim }) : respond({ error: 'Not found' }, 404); }
  if (path[0] === 'sources' && path.length === 2) { const source = data.sources.find((s) => s.id === path[1]); return source ? respond({ source }) : respond({ error: 'Not found' }, 404); }
  if (path[0] === 'graph' && path.length === 1) {
    const id = url.searchParams.get('passage_id');
    if (!id || !data.passages.some((p) => p.id === id)) return respond({ error: 'Valid passage_id required' }, 400);
    return respond(graph(id, include));
  }
  return respond({ error: 'Not found' }, 404);
}
export async function POST(request: Request, context: Context) {
  const { path } = await context.params;
  if (path[0] !== 'admin') return respond({ error: 'Not found' }, 404);
  const requestedDataset = new URL(request.url).searchParams.get('dataset');
  if (!authorized(request) || (requestedDataset === 'database' && Buffer.byteLength(process.env.SCRIPTURA_ADMIN_TOKEN || '') < 32)) return respond({ error: 'Unauthorized' }, 401);
  try {
    const body = await request.json();
    if (!body || typeof body !== 'object' || Array.isArray(body)) return respond({ error: 'Invalid request' }, 400);
    const dataset = new URL(request.url).searchParams.get('dataset');
    if (dataset && dataset !== 'database' && dataset !== 'synthetic') return respond({ error:'Invalid dataset' },400);
    if (dataset === 'database') {
      if (path.length === 2 && path[1] === 'reviews') return respond({ dataset_kind:'database', warning:dbWarning, review:await pgReview(body) },201);
      return respond({ dataset_kind:'database', warning:dbWarning, error:'Not found' },404);
    }
    if (path.length === 2 && path[1] === 'claims') {
      if (Object.keys(body).some((key) => key !== 'fixture_version_id')) return respond({ error: 'Only fixture_version_id is accepted; external content cannot be imported' }, 400);
      return respond({ sample: createSample(body.fixture_version_id) }, 201);
    }
    if (path.length === 2 && path[1] === 'reviews') {
      if (Object.keys(body).some((key) => key !== 'sample_id' && key !== 'event')) return respond({ error: 'Invalid fields' }, 400);
      return respond({ review: addReview(body.sample_id, body.event) }, 201);
    }
    return respond({ error: 'Not found' }, 404);
  } catch (e) {
    console.error('Admin operation failed:', e instanceof Error ? e.name : 'unknown error');
    return respond({ error: 'Invalid request or unavailable demo storage' }, 400);
  }
}
