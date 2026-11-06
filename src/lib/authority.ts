/**
 * Authority is a scoped, source-backed observation. This prototype neither
 * judges theology nor treats a publisher, affiliation or peer review as proof.
 */
export const AUTHORITY_KINDS = [
  'normative_adopted', 'official_institutional_guidance',
  'historical_organizational_publication', 'individual_insider_view',
  'external_description_or_criticism', 'scholarly_individual_analysis',
  'plural_or_unresolved',
] as const;
export type AuthorityKind = typeof AUTHORITY_KINDS[number];
export const RIGHTS_ACTIONS = ['browse','collect_metadata','store_raw','store_excerpt','index_fulltext','embed','send_to_model','redistribute','public_link'] as const;
export type QuotationStatus = 'direct_checked'|'translation_checked'|'secondary_report'|'search_only'|'unchecked';
export type AuthorityStatus = 'adoption_documented'|'issuer_documented'|'historical_only'|'individual_only'|'disputed'|'unknown';
export type ArgumentStatus = 'documented_argument'|'externally_challenged'|'cross_checked'|'contested'|'not_assessed';
export type IndependentStatus = 'human_review_documented'|'published_critique_documented'|'none'|'pending';
export type VerificationPath = 'direct'|'translation'|'secondary'|'search'|'unknown';

export interface Evidence {
  issuer_id?: string; issuer_kind?: 'person'|'institution'|'collective';
  issuer_documented?: boolean; document_tradition_id?: string; subject_agent_id?: string; document_source_id?: string; quotation_source_id?: string; verified_attribution?: boolean; publication_date?: string; revised_on?: string;
  valid_from?: string; valid_until?: string; jurisdiction?: string; edition?: string; language?: string;
  exact_locator?: string; locator_checked?: boolean; locator_checked_at?: string; quotation_checked_by?: string; quotation_check_scope?: string; verification_path?: VerificationPath;
  adoption_locator?: string; adoption_locator_checked?: boolean; adoption_checked_at?: string;
  adoption_issuer_id?: string; adoption_tradition_id?: string; formal_adoption_confirmed?: boolean;
  adoption_scope?: string; adoption_document_verified?: boolean; adoption_verified_by?: string; rights_evidence_documented?: boolean; rights_locator?: string; rights_checked_by?: string; rights_checked_at?: string; rights_scope?: string; rights_locator_checked?: boolean; authority_checked_by?: string; authority_checked_at?: string; authority_check_scope?: string; issuer_tradition_locator?: string; issuer_tradition_checked?: boolean; document_source_kind?: string; document_creator?: string;
  argument_locator?: string; argument_evaluator?: string; argument_checked_at?: string; argument_scope?: string; argument_evidence_checked?: boolean; argument_source_id?: string; argument_counter_locator?: string; argument_counter_source_id?: string; argument_counter_checked?: boolean;
  review_locator?: string; review_evaluator?: string; review_checked_at?: string; review_scope?: string; review_evidence_checked?: boolean; review_target_id?: string;
  independent_human?: boolean; review_method?: string; critique_targets_claim?: boolean;
  /** Informational inputs deliberately cannot prove these separate axes. */
  affiliated?: boolean; peer_reviewed_publication?: boolean; source_verified?: boolean;
  citation_kind?: 'bibliographic'|'argument';
}
export interface AuthorityInput {
  id: string; label: string; summary: string; tradition_id: string; issuer: string;
  kind: AuthorityKind; position_scope: string; perspective: 'community_self'|'outsider'|'scholar';
  quotation_status: QuotationStatus; authority_status: AuthorityStatus; argument_status: ArgumentStatus;
  independent_review_status: IndependentStatus; evidence: Evidence; uncertainty: string;
}
const text = (x: unknown): x is string => typeof x === 'string' && x.trim().length > 0;
export function isDate(value: unknown): value is string {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const d = new Date(value + 'T00:00:00Z');
  return Number.isFinite(d.getTime()) && d.toISOString().slice(0,10) === value;
}
function hasQuote(e: Evidence) { return text(e.exact_locator) && e.locator_checked === true && isDate(e.locator_checked_at) && text(e.quotation_checked_by) && text(e.quotation_check_scope); }
function hasRightsEvidence(e: Evidence) { return e.rights_evidence_documented === true && text(e.rights_locator) && e.rights_locator_checked === true && text(e.rights_checked_by) && isDate(e.rights_checked_at) && text(e.rights_scope); }
function hasAuthorityReview(e: Evidence) { return text(e.authority_checked_by) && isDate(e.authority_checked_at) && text(e.authority_check_scope); }
function hasIssuer(e: Evidence, tradition: string, issuer: string) {
  return text(e.issuer_id) && (e.issuer_kind === 'institution' || e.issuer_kind === 'collective') && e.issuer_documented === true && e.document_tradition_id === tradition && e.subject_agent_id === e.issuer_id && text(e.document_source_id) && e.quotation_source_id === e.document_source_id && e.verified_attribution === true && e.document_source_kind === 'official_document' && e.document_creator === issuer && hasAuthorityReview(e) && hasRightsEvidence(e);
}
function hasAdoption(e: Evidence, tradition: string, issuer: string) {
  return hasIssuer(e, tradition, issuer) && hasQuote(e) && (e.verification_path === 'direct' || e.verification_path === 'translation') &&
    isDate(e.publication_date) && isDate(e.revised_on) && e.publication_date <= e.revised_on && isDate(e.valid_from) && isDate(e.valid_until) && e.valid_from <= e.valid_until &&
    text(e.jurisdiction) && text(e.edition) && text(e.language) && text(e.adoption_scope) &&
    text(e.issuer_tradition_locator) && e.issuer_tradition_checked === true && text(e.adoption_locator) && e.adoption_locator_checked === true && isDate(e.adoption_checked_at) &&
    e.adoption_issuer_id === e.issuer_id && e.adoption_tradition_id === tradition &&
    e.formal_adoption_confirmed === true && e.adoption_document_verified === true && text(e.adoption_verified_by) && e.rights_evidence_documented === true;
}
function evidenceRecorded(locator: unknown, evaluator: unknown, checkedAt: unknown, scope: unknown) {
  return text(locator) && text(evaluator) && isDate(checkedAt) && text(scope);
}
/** No trust in raw declared status; return the independently supported values. */
export function evaluateAuthority(raw: AuthorityInput, requestedAsOf?: string|null) {
  const e = raw.evidence;
  let quotation: QuotationStatus = raw.quotation_status;
  if (quotation === 'direct_checked' && (!hasQuote(e) || e.verification_path !== 'direct')) quotation = 'unchecked';
  if (quotation === 'translation_checked' && (!hasQuote(e) || e.verification_path !== 'translation')) quotation = 'unchecked';
  if (quotation === 'secondary_report' && (e.verification_path !== 'secondary' || !hasQuote(e))) quotation = 'unchecked';
  let argument: ArgumentStatus = raw.argument_status;
  if (argument !== 'not_assessed' && (!evidenceRecorded(e.argument_locator,e.argument_evaluator,e.argument_checked_at,e.argument_scope) || e.argument_evidence_checked !== true || e.citation_kind === 'bibliographic' || (['cross_checked','contested'].includes(argument) && (!text(e.argument_source_id) || !text(e.argument_counter_source_id) || e.argument_source_id === e.argument_counter_source_id || !text(e.argument_counter_locator) || e.argument_counter_checked !== true)))) argument = 'not_assessed';
  let independent: IndependentStatus = raw.independent_review_status;
  if (independent === 'human_review_documented' && (!evidenceRecorded(e.review_locator,e.review_evaluator,e.review_checked_at,e.review_scope) || e.independent_human !== true || e.review_evidence_checked !== true || !text(e.review_method) || !text(e.issuer_id) || e.review_evaluator === e.issuer_id || e.review_target_id !== raw.id)) independent = 'pending';
  if (independent === 'published_critique_documented' && (!evidenceRecorded(e.review_locator,e.review_evaluator,e.review_checked_at,e.review_scope) || e.review_evidence_checked !== true || e.critique_targets_claim !== true || e.review_target_id !== raw.id)) independent = 'pending';
  let authority: AuthorityStatus = raw.authority_status;
  let kind: AuthorityKind = raw.kind;
  const asOf = requestedAsOf || new Date().toISOString().slice(0,10);
  const inPeriod = isDate(e.valid_from) && isDate(e.valid_until) && e.valid_from <= asOf && asOf <= e.valid_until;
  const adoption = raw.kind === 'normative_adopted' && raw.perspective === 'community_self' && hasAdoption(e, raw.tradition_id, raw.issuer) && ((e.verification_path === 'direct' && quotation === 'direct_checked') || (e.verification_path === 'translation' && quotation === 'translation_checked')) && e.publication_date! <= asOf && e.revised_on! <= asOf && e.valid_from! <= asOf && asOf <= e.valid_until!;
  if (authority === 'adoption_documented' && !adoption) authority = 'unknown';
  if (kind === 'normative_adopted' && (authority !== 'adoption_documented' || !adoption)) kind = 'plural_or_unresolved';
  if (raw.kind === 'official_institutional_guidance' && (!inPeriod || raw.perspective !== 'community_self' || !hasIssuer(e,raw.tradition_id,raw.issuer) || !hasQuote(e) || (!isDate(e.publication_date) || e.publication_date > asOf || !isDate(e.revised_on) || e.revised_on > asOf || e.publication_date > e.revised_on))) { kind = 'plural_or_unresolved'; authority = 'unknown'; }
  if (authority === 'issuer_documented' && (!inPeriod || raw.perspective !== 'community_self' || !hasIssuer(e,raw.tradition_id,raw.issuer) || !hasQuote(e) || (!isDate(e.publication_date) || e.publication_date > asOf || !isDate(e.revised_on) || e.revised_on > asOf || e.publication_date > e.revised_on))) authority = 'unknown';
  if (raw.perspective === 'outsider' && (raw.kind === 'normative_adopted' || raw.kind === 'official_institutional_guidance')) { kind = 'external_description_or_criticism'; authority = 'unknown'; }
  if (kind === 'historical_organizational_publication') {
    if (authority === 'historical_only' && raw.perspective === 'community_self' && hasIssuer(e,raw.tradition_id,raw.issuer) && hasQuote(e) && isDate(e.publication_date) && e.publication_date <= asOf) authority = 'historical_only';
    else { authority = 'unknown'; kind = 'plural_or_unresolved'; }
  }
  if ((kind === 'individual_insider_view' || kind === 'scholarly_individual_analysis') && (authority !== 'individual_only' || e.issuer_kind !== 'person' || !hasQuote(e) || !isDate(e.publication_date) || e.publication_date > asOf)) authority = 'unknown';
  if (kind === 'external_description_or_criticism' && authority !== 'disputed') authority = 'unknown';
  const uncertain = kind === 'plural_or_unresolved' || authority === 'unknown' || quotation === 'unchecked';
  const rights = Object.fromEntries(RIGHTS_ACTIONS.map(a => [a, false]));
  return {
    id:raw.id, label:raw.label, summary:raw.summary, tradition_id:raw.tradition_id, issuer:raw.issuer,
    kind, authority_kind:kind, position_scope:kind === 'plural_or_unresolved' ? 'insufficient_evidence' : raw.position_scope,
    quotation_status:quotation, authority_status:authority, argument_status:argument, independent_review_status:independent,
    as_of:asOf, as_of_basis:requestedAsOf ? 'requested' : 'current_utc', published_at:e.publication_date ?? null, revised_on:e.revised_on ?? null, effective_from:e.valid_from ?? null, effective_until:e.valid_until ?? null, edition:e.edition ?? null, language:e.language ?? null, jurisdiction:e.jurisdiction ?? null, exact_locator:e.exact_locator ?? null,
    representativity: adoption ? '합성 채택 문서 및 범위 확인' : '공식 채택으로 추정할 근거 없음',
    proof_directness:e.verification_path ?? 'unknown', verification_path:e.verification_path ?? 'unknown', uncertainty:raw.uncertainty,
    assessment:uncertain ? 'insufficient_evidence' : 'documented', rights,
    warning:'합성 데모 / 실제 학술 데이터 아님',
  };
}
const common: Evidence = { exact_locator:'fictional page 1', locator_checked:true, locator_checked_at:'2020-01-02', quotation_checked_by:'synthetic:reviewer', quotation_check_scope:'가상 문언', authority_checked_by:'synthetic:reviewer', authority_checked_at:'2020-01-02', authority_check_scope:'가상 범위', rights_evidence_documented:true, rights_locator:'fictional rights', rights_locator_checked:true, rights_checked_by:'synthetic:reviewer', rights_checked_at:'2020-01-02', rights_scope:'합성 예시만', verification_path:'direct', publication_date:'2020-01-01', jurisdiction:'가상 관할', edition:'가상 판본', language:'ko' };
const official: Evidence = { ...common, issuer_id:'synthetic:institution', issuer_kind:'institution', issuer_documented:true, document_tradition_id:'synthetic:tradition-a', subject_agent_id:'synthetic:institution', document_source_id:'synthetic:document', quotation_source_id:'synthetic:document', verified_attribution:true, document_source_kind:'official_document', document_creator:'가상 기관 A', issuer_tradition_locator:'fictional authority list', issuer_tradition_checked:true, revised_on:'2020-01-01', valid_from:'2020-01-01', valid_until:'2030-12-31', adoption_locator:'fictional resolution 1', adoption_locator_checked:true, adoption_checked_at:'2020-01-02', adoption_issuer_id:'synthetic:institution', adoption_tradition_id:'synthetic:tradition-a', formal_adoption_confirmed:true, adoption_document_verified:true, adoption_verified_by:'synthetic:reviewer', adoption_scope:'가상 전통의 지정된 범위', rights_evidence_documented:true };
export const syntheticAuthority: AuthorityInput[] = [
  {id:'authority:synthetic-official', label:'가상 공동체의 채택 문헌', summary:'가상 공동체가 한정된 범위에서 가상 입장을 채택한 예시입니다.', tradition_id:'synthetic:tradition-a', issuer:'가상 기관 A',kind:'normative_adopted',position_scope:'documented_group_position',perspective:'community_self',quotation_status:'direct_checked',authority_status:'adoption_documented',argument_status:'not_assessed',independent_review_status:'none',evidence:official,uncertainty:'합성 예시이며 이 채택 사실은 실제로 존재하지 않습니다.'},
  {id:'authority:synthetic-guidance',label:'가상 기관의 교육 설명',summary:'기관 설명과 공동체의 채택된 교리는 구분합니다.',tradition_id:'synthetic:tradition-a',issuer:'가상 기관 A',kind:'official_institutional_guidance',position_scope:'documented_local_position',perspective:'community_self',quotation_status:'translation_checked',authority_status:'issuer_documented',argument_status:'not_assessed',independent_review_status:'none',evidence:{...common,verification_path:'translation',issuer_id:'synthetic:institution',issuer_kind:'institution',issuer_documented:true,document_tradition_id:'synthetic:tradition-a',subject_agent_id:'synthetic:institution',document_source_id:'synthetic:document',quotation_source_id:'synthetic:document',verified_attribution:true,document_source_kind:'official_document',document_creator:'가상 기관 A',revised_on:'2020-01-01',valid_from:'2020-01-01',valid_until:'2030-12-31'},uncertainty:'가상 번역을 통한 확인이며 채택 근거는 없습니다.'},
  {id:'authority:synthetic-historical',label:'가상 과거 간행물',summary:'과거 간행물의 입장은 현재로 자동 연장하지 않습니다.',tradition_id:'synthetic:tradition-b',issuer:'가상 기관 B',kind:'historical_organizational_publication',position_scope:'historical_group_position',perspective:'community_self',quotation_status:'direct_checked',authority_status:'historical_only',argument_status:'not_assessed',independent_review_status:'none',evidence:{...common,publication_date:'1951-01-01',issuer_id:'synthetic:publisher',issuer_kind:'institution',issuer_documented:true,document_tradition_id:'synthetic:tradition-b',subject_agent_id:'synthetic:publisher',document_source_id:'synthetic:history',quotation_source_id:'synthetic:history',verified_attribution:true,document_source_kind:'official_document',document_creator:'가상 기관 B'},uncertainty:'현재 입장인지 확인되지 않았습니다.'},
  {id:'authority:synthetic-person',label:'가상 개인 의견',summary:'한 개인의 의견은 그 소속 공동체의 교리가 아닙니다.',tradition_id:'synthetic:tradition-a',issuer:'가상 연구자 A',kind:'individual_insider_view',position_scope:'documented_individual_view',perspective:'community_self',quotation_status:'direct_checked',authority_status:'individual_only',argument_status:'not_assessed',independent_review_status:'none',evidence:{...common,issuer_kind:'person',affiliated:true},uncertainty:'소속은 공식 채택의 근거가 아닙니다.'},
  {id:'authority:synthetic-external',label:'가상 외부 비판',summary:'제3자의 설명은 공동체 자신의 입장이 아닙니다.',tradition_id:'synthetic:tradition-b',issuer:'가상 외부 연구자',kind:'external_description_or_criticism',position_scope:'attributed_by_outsider',perspective:'outsider',quotation_status:'secondary_report',authority_status:'unknown',argument_status:'not_assessed',independent_review_status:'none',evidence:{...common,verification_path:'secondary'},uncertainty:'전언이며 원화자의 직접 확인이 아닙니다.'},
  {id:'authority:synthetic-scholar',label:'가상 학술 분석',summary:'출판 사실과 특정 주장에 대한 독립 심사는 다릅니다.',tradition_id:'synthetic:tradition-b',issuer:'가상 학자 B',kind:'scholarly_individual_analysis',position_scope:'documented_individual_view',perspective:'scholar',quotation_status:'direct_checked',authority_status:'individual_only',argument_status:'not_assessed',independent_review_status:'none',evidence:{...common,issuer_id:'synthetic:scholar',issuer_kind:'person',peer_reviewed_publication:true},uncertainty:'독립된 개별 주장 검수는 기록되지 않았습니다.'},
  {id:'authority:synthetic-unresolved',label:'가상 미확정 다원성',summary:'자료가 부족하거나 여러 견해가 있는 경우를 보류합니다.',tradition_id:'synthetic:plural',issuer:'확인되지 않음',kind:'plural_or_unresolved',position_scope:'insufficient_evidence',perspective:'community_self',quotation_status:'unchecked',authority_status:'unknown',argument_status:'not_assessed',independent_review_status:'none',evidence:{},uncertainty:'대표성과 적용 범위가 확인되지 않았습니다.'},
];
