import fixture from '../../fixtures/demo_valid.json';

export const warning = '합성 데모 / 실제 학술 데이터 아님 — 검증되지 않은 가상 데이터';
const data = fixture;
const verified = new Set(['source_verified', 'scholarly_reviewed']);
export const isVisible = (status: string, includeUnverified: boolean) => includeUnverified || verified.has(status);

export function claimDetails(id: string, includeUnverified: boolean) {
  const claim = data.claim_versions.find((v) => v.id === id);
  if (!claim || !isVisible(claim.review_status, includeUnverified)) return null;
  const attributions = data.claim_attributions.filter((a) => a.claim_version_id === id).map((a) => ({ ...a, agent: data.agents.find((agent) => agent.id === a.agent_id) ?? null }));
  const evidence = data.claim_evidence.filter((e) => e.claim_version_id === id).map((e) => {
    const locator = data.source_locators.find((l) => l.id === e.source_locator_id);
    const source = data.sources.find((s) => s.id === locator?.source_id);
    return { ...e, locator: locator ?? null, source: source ?? null };
  });
  // The starter does not include agent affiliations; do not infer them from names.
  return { ...claim, attributions, evidence, tradition_ids: [] as string[], display_warning: warning };
}
export function interpretations(passageId: string, includeUnverified: boolean, traditionId?: string | null) {
  return data.claim_passages.filter((link) => link.passage_id === passageId)
    .map((link) => claimDetails(link.claim_version_id, includeUnverified))
    .filter((item): item is NonNullable<typeof item> => item !== null && (!traditionId || item.tradition_ids.includes(traditionId)));
}
export function graph(passageId: string, includeUnverified: boolean) {
  const nodes = interpretations(passageId, includeUnverified);
  const ids = new Set(nodes.map((n) => n.id));
  const edges = data.claim_relations.filter((r) => ids.has(r.from_version_id) && ids.has(r.to_version_id) && (includeUnverified || r.review_status === 'verified'));
  return { nodes, edges };
}
export { data };

// Rights are explicit capabilities, not inferred from a verified license alone.
export function permitsContent(source: { storage_policy: string; license_status: string }, action: 'store' | 'embed' | 'redistribute', explicitPermission = false) {
  return explicitPermission && source.license_status === 'verified' && source.storage_policy === 'full_text_allowed' && ['store', 'embed', 'redistribute'].includes(action);
}
