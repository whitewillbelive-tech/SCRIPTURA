import { test } from 'node:test';
import assert from 'node:assert/strict';
import { evaluateAuthority, syntheticAuthority, RIGHTS_ACTIONS, isDate } from '../src/lib/authority.ts';

const official = () => structuredClone(syntheticAuthority[0]);

test('documented adoption requires explicitly scoped source, adoption and rights evidence without promoting other axes', () => {
  const result = evaluateAuthority(official(), '2025-01-01');
  assert.equal(result.kind, 'normative_adopted');
  assert.equal(result.authority_status, 'adoption_documented');
  assert.equal(result.quotation_status, 'direct_checked');
  assert.equal(result.argument_status, 'not_assessed');
  assert.equal(result.independent_review_status, 'none');
  assert.equal(result.assessment, 'documented');
  assert.deepEqual(Object.keys(result.rights).sort(), [...RIGHTS_ACTIONS].sort());
  assert.ok(Object.values(result.rights).every(v => v === false));
});
test('every mandatory adoption evidence field is required', () => {
  const keys=['issuer_id','issuer_kind','issuer_documented','document_tradition_id','subject_agent_id','document_source_id','quotation_source_id','verified_attribution','publication_date','revised_on','valid_from','valid_until','jurisdiction','edition','language','exact_locator','locator_checked','locator_checked_at','adoption_locator','adoption_locator_checked','adoption_checked_at','adoption_issuer_id','adoption_tradition_id','formal_adoption_confirmed','adoption_document_verified','adoption_verified_by','adoption_scope','rights_evidence_documented','rights_locator','rights_checked_by','rights_checked_at','rights_scope','rights_locator_checked','authority_checked_by','authority_checked_at','authority_check_scope','issuer_tradition_locator','issuer_tradition_checked','document_source_kind','document_creator','quotation_checked_by','quotation_check_scope'];
  for (const key of keys) {
    const raw=official(); delete raw.evidence[key];
    const result=evaluateAuthority(raw,'2025-01-01');
    assert.equal(result.authority_status,'unknown',key); assert.equal(result.kind,'plural_or_unresolved',key);
  }
});
test('a personal post on an official site or different institution cannot establish group adoption', () => {
  for (const changes of [{issuer_kind:'person'}, {subject_agent_id:'different:person'}, {quotation_source_id:'different:document'}, {adoption_issuer_id:'different:institution'}, {adoption_tradition_id:'different:tradition'}, {document_tradition_id:'different:tradition'}]) {
    const raw=official(); Object.assign(raw.evidence, changes); raw.evidence.affiliated=true;
    assert.equal(evaluateAuthority(raw,'2025-01-01').assessment,'insufficient_evidence');
  }
});
test('adoption is bounded by publication, revision, scope and valid explicit or current date', () => {
  const raw=official();
  for (const date of ['2019-12-31','2031-01-01']) assert.equal(evaluateAuthority(raw,date).kind,'plural_or_unresolved');
  const future=official(); future.evidence.revised_on='2029-01-01'; assert.equal(evaluateAuthority(future,'2025-01-01').authority_status,'unknown');
  const inverted=official(); inverted.evidence.revised_on='2019-01-01'; assert.equal(evaluateAuthority(inverted,'2025-01-01').authority_status,'unknown');
  assert.equal(evaluateAuthority(raw).as_of_basis,'current_utc');
  assert.equal(isDate('2025-02-30'),false);
});
test('historical records require evidence and are never automatically made current', () => {
  const historical=structuredClone(syntheticAuthority[2]);
  const out=evaluateAuthority(historical,'2026-11-06');
  assert.equal(out.published_at,'1951-01-01'); assert.equal(out.authority_status,'historical_only');
  assert.notEqual(out.kind,'normative_adopted'); assert.match(out.uncertainty,/현재/);
  delete historical.evidence.publication_date;
  assert.equal(evaluateAuthority(historical,'2026-11-06').assessment,'insufficient_evidence');
  const unknown=structuredClone(syntheticAuthority[2]);unknown.authority_status='unknown';
  assert.notEqual(evaluateAuthority(unknown,'2026-11-06').authority_status,'historical_only');
});
test('direct quotation cannot be invented from translation or a secondary report', () => {
  const raw=official();raw.evidence.verification_path='translation';
  assert.equal(evaluateAuthority(raw,'2025-01-01').quotation_status,'unchecked');
  raw.evidence.verification_path='secondary';
  assert.equal(evaluateAuthority(raw,'2025-01-01').quotation_status,'unchecked');
});
test('bibliographic citation alone cannot support a direct argument', () => {
  const raw=official();raw.argument_status='cross_checked';Object.assign(raw.evidence,{argument_locator:'fictional loc',argument_evaluator:'fictional evaluator',argument_checked_at:'2020-01-02',argument_scope:'test',argument_evidence_checked:true,citation_kind:'bibliographic'});
  assert.equal(evaluateAuthority(raw,'2025-01-01').argument_status,'not_assessed');
});
test('peer review is not proof of independent human review of this claim', () => {
  const raw=official();raw.independent_review_status='human_review_documented';raw.evidence.peer_reviewed_publication=true;
  assert.equal(evaluateAuthority(raw,'2025-01-01').independent_review_status,'pending');
  Object.assign(raw.evidence,{review_locator:'fictional loc',review_evaluator:raw.evidence.issuer_id,review_checked_at:'2020-01-02',review_scope:'specific claim',review_evidence_checked:true,independent_human:true,review_method:'fictional review'});
  assert.equal(evaluateAuthority(raw,'2025-01-01').independent_review_status,'pending');
});
test('unknown or conditional rights never permit any of nine content actions', () => {
  for (const raw of syntheticAuthority) assert.ok(Object.values(evaluateAuthority(raw,'2025-01-01').rights).every(x=>x===false));
});
test('outsider reporting cannot become community self-attestation', () => {
  const raw=official();raw.perspective='outsider';
  const out=evaluateAuthority(raw,'2025-01-01');
  assert.equal(out.kind,'external_description_or_criticism'); assert.equal(out.authority_status,'unknown');
});

test('institutional guidance requires the requesting date in an evidenced period', () => {
  const raw=structuredClone(syntheticAuthority[1]);
  assert.equal(evaluateAuthority(raw,'2025-01-01').kind,'official_institutional_guidance');
  delete raw.evidence.valid_until;
  assert.equal(evaluateAuthority(raw,'2025-01-01').assessment,'insufficient_evidence');
  const past=structuredClone(syntheticAuthority[1]); past.evidence.publication_date='1951-01-01'; past.evidence.revised_on='1951-01-01'; past.evidence.valid_from='1951-01-01';past.evidence.valid_until='1951-12-31';
  assert.equal(evaluateAuthority(past,'2026-11-06').kind,'plural_or_unresolved');
});
test('checked quotation and independent review need specific reviewer, scope and target', () => {
  const raw=official(); delete raw.evidence.quotation_check_scope;
  assert.equal(evaluateAuthority(raw,'2025-01-01').quotation_status,'unchecked');
  assert.equal(evaluateAuthority(raw,'2025-01-01').assessment,'insufficient_evidence');
  const other=official();other.independent_review_status='human_review_documented';
  Object.assign(other.evidence,{review_locator:'fictional loc',review_evaluator:'synthetic:other',review_checked_at:'2020-01-02',review_scope:'specific claim',review_evidence_checked:true,independent_human:true,review_method:'fictional review',review_target_id:'different'});
  assert.equal(evaluateAuthority(other,'2025-01-01').independent_review_status,'pending');
});
test('individual and historical raw unknown statuses are never automatically upgraded', () => {
  for (const index of [2,3,5]) { const raw=structuredClone(syntheticAuthority[index]); raw.authority_status='unknown'; assert.notEqual(evaluateAuthority(raw,'2025-01-01').authority_status,'individual_only'); assert.notEqual(evaluateAuthority(raw,'2025-01-01').authority_status,'historical_only'); }
});
