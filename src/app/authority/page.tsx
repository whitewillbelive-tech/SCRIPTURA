'use client';

import { useEffect, useRef, useState } from 'react';
import styles from './authority.module.css';

type Position = {
  id: string;
  kind: string;
  label?: string;
  summary?: string;
  tradition_id?: string;
  issuer?: string | null;
  jurisdiction?: string | null;
  as_of?: string | null;
  published_at?: string | null;
  revised_on?: string | null;
  effective_from?: string | null;
  effective_until?: string | null;
  edition?: string | null;
  language?: string | null;
  quotation_status?: string | null;
  authority_status?: string | null;
  argument_status?: string | null;
  independent_review_status?: string | null;
  representativity?: string | null;
  verification_path?: string | null;
  exact_locator?: string | null;
  uncertainty?: string | null;
  assessment?: string | null;
};
type ApiResponse = { dataset_kind: string; warning: string; positions: Position[] };

type Group = { key: string; title: string; explanation: string; includes: (p: Position) => boolean };
const groups: Group[] = [
  { key: 'official', title: '집단 자신의 공식 채택 입장', explanation: '해당 집단의 채택 문헌과 적용 범위를 확인한 예시입니다.', includes: p => p.kind === 'normative_adopted' && p.authority_status === 'adoption_documented' && p.assessment === 'documented' },
  { key: 'institution', title: '공동체 교육과 기관 간행물', explanation: '기관 발행과 공식 교리 채택은 별개의 확인입니다.', includes: p => p.kind === 'official_institutional_guidance' && p.authority_status === 'issuer_documented' && p.assessment === 'documented' },
  { key: 'individual', title: '전통 안의 개인 설명', explanation: '개인의 소속이 공동체 전체의 채택을 뜻하지 않습니다.', includes: p => p.kind === 'individual_insider_view' },
  { key: 'outside', title: '외부의 설명과 비판', explanation: '외부 평가를 해당 공동체의 자기 진술로 바꾸지 않습니다.', includes: p => p.kind === 'external_description_or_criticism' },
  { key: 'academic', title: '언어·역사 및 학술적 검토', explanation: '연구자의 분석과 독립적 검수 여부를 따로 살펴봅니다.', includes: p => p.kind === 'scholarly_individual_analysis' },
  { key: 'historical', title: '과거 기관 간행물', explanation: '과거 간행물을 현재의 입장으로 자동 적용하지 않습니다.', includes: p => p.kind === 'historical_organizational_publication' },
  { key: 'uncertain', title: '다원적이거나 근거가 부족한 입장', explanation: '범위나 공식 채택 근거가 부족하면 미확정으로 둡니다.', includes: p => p.kind === 'plural_or_unresolved' || (p.kind === 'official_institutional_guidance' && (p.authority_status !== 'issuer_documented' || p.assessment !== 'documented')) || (p.kind === 'normative_adopted' && (p.authority_status !== 'adoption_documented' || p.assessment !== 'documented')) || !['normative_adopted','official_institutional_guidance','individual_insider_view','external_description_or_criticism','scholarly_individual_analysis','historical_organizational_publication','plural_or_unresolved'].includes(p.kind) },
];
const fallback = (v?: string | null) => typeof v === 'string' && v.trim() ? v : '확인되지 않음';
const axisLabel: Record<string, string> = {
  direct_checked: '직접 대조', translation_checked: '번역 대조', secondary_report: '전언', search_only: '검색 결과만', unchecked: '미확인',
  adoption_documented: '채택 근거 확인', issuer_documented: '발행 주체 확인', historical_only: '과거에 한정', individual_only: '개인 의견', disputed: '이견 있음', unknown: '미확인',
  documented_argument: '논증 기록됨', externally_challenged: '외부 반론 있음', cross_checked: '교차 확인', contested: '논쟁 중', not_assessed: '평가하지 않음',
  human_review_documented: '독립 검수 기록됨', published_critique_documented: '출판된 비판 기록됨', none: '기록 없음', pending: '검토 대기',
  direct: '직접 확인', translation: '번역을 통한 간접 확인', secondary: '전언', search: '검색 결과',
};
const readable = (v?: string | null) => v && axisLabel[v] || fallback(v);
const traditionLabel: Record<string, string> = { 'synthetic:tradition-a': '가상 전통 A', 'synthetic:tradition-b': '가상 전통 B', 'synthetic:plural': '가상 다원 전통' };
const kindOptions = [
  ['normative_adopted', '공식 채택 근거'], ['official_institutional_guidance', '기관 교육·설명'], ['historical_organizational_publication', '과거 간행물'],
  ['individual_insider_view', '개인 의견'], ['external_description_or_criticism', '외부 설명·비판'], ['scholarly_individual_analysis', '학술 분석'], ['plural_or_unresolved', '다원·미확정'],
];

export default function AuthorityPage() {
  const [positions, setPositions] = useState<Position[]>([]);
  const [tradition, setTradition] = useState('');
  const [traditions, setTraditions] = useState<string[]>([]);
  const [kind, setKind] = useState('');
  const [asOf, setAsOf] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const requestGeneration = useRef(0);
  const activeRequest = useRef<AbortController | null>(null);

  // Invalidate the old request immediately, before React runs effect cleanup.
  // Clear actual state, so stale results are not merely hidden by an alert.
  const clearForNewRequest = () => {
    requestGeneration.current += 1;
    activeRequest.current?.abort();
    setPositions([]);
    setError('');
    setLoading(true);
    setRefresh(n => n + 1);
  };

  useEffect(() => {
    const controller = new AbortController();
    const generation = ++requestGeneration.current;
    activeRequest.current = controller;
    const isCurrent = () => !controller.signal.aborted && requestGeneration.current === generation;
    const params = new URLSearchParams({ dataset: 'synthetic' });
    if (tradition.trim()) params.set('tradition_id', tradition.trim());
    if (asOf) params.set('as_of', asOf);
    if (kind) params.set('kind', kind);
    setLoading(true);
    setError('');
    setPositions([]);
    fetch(`/api/v1/authority?${params}`, { cache: 'no-store', signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error('unavailable');
        const data: ApiResponse = await response.json();
        if (data.dataset_kind !== 'synthetic' || !Array.isArray(data.positions)) throw new Error('unexpected data');
        if (isCurrent()) {
          setPositions(data.positions);
          if (!tradition && !asOf && !kind) setTraditions([...new Set(data.positions.map(p => p.tradition_id).filter((v): v is string => Boolean(v)))]);
        }
      })
      .catch(() => {
        if (isCurrent()) {
          setPositions([]);
          setError('권위 비교 예시를 불러오지 못했습니다. 서버 상태를 확인해 주세요.');
        }
      })
      .finally(() => { if (isCurrent()) setLoading(false); });
    return () => {
      controller.abort();
      if (activeRequest.current === controller) activeRequest.current = null;
    };
  }, [tradition, asOf, kind, refresh]);

  return <main className={styles.main}>
    <div className={styles.banner}>합성 데모 / 실제 학술 데이터 아님 · 모든 인물, 기관, 문헌과 입장은 가상입니다</div>
    <header className={styles.header}><a href="/" className={styles.brand}>SCRIPTURA <small>AUTHORITY &amp; EVIDENCE</small></a><nav aria-label="탐색"><a href="/">합성 본문 탐색</a><a href="/explore">연구 자료 탐색</a></nav></header>
    <div className={styles.shell}>
      <section className={styles.intro}><p className={styles.eyebrow}>I-2 · SYNTHETIC COMPARISON</p><h1>누가, 어떤 범위에서<br/><em>무엇을 말했을까요?</em></h1><p>발언의 출처, 공동체의 채택, 학술적 검토는 각각 다른 질문입니다.<br/>가상의 자료를 통해 근거와 불확실성을 함께 살펴보세요.</p></section>
      <section className={styles.filters} aria-label="비교 설정">
        <div><span className={styles.step}>01 / 범위</span><h2>비교 기준</h2><p>기준일을 비우면 오늘(UTC)과 명시된 유효기간을 대조합니다. 기간 근거가 없는 과거 간행물은 현재 입장으로 추정하지 않습니다.</p></div>
        <div className={styles.filterControls}><label>가상 전통 <select value={tradition} onChange={e => { clearForNewRequest(); setTradition(e.target.value); }}><option value="">전체 전통</option>{traditions.map(value => <option key={value} value={value}>{traditionLabel[value] ?? value}</option>)}</select></label><label>비교 범주 <select value={kind} onChange={e => { clearForNewRequest(); setKind(e.target.value); }}><option value="">전체 범주</option>{kindOptions.map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>기준일 <input type="date" value={asOf} onChange={e => { clearForNewRequest(); setAsOf(e.target.value); }} /></label><button type="button" onClick={() => {clearForNewRequest(); setTradition(''); setAsOf(''); setKind('');}}>초기화</button></div>
      </section>
      <section aria-label="해석 비교" aria-live="polite" className={styles.results}>
        <div className={styles.resultsHeading}><div><p className={styles.eyebrow}>02 / COMPARISON</p><h2>서로 다른 권위의 자리</h2></div><span>{loading ? '불러오는 중' : `${positions.length}개 예시`}</span></div>
        <p className={styles.disclaimer}>공식 채택은 발행 사실이나 개인의 소속과 다릅니다. 특정 종교나 전통에 하나의 중앙 권위를 가정하지 않습니다.</p>
        {error && <p role="alert" className={styles.error}>{error}</p>}
        {!loading && !error && positions.length === 0 && <p className={styles.empty}>선택한 조건에 맞는 합성 예시가 없습니다.</p>}
        {!error && groups.map(group => {
          const items = positions.filter(group.includes);
          return <section key={group.key} className={styles.group} aria-labelledby={`group-${group.key}`}>
            <div className={styles.groupHead}><div><h3 id={`group-${group.key}`}>{group.title}</h3><p>{group.explanation}</p></div><span>{items.length}</span></div>
            {items.length === 0 ? <p className={styles.groupEmpty}>{loading ? '확인 중' : '해당 예시가 없습니다.'}</p> : <div className={styles.cards}>{items.map(p => <article key={p.id} className={styles.card}>
              <div className={styles.cardHead}><span className={styles.category}>{group.title}</span><span className={p.assessment === 'documented' ? styles.status : styles.pending}>{p.assessment === 'documented' ? '근거 기록됨' : '근거 부족 · 미확정'}</span></div>
              <h4>{fallback(p.label)}</h4><p className={styles.summary}>{fallback(p.summary)}</p>
              <dl className={styles.facts}>
                <div><dt>대상 전통</dt><dd>{traditionLabel[p.tradition_id ?? ''] ?? fallback(p.tradition_id)}</dd></div>
                <div><dt>집단 대표성의 근거</dt><dd>{fallback(p.representativity)}</dd></div>
                <div><dt>발행 주체 · 관할</dt><dd>{fallback(p.issuer)} · {fallback(p.jurisdiction)}</dd></div>
                <div><dt>시점 및 적용 기간</dt><dd>기준일 {fallback(p.as_of)} · 발행 {fallback(p.published_at)} · 개정 {fallback(p.revised_on)} · 적용 {fallback(p.effective_from)} ~ {fallback(p.effective_until)}</dd></div>
                <div><dt>판본 · 언어</dt><dd>{fallback(p.edition)} · {fallback(p.language)}</dd></div>
                <div><dt>직접·간접 확인 및 위치</dt><dd>{readable(p.verification_path)} · {fallback(p.exact_locator)}</dd></div>
                <div><dt>불확실성</dt><dd>{fallback(p.uncertainty)}</dd></div>
              </dl>
              <p className={styles.rights}>원문 저장·임베딩·재배포 등 이용 권리는 별도로 확인해야 합니다.</p>
              <div className={styles.axes} aria-label="독립된 네 검증 상태"><span>인용 <b>{readable(p.quotation_status)}</b></span><span>공식 지위 <b>{readable(p.authority_status)}</b></span><span>논증 <b>{readable(p.argument_status)}</b></span><span>독립 심사 <b>{readable(p.independent_review_status)}</b></span></div>
            </article>)}</div>}
          </section>;
        })}
      </section>
      <footer className={styles.footer}><p>합성 데모 / 실제 학술 데이터 아님</p><p>AI 신학 판정 <strong>후속 단계 · 비활성</strong></p></footer>
    </div>
  </main>;
}
