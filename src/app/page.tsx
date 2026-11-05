"use client";

import { useEffect, useState } from "react";

type Passage = { id: string; external_ref: string; granularity: string };
type Tradition = { id: string; name: string; classification_kind: string };
type Source = { title: string; creator?: string; storage_policy: string; license_status: string };
type Locator = { locator_value: string; verification_status: string };
type Claim = { id: string; claim_id: string; statement: string; review_status: string; revision_no: number; attributions: { id: string; attribution_kind: string; attribution_status: string; agent?: { display_name: string } }[]; evidence: { id: string; explanation: string; review_status: string; locator?: Locator; source?: Source }[] };
type Edge = { id: string; from_version_id: string; to_version_id: string; relation_type: string; review_status: string; rationale?: string };

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, { cache: "no-store", signal });
  if (!response.ok) throw new Error(`조회 실패 (${response.status})`);
  return response.json() as Promise<T>;
}

export default function Home() {
  const [passages, setPassages] = useState<Passage[]>([]);
  const [traditions, setTraditions] = useState<Tradition[]>([]);
  const [passage, setPassage] = useState("");
  const [tradition, setTradition] = useState("");
  const [showUnverified, setShowUnverified] = useState(false);
  const [claims, setClaims] = useState<Claim[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([get<{ passages: Passage[] }>("/api/v1/passages"), get<{ traditions: Tradition[] }>("/api/v1/traditions")])
      .then(([p, t]) => { setPassages(p.passages); setTraditions(t.traditions); setPassage(p.passages[0]?.id ?? ""); })
      .catch(() => { setError("데모 데이터를 불러오지 못했습니다. 서버 상태를 확인해 주세요."); setLoading(false); });
  }, []);
  useEffect(() => {
    if (!passage) return;
    const controller = new AbortController();
    const load = async () => {
    setLoading(true); setError(""); setClaims([]); setEdges([]); setSelected(null);
    const params = new URLSearchParams();
    if (tradition) params.set("tradition_id", tradition);
    if (showUnverified) params.set("include_unverified", "true");
    const graphParams = new URLSearchParams({ passage_id: passage });
    if (showUnverified) graphParams.set("include_unverified", "true");
    try {
      const [c, g] = await Promise.all([
        get<{ interpretations: Claim[] }>(`/api/v1/passages/${encodeURIComponent(passage)}/interpretations?${params}`, controller.signal),
        get<{ edges: Edge[] }>(`/api/v1/graph?${graphParams}`, controller.signal),
      ]);
      setClaims(c.interpretations); setEdges(g.edges); setSelected(c.interpretations[0]?.id ?? null);
    } catch { if (!controller.signal.aborted) { setError("주장과 관계를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요."); setClaims([]); setEdges([]); setSelected(null); } }
    finally { if (!controller.signal.aborted) setLoading(false); }
    };
    void load();
    return () => controller.abort();
  }, [passage, tradition, showUnverified]);
  const active = claims.find(c => c.id === selected);
  const visibleEdges = edges.filter(e => claims.some(c => c.id === e.from_version_id) && claims.some(c => c.id === e.to_version_id));
  const short = (id: string) => claims.find(c => c.id === id)?.statement ?? id;
  return <main>
    <div className="notice"><span className="notice-dot"/> 합성 데모 / 실제 학술 데이터 아님 <span className="notice-note">모든 주장과 출처는 개발을 위한 가상 예시입니다.</span></div>
    <header className="topbar"><a className="brand" href="/"><span className="brand-mark">S</span><span>SCRIPTURA<small>INTERPRETATION EXPLORER</small></span></a><a className="header-badge" href="/explore">연구 자료 탐색 →</a></header>
    <div className="shell">
      <section className="intro"><div><div className="eyebrow"><span>01</span> INTERPRETATION EXPLORER</div><h1>하나의 본문,<br/><em>다양한 관점.</em></h1><p>본문을 선택하고 가상의 주장과 그 근거를 살펴보세요.<br/>해석의 연결을 따라가며 출처와 검증 상태를 함께 확인할 수 있습니다.</p></div><div className="intro-mark" aria-hidden="true">§<span>TEXT / CONTEXT / CONNECTION</span></div></section>
      <section className="workspace" aria-label="본문 탐색">
        <aside className="sidebar"><div className="section-label"><span>탐색 설정</span><span>01 — 02</span></div><h2>어디서 시작할까요?</h2><p className="muted">본문과 관점을 선택해 주세요.</p>
          <label htmlFor="passage">01 <strong>본문 주소</strong></label><select id="passage" value={passage} onChange={e => { setClaims([]); setSelected(null); setPassage(e.target.value); }}>{passages.map(p => <option key={p.id} value={p.id}>{p.external_ref}</option>)}</select>
          <label htmlFor="tradition">02 <strong>해석 전통</strong></label><select id="tradition" value={tradition} onChange={e => { setClaims([]); setSelected(null); setTradition(e.target.value); }}><option value="">모든 전통</option>{traditions.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}</select>
          <p className="help">데모에는 전통과 주장의 연결이 없어 전통 필터 결과가 비어 있습니다.</p>
          <div className="toggle-box"><label className="toggle-label"><input type="checkbox" checked={showUnverified} onChange={e => { setClaims([]); setSelected(null); setShowUnverified(e.target.checked); }}/><span><strong>미검증 예시 표시</strong><small>기본적으로 검증된 주장만 표시합니다.</small></span></label></div>
          <div className="sidebar-foot"><span>✳</span><p>이 화면의 모든 자료는 합성 데모입니다. 실제 학술 자료나 신학적 판단이 아닙니다.</p></div>
        </aside>
        <div className="content"><div className="content-heading"><div><div className="eyebrow">SELECTED PASSAGE</div><h2>{passages.find(p => p.id === passage)?.external_ref ?? "본문 선택"}</h2><p>본문 원문은 제공하지 않습니다. 주소와 합성 해석 예시를 탐색하세요.</p></div><span className="outline-pill">합성 데이터</span></div>
          {error && <div className="error" role="alert">{error}</div>}
          <div className="claims-head"><div><div className="section-label"><span>INTERPRETATIONS</span><span>03</span></div><h3>주장 살펴보기</h3></div><span className="count">{claims.length}개의 주장</span></div>
          {loading ? <div className="empty">불러오는 중입니다...</div> : claims.length === 0 ? <div className="empty"><span>◇</span><strong>표시할 주장이 없습니다</strong><p>{tradition ? "선택한 전통에 연결된 데모 주장이 없습니다." : "검증된 데모 주장이 없습니다. 미검증 예시를 보려면 왼쪽 설정을 켜 주세요."}</p></div> : <div className="claim-list">{claims.map((c, i) => <button className={`claim ${selected === c.id ? "active" : ""}`} key={c.id} onClick={() => setSelected(c.id)}><span className="claim-index">0{i+1}</span><span className="claim-body"><span className="claim-status">{c.review_status} <span>·</span> 합성 예시</span><strong>{c.statement}</strong><small>{c.attributions?.map(a => a.agent?.display_name ?? a.attribution_kind).join(", ") || "귀속 정보 없음"}</small></span><span className="arrow">↗</span></button>)}</div>}
          {active && <section className="detail" aria-live="polite"><div className="section-label"><span>CLAIM DETAILS</span><span>04</span></div><h3>주장과 출처</h3><p className="detail-quote">“{active.statement}”</p><div className="detail-grid"><div><h4>귀속 및 검증</h4><p>주장 상태 <b>{active.review_status}</b></p>{active.attributions?.map(a => <p key={a.id}>{a.agent?.display_name ?? "미상"} · {a.attribution_kind} · {a.attribution_status}</p>)}</div><div><h4>근거 및 출처</h4>{active.evidence?.length ? active.evidence.map(e => <div key={e.id}><p><b>{e.source?.title ?? "출처 정보 없음"}</b></p><p>{e.explanation} · {e.review_status}</p><p>{e.locator?.locator_value} · {e.locator?.verification_status}</p><p>저장 정책: {e.source?.storage_policy ?? "미상"} / 권리: {e.source?.license_status ?? "미상"}</p></div>) : <p>등록된 근거가 없습니다.</p>}</div></div></section>}
          <section className="graph"><div className="section-label"><span>RELATIONSHIP MAP</span><span>05</span></div><div className="graph-heading"><div><h3>관계 그래프</h3><p>주장 사이의 가상 관계와 검토 상태를 확인하세요.</p></div><span className="graph-symbol">↗</span></div>{visibleEdges.length ? visibleEdges.map(e => <div className="graph-edge" key={e.id}><div>{short(e.from_version_id)}</div><div className="edge-label"><span>↓</span>{e.relation_type} · {e.review_status}</div><div>{short(e.to_version_id)}</div>{e.rationale && <p>{e.rationale}</p>}</div>) : <p className="graph-empty">현재 선택에서 표시할 관계가 없습니다.</p>}</section>
        </div>
      </section>
      <footer><div><strong>SCRIPTURA</strong><p>합성 데모 / 실제 학술 데이터 아님</p></div><div className="footer-right">AI 답변 <span>후속 단계 · 비활성</span><p>출처에 기반한 탐색을 위한 프로토타입</p></div></footer>
    </div>
  </main>;
}
