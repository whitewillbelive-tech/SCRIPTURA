'use strict';

// Do not persist credentials, research data or source paths in browser storage.
(() => {
  const form = document.getElementById('filters');
  const secretInput = document.getElementById('session-secret');
  const connection = document.getElementById('connection');
  const error = document.getElementById('error');
  const results = document.getElementById('results');
  const detail = document.getElementById('detail');
  const empty = document.getElementById('empty');
  const count = document.getElementById('result-count');
  const prev = document.getElementById('prev-page');
  const next = document.getElementById('next-page');
  const pageStatus = document.getElementById('page-status');
  const mappingSummary = document.getElementById('mapping-summary');
  let secret = '';
  let controller = null;
  let generation = 0;
  let rows = [];
  let offset = 0;
  let pageSize = 100;
  let detailGeneration = 0;
  let detailController = null;

  const value = (v, fallback = '표시 보류 또는 미확인') => {
    if (typeof v === 'string' && v.trim()) return v;
    if (typeof v === 'number' && Number.isFinite(v)) return String(v);
    return fallback;
  };
  // Only generated layer/table/row coordinates are displayed; never raw source IDs.
  const safeRef = key => typeof key === 'string' && /^(base|d[5-8]):(claims|sources):[1-9][0-9]{0,6}$/.test(key) ? key : '미확인';
  const safeCoordinate = (key, table) => typeof key === 'string' && new RegExp(`^(base|d[5-8]):${table}:[1-9][0-9]{0,6}$`).test(key) ? key : '미확인';
  const node = (tag, text, className) => {
    const el = document.createElement(tag);
    if (text !== undefined) el.textContent = text;
    if (className) el.className = className;
    return el;
  };
  const clear = () => {
    generation += 1;
    detailGeneration += 1;
    if (detailController) detailController.abort();
    detailController = null;
    if (controller) controller.abort();
    controller = null;
    rows = [];
    results.replaceChildren();
    detail.replaceChildren(node('p', '왼쪽에서 연구 후보를 선택하세요.', 'empty'));
    empty.hidden = true;
    error.hidden = true;
    error.textContent = '';
    count.textContent = '—';
    prev.disabled = true; next.disabled = true; pageStatus.textContent = '';
    mappingSummary.replaceChildren(node('p', '미확인', 'empty'));
  };
  const showError = message => {
    rows = [];
    results.replaceChildren();
    detail.replaceChildren(node('p', '후보를 불러오지 못했습니다.', 'empty'));
    empty.hidden = true;
    count.textContent = '—';
    error.textContent = message;
    error.hidden = false;
  };
  const fact = (dl, label, val) => {
    const wrapper = node('div', undefined, 'fact');
    wrapper.append(node('dt', label), node('dd', value(val)));
    dl.append(wrapper);
  };
  const labels = {
    community_self_explanation:'공동체 자기 설명', individual_opinion:'개인 의견',
    academic_interpretation:'학술 해석', external_critique:'외부 비평',
    official_doctrine:'공식 교리라고 기록된 주장 · 별도 검증 필요', unconfirmed_authority:'원본 공식 교리 귀속 · 미확인',
    metadata_candidate:'연구 후보', candidate_visible_local:'로컬 후보 표시',
    redacted_rights_unresolved:'표시 범위 미확인', not_done:'독립 심사 미실시',
  };
  const readable = v => typeof v === 'string' && labels[v] ? labels[v] : value(v);
  const showDetail = selected => {
    detailGeneration += 1;
    if (detailController) detailController.abort();
    detailController = null;
    const ref = safeRef(selected.key);
    results.querySelectorAll('button').forEach(el => el.setAttribute('aria-pressed', String(ref !== '미확인' && el.dataset.key === ref)));
    const body = node('div');
    body.append(node('p', '연구 후보 · 공식성 및 학술 검증 별도', 'tag'));
    body.append(node('h3', value(selected.source_title, '서지 제목 표시 보류')));
    const fields = node('dl', undefined, 'facts');
    fact(fields, '임시 참조 번호', safeRef(selected.key));
    fact(fields, '자료 단계 · 유형', [selected.stage,selected.record_kind].filter(v => typeof v === 'string' && v).join(' · '));
    fact(fields, '필드 표시 검토 상태', readable(selected.display_status));
    fact(fields, '귀속', readable(selected.attribution));
    fact(fields, '전통 · 공동체', selected.tradition);
    const role = selected.community_role === 'self' ? '자기 설명' : selected.community_role === 'target' ? '평가 대상' : '역할 미확인';
    fact(fields, '공동체 참조의 역할', [role, selected.community_reference].filter(v => typeof v === 'string' && v).join(' · '));
    fact(fields, '외부 평가 대상', selected.evaluated_subject);
    fact(fields, '연구자 / 출처 저자', selected.researcher);
    fact(fields, '발화 주체 · 유형 미확인', selected.speaker);
    fact(fields, '발화 주체 유형 · 미확정', selected.speaker_type);
    body.append(node('p', '발화 주체 표기는 형식만 검사된 연구 후보입니다. 개인·기관 여부와 공식 대표성, 개인정보 및 표시권은 확인되지 않았습니다.', 'field-notice'));
    fact(fields, '문헌 · 저자', [selected.source_title,selected.source_creator].filter(v => typeof v === 'string' && v).join(' · '));
    fact(fields, '판본 임시 참조 번호', safeCoordinate(selected.edition_key, 'editions'));
    fact(fields, '위치 임시 참조 번호', safeCoordinate(selected.locator_key, 'locators'));
    fact(fields, '문헌 종류 · 발행 연도 · DOI', [selected.source_kind,selected.source_year,selected.source_doi].filter(v => (typeof v === 'string' && v) || typeof v === 'number').join(' · '));
    const passages = Array.isArray(selected.passages) ? selected.passages : [];
    if (passages.length) {
      for (const p of passages) if (p && typeof p === 'object') fact(fields, '본문 코퍼스 · 장절 체계 · 주소', [p.corpus,p.scheme,p.reference].filter(v => typeof v === 'string' && v).join(' · '));
    } else fact(fields, '본문 코퍼스 · 장절 체계 · 주소', [selected.passage_corpus,selected.passage_scheme,selected.passage_reference].filter(v => typeof v === 'string' && v).join(' · '));
    fact(fields, '정확 위치', value(selected.locator, '권리·형식 검토 전 표시 보류'));
    fact(fields, '확인 경로', selected.access_path);
    fact(fields, '출처 확인 상태', selected.verification_status);
    fact(fields, '인용 확인 상태', selected.quotation_status);
    fact(fields, '공식성 상태', selected.authority_status);
    fact(fields, '입력에 기록된 공식성 상태 · 미확정', selected.input_authority_status);
    fact(fields, '논증 검토 상태', selected.argument_status);
    fact(fields, '입력에 기록된 독립 검토 상태', selected.reported_independent_review_status);
    fact(fields, '기준일 적용 범위', selected.date_filter_status);
    fact(fields, '독립 인간 학술 심사', readable(selected.independent_review_status));
    fact(fields, '권리 상태', selected.rights_status);
    body.append(fields);
    if (selected.record_kind === 'claim') {
      if (safeCoordinate(selected.source_key, 'sources') !== '미확인') {
        const source = node('button', '연결된 문헌 후보 열기', 'target-button');
        source.type = 'button'; source.addEventListener('click', () => openTarget(selected.source_key)); body.append(source);
      } else body.append(node('p', '연결된 문헌 후보 미확인', 'muted'));
    }
    body.append(node('h4', '판본별 권리 기록'));
    const actions = {browse:'열람',collect_metadata:'메타데이터 수집',store_raw:'원문 저장',store_excerpt:'발췌 저장',index_fulltext:'전문 색인',embed:'임베딩',send_to_model:'모델 전송',redistribute:'재배포',public_link:'공개 링크'};
    const editions = Array.isArray(selected.edition_rights) ? selected.edition_rights.filter(item => item && typeof item === 'object') : [];
    // Each edition remains separate. A source-level aggregate can be unmapped
    // and must never replace the per-edition decisions or imply permission.
    const groups = editions.length ? editions : [{rights:selected.rights, rights_overrides:selected.rights_overrides}];
    groups.forEach((group, index) => {
      const container = node('section');
      container.setAttribute('aria-label', editions.length ? `판본 ${index + 1} 권리` : '연결된 판본 권리');
      container.append(node('h5', editions.length ? `판본 ${index + 1} · 원본 권리 기록` : '연결된 판본 · 원본 권리 기록'));
      const rights = group.rights && typeof group.rights === 'object' && !Array.isArray(group.rights) ? group.rights : {};
      const rightsList = node('dl', undefined, 'facts');
      for (const [key,label] of Object.entries(actions)) fact(rightsList, label, rights[key]);
      container.append(rightsList);
      const overrides = Array.isArray(group.rights_overrides) ? group.rights_overrides : [];
      if (overrides.length) {
        container.append(node('p', '권리 추가 관찰 · 적용 대기'));
        const list = node('ul');
        for (const item of overrides) if (item && typeof item === 'object') list.append(node('li', `${value(actions[item.action], '행위 미확인')} · ${value(item.previous_decision, '이전 결정 미확인')} → ${value(item.new_decision, '새 관찰 미확인')} · 근거 ${value(item.evidence, '미확인')}`));
        container.append(list);
      }
      body.append(container);
    });
    body.append(node('p', '권리 원본 기록과 별개로 이 화면에서 원문 저장·재배포 등 모든 이용은 허가하지 않습니다.', 'field-notice'));
    const events = Array.isArray(selected.access_events) ? selected.access_events : [];
    if (events.length) {
      body.append(node('h4', '출처 접근 기록'));
      const list = node('ul');
      for (const event of events) if (event && typeof event === 'object') list.append(node('li', `${value(event.method, '방식 미확인')} · ${value(event.result, '결과 미확인')} · ${value(event.checked_at, '시점 미확인')}`));
      body.append(list);
    }
    const observations = Array.isArray(selected.attestation_observations) ? selected.attestation_observations : [];
    if (observations.length) {
      body.append(node('h4', '입력에 기록된 입장 관찰 · 별도 검토 필요'));
      const list = node('ul');
      for (const item of observations) if (item && typeof item === 'object') list.append(node('li', `${value(item.scope, '범위 미확인')} · ${value(item.verification_status, '상태 미확인')} · ${value(item.as_of, '시점 미확인')}`));
      body.append(list);
    }
    body.append(node('h4', '근거와 관계'));
    const evidence = Array.isArray(selected.evidence) ? selected.evidence : [];
    const relations = Array.isArray(selected.relationships) ? selected.relationships : [];
    const items = [];
    for (const item of evidence) if (item && typeof item === 'object') items.push(`근거 · ${value(item.kind, '유형 미확인')} · ${value(item.status, '상태 미확인')}`);
    if (items.length || relations.length) {
      const list = node('ul');
      for (const item of items) list.append(node('li', item));
      for (const item of relations) if (item && typeof item === 'object') {
        const direction = item.direction === 'outgoing' ? '이 후보 → 연결 대상' : item.direction === 'incoming' ? '연결 대상 → 이 후보' : '방향 미확인';
        const li = node('li', `관계 · ${direction} · ${value(item.kind, '유형 미확인')} · ${value(item.status, '상태 미확인')} · ${value(item.assessment, '근거 검토 대기')} `);
        if (safeRef(item.target_key) !== '미확인') {
          const target = node('button', '연결 대상 열기', 'target-button');
          target.type = 'button'; target.addEventListener('click', () => openTarget(item.target_key)); li.append(target);
        } else li.append(node('span', '대상 미확인'));
        list.append(li);
      }
      body.append(list);
    } else body.append(node('p', '표시 가능한 근거 또는 관계가 없습니다.', 'muted'));
    const unmapped = Array.isArray(selected.unmapped) ? selected.unmapped : [];
    body.append(node('p', `표시·대응 보류: ${unmapped.length}개 필드. 원문, 직접 인용, 자유 요약과 외부 링크는 표시하지 않습니다.`, 'field-notice'));
    const names = [...new Set(unmapped.filter(name => typeof name === 'string' && /^[A-Za-z0-9_]{1,80}$/.test(name)))];
    if (names.length) {
      const un = node('details'); un.append(node('summary', '대응되지 않은 필드 이름 보기'));
      const list = node('ul'); for (const name of names) list.append(node('li', name)); un.append(list); body.append(un);
    }
    detail.replaceChildren(body);
  };
  const openTarget = async key => {
    const local = rows.find(row => row && row.key === key);
    if (local) { showDetail(local); return; }
    detailGeneration += 1;
    if (detailController) detailController.abort();
    const current = detailGeneration;
    detailController = new AbortController();
    detail.replaceChildren(node('p', '연결 대상을 불러오는 중입니다.', 'empty'));
    try {
      const query = new URLSearchParams({key});
      const response = await fetch(`/api/candidates?${query}`, {cache:'no-store', headers:{Authorization:`Bearer ${secret}`}, signal:detailController.signal});
      if (current !== detailGeneration) return;
      if (!response.ok) throw new Error('unavailable');
      const data = await response.json();
      if (current !== detailGeneration) return;
      const target = Array.isArray(data.records) ? data.records.find(row => row && row.key === key) : null;
      if (!target) { detail.replaceChildren(node('p', '연결 대상의 표시 가능한 후보가 없습니다.', 'empty')); return; }
      showDetail(target);
    } catch (e) {
      if (current !== detailGeneration || e.name === 'AbortError') return;
      detail.replaceChildren(node('p', '연결 대상을 불러오지 못했습니다.', 'error'));
    }
  };
  const renderMapping = summary => {
    const entries = [];
    if (summary && typeof summary === 'object' && !Array.isArray(summary)) {
      for (const [stage,tables] of Object.entries(summary)) {
        if (!/^[a-z0-9_]{1,64}$/i.test(stage) || !tables || typeof tables !== 'object' || Array.isArray(tables)) continue;
        for (const [table,info] of Object.entries(tables)) {
          if (!/^[a-z0-9_]{1,64}$/i.test(table) || !info || typeof info !== 'object' || !Number.isSafeInteger(info.input_count) || info.input_count < 0) continue;
          const state = info.mapping === 'partial' ? '일부만 대응' : info.mapping === 'unmapped' ? '미대응' : '대응 상태 미확인';
          entries.push(`${stage} · ${table}: 입력 ${info.input_count}건 · ${state}`);
        }
      }
    }
    if (!entries.length) { mappingSummary.replaceChildren(node('p', '미확인', 'empty')); return; }
    const list = node('ul'); for (const entry of entries) list.append(node('li', entry));
    mappingSummary.replaceChildren(list);
  };
  const render = data => {
    rows = Array.isArray(data.records) ? data.records : [];
    renderMapping(data.unmapped_summary);
    const total = Number.isSafeInteger(data.total) && data.total >= 0 ? data.total : rows.length;
    count.textContent = `${total}개 후보`;
    pageSize = Number.isSafeInteger(data.page_size) && data.page_size > 0 ? data.page_size : 100;
    prev.disabled = offset <= 0; next.disabled = offset + rows.length >= total || rows.length === 0;
    pageStatus.textContent = total ? `${offset + 1}–${offset + rows.length} / ${total}` : '';
    connection.textContent = data.dataset === 'synthetic' ? '합성 시험 자료 / 실제 연구 데이터 아님.' : '선택한 로컬 자료에서 조회했습니다. 모든 결과는 연구 후보입니다.';
    empty.hidden = rows.length > 0;
    for (const row of rows) {
      if (!row || typeof row !== 'object') continue;
      const button = node('button', undefined, 'candidate');
      button.type = 'button'; if (safeRef(row.key) !== '미확인') button.dataset.key = safeRef(row.key); button.setAttribute('aria-pressed', 'false');
      button.append(node('span', readable(row.attribution), 'tag'));
      button.append(node('strong', value(row.source_title, '서지 제목 표시 보류')));
      button.append(node('small', `임시 참조 번호 · ${safeRef(row.key)}`));
      button.append(node('small', [value(row.stage, '단계 미확인'), value(row.verification_status, '확인 대기')].join(' · ')));
      button.addEventListener('click', () => showDetail(row));
      results.append(button);
    }

  };
  const search = async () => {
    clear();
    if (!secret) { connection.textContent = '세션 비밀을 입력해 주세요.'; return; }
    const current = generation;
    controller = new AbortController();
    const query = new URLSearchParams();
    for (const [key, item] of new FormData(form)) if (typeof item === 'string' && item.trim()) query.set(key, item.trim());
    if (offset) query.set('offset', String(offset));
    connection.textContent = '연구 후보를 불러오는 중입니다.';
    try {
      const response = await fetch(`/api/candidates${query.size ? `?${query}` : ''}`, {cache:'no-store', headers:{Authorization:`Bearer ${secret}`}, signal:controller.signal});
      if (current !== generation) return;
      if (response.status === 401 || response.status === 403) { secret = ''; connection.textContent = '세션을 열지 못했습니다.'; showError('세션 비밀을 확인하고, 연속으로 실패한 경우 10초 뒤 다시 시도해 주세요.'); return; }
      if (!response.ok) throw new Error('unavailable');
      const data = await response.json();
      if (current !== generation) return;
      if (!data || !Array.isArray(data.records) || !['D8','synthetic'].includes(data.dataset)) throw new Error('unexpected');
      render(data);
    } catch (e) {
      if (current !== generation || e.name === 'AbortError') return;
      connection.textContent = '자료를 불러오지 못했습니다.';
      showError('자료를 불러오지 못했습니다. 로컬 서버 상태와 선택한 자료를 확인해 주세요.');
    }
  };
  document.getElementById('session-form').addEventListener('submit', event => {
    event.preventDefault();
    offset = 0;
    secret = secretInput.value;
    secretInput.value = '';
    search();
  });
  document.getElementById('session-close').addEventListener('click', () => {
    secret = ''; secretInput.value = ''; clear(); connection.textContent = '세션이 닫혔습니다.';
  });
  form.addEventListener('input', () => { offset = 0; clear(); connection.textContent = secret ? '조건이 변경됐습니다. 후보 검색을 눌러 주세요.' : '세션 비밀을 입력해 주세요.'; });
  form.addEventListener('change', () => { offset = 0; clear(); connection.textContent = secret ? '조건이 변경됐습니다. 후보 검색을 눌러 주세요.' : '세션 비밀을 입력해 주세요.'; });
  form.addEventListener('submit', event => { event.preventDefault(); offset = 0; search(); });
  form.addEventListener('reset', () => { offset = 0; clear(); setTimeout(search, 0); });
  prev.addEventListener('click', () => { offset = Math.max(0, offset - pageSize); search(); });
  next.addEventListener('click', () => { offset += pageSize; search(); });
})();
