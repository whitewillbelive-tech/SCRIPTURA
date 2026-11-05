"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

type Corpus = { id: string; name: string };
type Scheme = { id: string; scheme_name: string };
type Passage = { id: string; external_ref: string; scheme_id: string; work_id: string };
type Tradition = { id: string; name: string; classification_kind: string };
type Agent = { id: string; display_name: string; agent_kind: string };
type Source = { title: string; data_class?: string; storage_policy: string; license_status: string };
type Locator = { locator_value?: string; verification_status?: string; verified_at?: string | null };
type Claim = { id: string; statement: string; review_status: string; data_class?: string; attributions?: { id: string; attribution_kind: string; attribution_status: string; agent?: Agent | null }[]; evidence?: { id: string; explanation: string; evidence_role?: string; review_status: string; locator?: Locator | null; source?: Source | null }[] };
type Alignment = { id: string; from_passage_id: string; to_passage_id: string; alignment_type: string; review_status: string; from_passage?: Passage; to_passage?: Passage; source_locator_id?: string | null; locator?: Locator | null; source?: Source | null };
type GraphNode = { id: string; type?: string; statement?: string; label?: string; explanation?: string; external_ref?: string; data_class?: string; evidence?: Claim["evidence"] };
type GraphEdge = { id: string; from_version_id?: string; to_version_id?: string; source?: string | Source; target?: string; from?: string; to?: string; relation_type?: string; edgeType?: string; review_status?: string; source_locator_id?: string | null; locator?: Locator | null; rationale?: string };
type Graph = { nodes: GraphNode[]; edges: GraphEdge[] };
const base = "/api/v1";
const dataset = "database";
const classLabel = (value?: string) => ({ synthetic: "합성", unclassified: "분류 미확인", scholarly_candidate: "연구 후보", source_verified: "출처 검증", scholarly_reviewed: "학술 검토" }[value ?? ""] ?? value ?? "분류 미확인");
function query(values: Record<string, string | boolean | undefined>, dataMode: string) {
  const p = new URLSearchParams({ dataset });
  if (dataMode === "synthetic") p.set("data_mode", "synthetic");
  Object.entries(values).forEach(([key, value]) => { if (value === true) p.set(key, "true"); else if (typeof value === "string" && value) p.set(key, value); });
  return p.toString();
}
async function get<T>(path: string, signal: AbortSignal): Promise<T> {
  const result = await fetch(`${base}${path}`, { cache: "no-store", signal });
  if (!result.ok) throw new Error(`데이터베이스 조회 실패 (${result.status})`);
  return await result.json() as T;
}
function isAbort(error: unknown) { return error instanceof Error && error.name === "AbortError"; }

export default function Explore() {
  const [dataMode, setDataMode] = useState("research");
  const [corpora, setCorpora] = useState<Corpus[]>([]);
  const [schemes, setSchemes] = useState<Scheme[]>([]);
  const [passages, setPassages] = useState<Passage[]>([]);
  const [traditions, setTraditions] = useState<Tradition[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [corpus, setCorpus] = useState("");
  const [scheme, setScheme] = useState("");
  const [reference, setReference] = useState("");
  const [appliedRef, setAppliedRef] = useState("");
  const [passage, setPassage] = useState("");
  const [tradition, setTradition] = useState("");
  const [agent, setAgent] = useState("");
  const [classFilter, setClassFilter] = useState("");
  const [rightsUnknown, setRightsUnknown] = useState(false);
  const [includeUnverified, setIncludeUnverified] = useState(false);
  const [claims, setClaims] = useState<Claim[]>([]);
  const [selected, setSelected] = useState("");
  const [alignments, setAlignments] = useState<Alignment[]>([]);
  const [graph, setGraph] = useState<Graph>({ nodes: [], edges: [] });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const c = new AbortController();
    setCorpora([]); setTraditions([]); setAgents([]); setCorpus(""); setScheme(""); setPassage(""); setClaims([]); setGraph({ nodes: [], edges: [] }); setAlignments([]);
    Promise.all([
      get<{ corpora: Corpus[] }>(`/corpora?${query({}, dataMode)}`, c.signal),
      get<{ traditions: Tradition[] }>(`/traditions?${query({}, dataMode)}`, c.signal),
      get<{ agents: Agent[] }>(`/agents?${query({}, dataMode)}`, c.signal),
    ]).then(([a, b, d]) => { setCorpora(a.corpora); setTraditions(b.traditions); setAgents(d.agents); setCorpus(a.corpora[0]?.id ?? ""); setError(""); })
      .catch((e: unknown) => { if (!isAbort(e)) setError("데이터베이스를 불러올 수 없습니다. 연결과 서버 설정을 확인해 주세요."); });
    return () => c.abort();
  }, [dataMode]);
  useEffect(() => {
    const c = new AbortController(); setScheme(""); setPassage(""); setSchemes([]); setPassages([]);
    if (corpus) get<{ reference_schemes: Scheme[] }>(`/reference-schemes?${query({ corpus_id: corpus }, dataMode)}`, c.signal)
      .then(r => { setSchemes(r.reference_schemes); setScheme(r.reference_schemes[0]?.id ?? ""); })
      .catch((e: unknown) => { if (!isAbort(e)) setError("주소 체계를 불러오지 못했습니다."); });
    return () => c.abort();
  }, [corpus, dataMode]);
  useEffect(() => {
    const c = new AbortController(); setPassage(""); setPassages([]);
    if (scheme) get<{ passages: Passage[] }>(`/passages?${query({ scheme_id: scheme, ref: appliedRef }, dataMode)}`, c.signal)
      .then(r => { setPassages(r.passages); setPassage(r.passages[0]?.id ?? ""); })
      .catch((e: unknown) => { if (!isAbort(e)) setError("본문 주소를 불러오지 못했습니다."); });
    return () => c.abort();
  }, [scheme, appliedRef, dataMode]);
  useEffect(() => {
    const c = new AbortController(); setClaims([]); setGraph({ nodes: [], edges: [] }); setAlignments([]); setSelected("");
    if (!passage) { setLoading(false); return () => c.abort(); }
    setLoading(true); setError("");
    const filters = { tradition_id: tradition, agent_id: agent, include_unverified: includeUnverified };
    const path = `/passages/${encodeURIComponent(passage)}`;
    Promise.all([
      get<{ interpretations: Claim[] }>(`${path}/interpretations?${query(filters, dataMode)}`, c.signal),
      get<{ alignments: Alignment[] }>(`${path}/alignments?${query({ include_unverified: includeUnverified }, dataMode)}`, c.signal),
      get<Graph>(`/graph?${query({ passage_id: passage, ...filters }, dataMode)}`, c.signal),
    ]).then(([a, b, d]) => { setClaims(a.interpretations); setSelected(a.interpretations[0]?.id ?? ""); setAlignments(b.alignments); setGraph(d); })
      .catch((e: unknown) => { if (!isAbort(e)) setError("주장, 주소 대응 또는 관계를 불러오지 못했습니다."); })
      .finally(() => { if (!c.signal.aborted) setLoading(false); });
    return () => c.abort();
  }, [passage, tradition, agent, includeUnverified, dataMode]);

  const visibleClaims = useMemo(() => claims.filter(c => (!classFilter || c.data_class === classFilter) && (!rightsUnknown || !c.evidence?.length || c.evidence.some(e => !e.source || e.source.license_status !== "verified"))), [claims, classFilter, rightsUnknown]);
  const active = visibleClaims.find(c => c.id === selected) ?? visibleClaims[0];
  const agentGroups = ["person", "institution", "collective"];
  const graphClaims = graph.nodes.filter(n => n.type === "claim" && (!classFilter || n.data_class === classFilter) && (!rightsUnknown || !n.evidence?.length || n.evidence.some(e => !e.source || e.source.license_status !== "verified")));
  const visibleIds = new Set([...visibleClaims.map(c => c.id), ...graphClaims.map(c => c.id), ...graph.nodes.filter(n => n.type === "passage").map(n => n.id)]);
  const visibleEvidenceIds = new Set([...visibleClaims.flatMap(c => c.evidence?.map(e => e.id) ?? []), ...graphClaims.flatMap(c => c.evidence?.map(e => e.id) ?? [])]);
  const visibleEdges = graph.edges.filter(e => { const from = e.from_version_id ?? e.from ?? (typeof e.source === "string" ? e.source : undefined); const to = e.to_version_id ?? e.to ?? e.target; return !!from && !!to && (visibleIds.has(from) || visibleEvidenceIds.has(from)) && (visibleIds.has(to) || visibleEvidenceIds.has(to)); });
  const labelNode = (id?: string) => graph.nodes.find(n => n.id === id)?.label || graph.nodes.find(n => n.id === id)?.statement || graph.nodes.find(n => n.id === id)?.explanation || graph.nodes.find(n => n.id === id)?.external_ref || claims.find(c => c.id === id)?.statement || id || "정보 없음";
  const confirmed = (status?: string, locator?: Locator | null, locatorId?: string | null, source?: Source | string | null) => status === "verified" && Boolean(locatorId) && locator?.verification_status === "checked" && Boolean(locator.verified_at) && Boolean(locator.locator_value?.trim()) && !!source && typeof source !== "string" && (source.data_class === "source_verified" || source.data_class === "scholarly_reviewed");
  return <main>
    <div className="notice"><span className="notice-dot"/> {dataMode === "synthetic" ? "합성 테스트 / 실제 학술 데이터 아님" : "연구 자료 탐색 · 검증과 권리 상태를 개별 확인해 주세요"}</div>
    <header className="topbar"><Link className="brand" href="/"><span className="brand-mark">S</span><span>SCRIPTURA<small>RESEARCH EXPLORER</small></span></Link><Link href="/">합성 데모로 돌아가기</Link></header>
    <div className="shell"><section className="intro compact-intro"><div><div className="eyebrow">DATABASE EXPLORER</div><h1>출처를 따라<br/><em>관계를 살펴보세요.</em></h1><p>정경과 주소 체계를 선택하고, 귀속·검증 및 권리 상태를 확인하세요. 실제 데이터의 학술 검증이나 권리를 이 화면이 보증하지 않습니다.</p><p>Work S-1A 연구 자료는 아직 통합되지 않았습니다.</p></div></section>
      <section className="workspace" aria-label="연구 자료 탐색"><aside className="sidebar">
        <div className="section-label"><span>탐색 설정</span></div>
        <label htmlFor="data-mode"><strong>자료 집합</strong></label><select id="data-mode" value={dataMode} onChange={e => { setClaims([]); setSelected(""); setGraph({ nodes: [], edges: [] }); setAlignments([]); setCorpus(""); setScheme(""); setPassage(""); setDataMode(e.target.value); setClassFilter(""); setReference(""); setAppliedRef(""); setTradition(""); setAgent(""); setIncludeUnverified(false); }}><option value="research">연구 자료</option><option value="synthetic">합성 테스트 자료</option></select>
        <label htmlFor="corpus"><strong>정경 · 코퍼스</strong></label><select id="corpus" value={corpus} onChange={e => setCorpus(e.target.value)}><option value="">선택</option>{corpora.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
        <label htmlFor="scheme"><strong>장절 · 주소 체계</strong></label><select id="scheme" value={scheme} onChange={e => setScheme(e.target.value)}><option value="">선택</option>{schemes.map(s => <option key={s.id} value={s.id}>{s.scheme_name}</option>)}</select>
        <form onSubmit={e => { e.preventDefault(); setAppliedRef(reference.trim()); }}><label htmlFor="reference"><strong>본문 주소 검색</strong></label><input id="reference" value={reference} onChange={e => setReference(e.target.value)} placeholder="예: Isa.7.14"/><button className="search-button" type="submit">검색</button></form>
        <label htmlFor="db-passage"><strong>본문 선택</strong></label><select id="db-passage" value={passage} onChange={e => setPassage(e.target.value)}><option value="">선택</option>{passages.map(p => <option value={p.id} key={p.id}>{p.external_ref}</option>)}</select>
        <label htmlFor="db-tradition"><strong>종교 · 교단 · 교파</strong></label><select id="db-tradition" value={tradition} onChange={e => setTradition(e.target.value)}><option value="">전체</option>{traditions.map(t => <option key={t.id} value={t.id}>{t.name} ({t.classification_kind})</option>)}</select>
        <label htmlFor="agent"><strong>연구자 · 기관</strong></label><select id="agent" value={agent} onChange={e => setAgent(e.target.value)}><option value="">전체</option>{agentGroups.map(group => <optgroup key={group} label={{ person: "개인 연구자", institution: "기관", collective: "단체" }[group]}>{agents.filter(a => a.agent_kind === group).map(a => <option key={a.id} value={a.id}>{a.display_name}</option>)}</optgroup>)}</select>
        <label htmlFor="data-class"><strong>자료 분류</strong></label><select id="data-class" value={classFilter} onChange={e => { setSelected(""); setClassFilter(e.target.value); }}><option value="">전체 분류</option><option value="scholarly_candidate">연구 후보</option><option value="source_verified">출처 검증</option><option value="scholarly_reviewed">학술 검토</option></select>
        <div className="toggle-box"><label className="toggle-label"><input type="checkbox" checked={rightsUnknown} onChange={e => setRightsUnknown(e.target.checked)}/><span><strong>권리 미확인 자료만</strong><small>출처가 없거나 권리 상태가 검증되지 않은 자료입니다.</small></span></label></div>
        <div className="toggle-box"><label className="toggle-label"><input type="checkbox" checked={includeUnverified} onChange={e => setIncludeUnverified(e.target.checked)}/><span><strong>검증 대기 자료 포함</strong><small>검증 상태와 출처 위치가 불확실한 자료를 별도로 표시합니다.</small></span></label></div>
      </aside><div className="content">
        {error && <div className="error" role="alert">{error}</div>}
        <div className="content-heading"><div><div className="eyebrow">SELECTED PASSAGE</div><h2>{passages.find(p => p.id === passage)?.external_ref ?? "본문 선택"}</h2><p>원문은 제공하지 않습니다. 자료 분류와 권리 상태를 확인하세요.</p></div><span className="outline-pill">{dataMode === "synthetic" ? "합성 테스트" : "연구 자료"}</span></div>
        <section className="alignments"><div className="section-label"><span>ADDRESS ALIGNMENTS</span></div><h3>다른 주소 체계 대응</h3>{alignments.length ? alignments.map(a => {
          const other = a.from_passage_id === passage ? a.to_passage : a.from_passage;
          return <p key={a.id}><strong>{other?.external_ref ?? (a.from_passage_id === passage ? a.to_passage_id : a.from_passage_id)}</strong> · 체계: {other?.scheme_id ?? "미확인"} · {a.alignment_type} · {confirmed(a.review_status, a.locator, a.source_locator_id, a.source) ? "검증됨" : "확정되지 않음"} ({a.review_status}) · {a.locator?.locator_value || "출처 위치 미확인"}</p>;
        }) : <p>표시할 주소 대응이 없습니다.</p>}</section>
        <div className="claims-head"><div><div className="section-label"><span>INTERPRETATIONS</span></div><h3>주장 살펴보기</h3></div><span className="count">{visibleClaims.length}개의 주장</span></div>
        {loading ? <div className="empty">불러오는 중입니다...</div> : visibleClaims.length === 0 ? <div className="empty"><strong>표시할 주장이 없습니다</strong><p>필터나 검증 상태를 확인하세요.</p></div> : <div className="claim-list">{visibleClaims.map(c => <button className={`claim ${active?.id === c.id ? "active" : ""}`} key={c.id} onClick={() => setSelected(c.id)}><span className="claim-body"><span className="claim-status">{classLabel(c.data_class)} · {c.review_status}</span><strong>{c.statement}</strong><small>{c.attributions?.map(a => `${a.agent?.display_name ?? "미상"} · ${a.attribution_kind}`).join(", ") || "귀속 정보 없음"}</small></span></button>)}</div>}
        {active && <section className="detail" aria-live="polite"><div className="section-label"><span>CLAIM DETAILS</span></div><h3>주장과 출처</h3><p className="detail-quote">“{active.statement}”</p><div className="detail-grid"><div><h4>귀속 및 검증</h4><p>{classLabel(active.data_class)} · {active.review_status}</p>{active.attributions?.map(a => <p key={a.id}>{a.agent?.display_name ?? "미상"} · {a.attribution_kind} · {a.attribution_status}</p>)}</div><div><h4>근거 및 출처</h4>{active.evidence?.length ? active.evidence.map(e => <div key={e.id}><p><b>{e.source?.title ?? "출처 정보 없음"}</b> · {classLabel(e.source?.data_class)}</p><p>{e.evidence_role} · {e.explanation} · {e.review_status}</p><p>출처 위치: {e.locator?.locator_value ?? "미확인"} · {e.locator?.verification_status ?? "미검증"}</p><p>저장 정책: {e.source?.storage_policy ?? "미상"} / 권리: {e.source?.license_status ?? "미상"}</p></div>) : <p>등록된 근거가 없습니다.</p>}</div></div></section>}
        <section className="graph"><div className="section-label"><span>RELATIONSHIP MAP</span></div><div className="graph-heading"><div><h3>주장 · 근거 · 반론 · 상호 참조</h3><p>출처 위치와 검증 상태가 확인되지 않은 관계는 확정되지 않음으로 표시합니다.</p></div></div>{visibleEdges.length ? visibleEdges.map(e => <div className="graph-edge" key={e.id}><div>{labelNode(e.from_version_id ?? e.from ?? (typeof e.source === "string" ? e.source : undefined))}</div><div className="edge-label">↓ {e.relation_type ?? e.edgeType ?? "관계"} · {confirmed(e.review_status, e.locator, e.source_locator_id, e.source) ? "검증됨" : "확정되지 않음"} ({e.review_status ?? "미검증"})</div><div>{labelNode(e.to_version_id ?? e.to ?? e.target)}</div><p>출처: {typeof e.source === "object" && e.source ? e.source.title : "미확인"} · 출처 위치: {e.locator?.locator_value ?? "미확인"}</p>{e.rationale && <p>{e.rationale}</p>}</div>) : <p className="graph-empty">현재 선택에서 표시할 관계가 없습니다.</p>}</section>
      </div></section><footer><div><strong>SCRIPTURA</strong><p>자료의 검증 및 권리 상태를 개별 확인하세요.</p></div><div className="footer-right">AI 답변 <span>후속 단계 · 비활성</span></div></footer></div>
  </main>;
}
