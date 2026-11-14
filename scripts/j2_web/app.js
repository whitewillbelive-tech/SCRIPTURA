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
  const pageSort = document.getElementById('page-sort');
  const mappingSummary = document.getElementById('mapping-summary');
  const visibilityStatus = document.getElementById('visibility-status');
  const metadataCoverage = document.getElementById('metadata-coverage');
  const creatorFilterLabel = document.getElementById('creator-filter-label');
  const candidateLimits = document.getElementById('candidate-limits');
  const candidateLimitsContent = document.getElementById('candidate-limits-content');
  let secret = '';
  let controller = null;
  let generation = 0;
  let rows = [];
  let offset = 0;
  let pageSize = 100;
  let detailGeneration = 0;
  let detailController = null;
  let comparisonController = null;
  let comparisonGeneration = 0;
  let comparisonPassages = [];
  // The selected archive is fixed for one authenticated session. A response
  // that changes dataset must never replace results from the selected archive.
  let sessionDataset = null;
  // Set only from the authenticated server response, not an input record's
  // eligibility flag. The server must enforce field-level permissions before
  // producing this projection and before using any values in search.
  let verifiedMetadataProjection = false;
  let metadataNameCoverage = null;
  const METADATA_PROJECTION = 'k1.1-verified';
  const CANDIDATE_PROJECTION = 'k1.3-local-candidate';
  const isMetadataProjection = marker => marker === METADATA_PROJECTION || marker === CANDIDATE_PROJECTION;
  const CANDIDATE_FIELDS = ['source_title','source_creator','source_publisher','source_year','community_name'];
  const CANDIDATE_MAX_LENGTH = {source_title:1024, source_creator:512, source_publisher:512, source_year:4, community_name:512};
  const CANDIDATE_STATES = new Set(['recorded_unverified','source_confirmed','restricted','missing_or_unmapped']);
  const CANDIDATE_STATE_LABELS = {
    recorded_unverified:'원본 기록 · 독립 확인 전',
    source_confirmed:'출처 대조 완료',
    restricted:'표시 제한',
    missing_or_unmapped:'누락 또는 연결 미확인',
  };
  const CANDIDATE_REASON_LABELS = {
    no_record:'원본 기록 없음', ambiguous_source:'출처 연결 불명확', ambiguous_edition:'판본 연결 불명확',
    explicit_restriction:'명시적 이용 제한', conditional_use:'조건부 이용',
    sensitive_or_personal:'민감정보 또는 개인정보', unsafe_format:'안전하지 않은 형식',
    unmapped_relationship:'귀속 관계 미확인', community_unlinked:'공동체 레코드 미연결',
    community_role_unconfirmed:'공동체의 발화·대상 역할 미확인',
  };

  const value = (v, fallback = '표시 보류 또는 미확인') => {
    if (typeof v === 'string' && v.trim()) return v;
    if (typeof v === 'number' && Number.isFinite(v)) return String(v);
    return fallback;
  };
  // Only generated layer/table/row coordinates are displayed; never raw source IDs.
  const safeRef = key => typeof key === 'string' && /^(base|d[5-9]|d1[012]):(claims|sources):[1-9][0-9]{0,6}$/.test(key) ? key : '미확인';
  const safeCoordinate = (key, table) => typeof key === 'string' && new RegExp(`^(base|d[5-9]|d1[012]):${table}:[1-9][0-9]{0,6}$`).test(key) ? key : '미확인';
  // Research fields remain closed until their individual use is checked by
  // the server. This extra UI boundary is not a replacement for that gate.
  // Synthetic tests remain labeled and never represent real approval.
  const safeRow = (row, dataset, projection, summaryProjection) => {
    if (!row || typeof row !== 'object') return null;
    if (dataset === 'synthetic') {
      const synthetic = {...row, summary: null};
      if (summaryProjection === 'k2-reviewed-summary' && row.summary_status === 'recorded_unverified' && typeof row.summary === 'string' && row.summary.trim() && row.summary.length <= 500 && !/[\x00-\x1f\x7f]/.test(row.summary)) synthetic.summary = row.summary;
      return synthetic;
    }
    const safe = {...row};
    for (const field of ['source_title','source_creator','source_publisher','source_doi','source_year','locator','researcher','speaker','tradition','community_reference','evaluated_subject','summary']) safe[field] = null;
    if (summaryProjection === 'k2-reviewed-summary' && row.summary_status === 'recorded_unverified' && typeof row.summary === 'string' && row.summary.trim() && row.summary.length <= 500 && !/[\x00-\x1f\x7f]/.test(row.summary)) safe.summary = row.summary;
    // Only the authenticated API's explicit K-1.3 safe projection can carry
    // a private candidate value; a raw archive field or policy flag cannot.
    safe.candidate_field_states = null;
    safe.candidate_field_reasons = null;
    if (projection === CANDIDATE_PROJECTION && row.candidate_metadata && typeof row.candidate_metadata === 'object' && !Array.isArray(row.candidate_metadata)) {
      // A community name is meaningful only when the server established its
      // relation to this specific candidate. Never infer the role from a raw
      // claim or reuse a label for an unlinked subject or critic.
      safe.community_role = 'unspecified';
      const states = {}, reasons = {};
      for (const key of CANDIDATE_FIELDS) {
        const item = row.candidate_metadata[key];
        const state = item && typeof item === 'object' && !Array.isArray(item) && CANDIDATE_STATES.has(item.status) ? item.status : 'missing_or_unmapped';
        states[key] = state;
        if (item && typeof item.reason === 'string' && Object.hasOwn(CANDIDATE_REASON_LABELS, item.reason)) reasons[key] = item.reason;
        const allowed = state === 'recorded_unverified' || state === 'source_confirmed';
        const fieldValue = item && item.value;
        if (!allowed) continue;
        if (typeof fieldValue !== 'string' || !fieldValue.trim() || fieldValue.length > CANDIDATE_MAX_LENGTH[key] || (key === 'source_year' && !/^\d{4}$/.test(fieldValue))) {
          states[key] = 'missing_or_unmapped';
          continue;
        }
        if (key === 'community_name') {
          if (item.relationship_role !== 'self' && item.relationship_role !== 'target') {
            states[key] = 'missing_or_unmapped';
            reasons[key] = 'community_role_unconfirmed';
            continue;
          }
          safe.community_role = item.relationship_role;
        }
        safe[key === 'community_name' ? 'tradition' : key] = fieldValue;
      }
      safe.candidate_field_states = states;
      safe.candidate_field_reasons = reasons;
    }
    const metadata = row.verified_metadata;
    if (projection === METADATA_PROJECTION && metadata && typeof metadata === 'object' && !Array.isArray(metadata)) {
      for (const key of ['source_title','source_creator','source_publisher']) {
        if (Object.hasOwn(metadata, key) && typeof metadata[key] === 'string' && metadata[key].trim()) safe[key] = metadata[key];
      }
      if (Object.hasOwn(metadata, 'source_year') && ((typeof metadata.source_year === 'string' && /^\d{4}$/.test(metadata.source_year)) || (Number.isInteger(metadata.source_year) && metadata.source_year >= 1 && metadata.source_year <= 9999))) safe.source_year = metadata.source_year;
      if (Object.hasOwn(metadata, 'community_name') && typeof metadata.community_name === 'string' && metadata.community_name.trim()) safe.tradition = metadata.community_name;
    }
    return safe;
  };
  const node = (tag, text, className) => {
    const el = document.createElement(tag);
    if (text !== undefined) el.textContent = text;
    if (className) el.className = className;
    return el;
  };
  const clear = () => {
    closeDrawer();
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
    visibilityStatus.textContent = '표시 적격성 정보: 미확인';
    metadataCoverage.textContent = '서지 검색 범위: 미확인';
    candidateLimits.hidden = true;
    candidateLimitsContent.replaceChildren();
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
    verified_fields_only:'일부 서지 필드 확인', unconfirmed:'미확인',
  };
  const readable = v => typeof v === 'string' && labels[v] ? labels[v] : value(v);
  const OBSERVATION_KINDS = new Set(['audit_review','review_queue','evidence','relationship','audit']);
  const OBSERVATION_STATES = new Set(['verified_exact','partially_verified','source_checked','metadata_checked','pending','unknown','unmapped','direct_published_source_rechecked','translation_checked_human_review_pending','rendered_content_checked_adoption_unknown','source_label_checked_legal_event_ambiguous','direct_rendered_browser_checked','review_scan_checked_book_unseen']);
  const OBSERVATION_METHODS = new Set(['unknown','unmapped','direct']);
  const RIGHTS_ACTIONS = new Set(['browse','collect_metadata','store_raw','store_excerpt','index_fulltext','embed','send_to_model','redistribute','public_link']);
  const RIGHTS_DECISIONS = new Set(['unknown','conditional','allowed','prohibited','not_recorded','conflicting','unmapped']);
  const RELATION_TYPES = {
    same_community_similar_interpretation: '같은 공동체의 유사 해석',
    published_review_criticizes_book_treatment: '출판된 서평의 문헌 처리 비평',
    bibliographic_record_describes: '서지 기록의 설명',
    unmapped: '관계 유형 미대응',
  };
  // Only known schema field names can be displayed in research mode. A raw
  // ID, name or free text must not become visible merely by looking like a key.
  const UNMAPPED_FIELDS = new Set(['source_title','source_creator','source_chain','title','creator','speaker','community_id','statement_ko','scope_note','note','url','doi','access_scope','document_type_scope','language','published_at','theological_primary_document','original_text_saved','claim_truth_status','independent_human_review','source_full_text','rights_scope','source_url','unreviewed_source_text','formal_adoption_evidence','position_scope','human_review','scholarly_reviewed','reference','reference_scheme','corpus','location','status','verification_status','authority_status','attribution_kind','passage_ids','source_locator_id','checked_at','unrecognized_field']);
  const safeEnum = (v, allowed) => typeof v === 'string' && allowed.has(v) ? v : '미확인';
  const drawer = document.getElementById('research-drawer');
  const drawerTitle = document.getElementById('drawer-title');
  const drawerContent = document.getElementById('drawer-content');
  const drawerClose = document.getElementById('drawer-close');
  let drawerOpener = null;
  let drawerGeneration = 0;
  const closeDrawer = () => {
    drawerGeneration += 1;
    if (drawer.open) drawer.close();
  };
  drawerClose.addEventListener('click', closeDrawer);
  drawer.addEventListener('close', () => {
    drawerGeneration += 1;
    drawerContent.replaceChildren();
    if (drawerOpener && drawerOpener.isConnected) drawerOpener.focus();
    drawerOpener = null;
  });
  const openDrawer = (title, content, opener) => {
    drawerTitle.textContent = title;
    drawerContent.replaceChildren(content);
    if (!drawer.open) {
      drawerOpener = opener || document.activeElement;
      drawer.showModal();
    }
    drawerClose.focus();
  };
  const evidencePanel = (selected, summary) => {
    const section = node('div');
    if (summary) section.append(node('h3', '핵심 해석 · 원본 기록'), node('p', summary));
    section.append(node('h3', '연결 문헌'), node('p', value(selected.source_title, '문헌명 표시 보류')));
    section.append(node('p', `문헌 작성자: ${value(selected.source_creator, '미확인')}`));
    section.append(node('h3', '확인된 근거'));
    // Evidence types and statuses are metadata, not the content of a proof.
    // Do not turn them into an argument or generate a theological rationale.
    section.append(node('p', '논거 확인 대기'));
    const evidence = Array.isArray(selected.evidence) ? selected.evidence : [];
    if (evidence.length) {
      const list = node('ul');
      for (const item of evidence) if (item && typeof item === 'object') list.append(node('li', `관련 근거 기록 · ${value(item.kind, '유형 미확인')} · ${value(item.status, '상태 미확인')}`));
      section.append(list);
    }
    return section;
  };
  const appendPrimary = (container, selected, summary) => {
    // There is no independently verified claim-to-speaker relation in this
    // API. A confirmed community name alone cannot establish the speaker.
    const role = null;
    const actor = node('section', undefined, 'interpretation-actor');
    actor.append(node('h4', '해석 주체'), node('p', value(role, '해석 주체 미확인')));
    if (!role) actor.append(node('p', `문헌 작성자 · ${value(selected.source_creator, '미확인')}`, 'muted'));
    const claim = node('section', undefined, 'interpretation-summary');
    claim.append(node('h4', '핵심 해석'), node('p', value(summary, '해석 요지 표시 보류')));
    const argument = node('section', undefined, 'interpretation-argument');
    argument.append(node('h4', '핵심 논거'), node('p', '논거 확인 대기'));
    const source = node('section', undefined, 'interpretation-source');
    source.append(node('h4', '출처'), node('p', value(selected.source_title, '문헌명 표시 보류')));
    container.append(actor, claim, argument, source);
  };
  const showDetail = (selected, destination = detail) => {
    detailGeneration += 1;
    if (detailController) detailController.abort();
    detailController = null;
    const ref = safeRef(selected.key);
    if (destination === detail) results.querySelectorAll('button').forEach(el => el.setAttribute('aria-pressed', String(ref !== '미확인' && el.dataset.key === ref)));
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
    fact(fields, '문헌 · 기록된 작성자', [selected.source_title,selected.source_creator].filter(v => typeof v === 'string' && v).join(' · '));
    fact(fields, '발행기관', selected.source_publisher);
    if (selected.candidate_field_states) {
      for (const [key,label] of Object.entries({source_title:'문헌 제목',source_creator:'기록된 문헌 작성자',source_publisher:'발행기관',source_year:'발행 연도',community_name:'공동체명'})) {
        fact(fields, `${label} 표시 상태`, CANDIDATE_STATE_LABELS[selected.candidate_field_states[key]] || CANDIDATE_STATE_LABELS.missing_or_unmapped);
        const reason = selected.candidate_field_reasons && selected.candidate_field_reasons[key];
        if (reason && Object.hasOwn(CANDIDATE_REASON_LABELS, reason)) fact(fields, `${label} 제한 사유`, CANDIDATE_REASON_LABELS[reason]);
      }
      fact(fields, '로컬 표시 범위', '비공개 로컬 연구 후보');
      fact(fields, '공개 · 재배포', '별도 승인 필요');
    }
    fact(fields, '판본 임시 참조 번호', safeCoordinate(selected.edition_key, 'editions'));
    fact(fields, '위치 임시 참조 번호', safeCoordinate(selected.locator_key, 'locators'));
    fact(fields, '문헌 종류 · 발행 연도 · DOI', [selected.source_kind,selected.source_year,selected.source_doi].filter(v => (typeof v === 'string' && v) || typeof v === 'number').join(' · '));
    const passages = Array.isArray(selected.passages) ? selected.passages : [];
    if (passages.length) {
      for (const p of passages) if (p && typeof p === 'object') fact(fields, '본문 코퍼스 · 장절 체계 · 주소', [p.corpus,p.scheme,p.reference].filter(v => typeof v === 'string' && v).join(' · '));
    } else fact(fields, '본문 코퍼스 · 장절 체계 · 주소', [selected.passage_corpus,selected.passage_scheme,selected.passage_reference].filter(v => typeof v === 'string' && v).join(' · '));
    fact(fields, '정확 위치', value(selected.locator, '권리·형식 검토 전 표시 보류'));
    fact(fields, '확인 경로', selected.access_path);
    fact(fields, '출처 확인 상태', readable(selected.source_verification_status));
    fact(fields, '입력 검증 상태', selected.verification_status);
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
        source.type = 'button'; source.addEventListener('click', () => drawer.open ? openSourceDrawer(selected.source_key, source) : openTarget(selected.source_key)); body.append(source);
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
    const later = Array.isArray(selected.d9_observations) ? selected.d9_observations : [];
    const laterRights = Array.isArray(selected.d9_rights_observations) ? selected.d9_rights_observations : [];
    if ((sessionDataset === 'D9' || sessionDataset === 'D10' || sessionDataset === 'D12') && (later.length || laterRights.length)) {
      body.append(node('h4', 'D-9 후속 관찰 · 원본 상태 변경 없음'));
      const list = node('ul');
      for (const item of later) if (item && typeof item === 'object') {
        const direction = item.direction === 'outgoing' ? '이 후보 → 연결 대상' : item.direction === 'incoming' ? '연결 대상 → 이 후보' : '방향 미확인';
        const relation = Object.hasOwn(RELATION_TYPES, item.relation_type) ? RELATION_TYPES[item.relation_type] : '관계 유형 미확인';
        const li = node('li', `관찰 · ${safeEnum(item.kind, OBSERVATION_KINDS)} · ${safeEnum(item.status, OBSERVATION_STATES)} · ${safeEnum(item.method, OBSERVATION_METHODS)} · ${direction} · ${relation} `);
        if (safeRef(item.target_key) !== '미확인') {
          const target = node('button', '후속 관찰 연결 대상 열기', 'target-button');
          target.type = 'button'; target.addEventListener('click', () => drawer.open ? openSourceDrawer(item.target_key, target) : openTarget(item.target_key)); li.append(target);
        }
        list.append(li);
      }
      for (const item of laterRights) if (item && typeof item === 'object') {
        list.append(node('li', `권리 추가 관찰 · 판본 ${safeCoordinate(item.edition_key, 'editions')} · ${safeEnum(item.action, RIGHTS_ACTIONS)} · ${safeEnum(item.decision, RIGHTS_DECISIONS)} · 적용 대기`));
      }
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
          target.type = 'button'; target.addEventListener('click', () => drawer.open ? openSourceDrawer(item.target_key, target) : openTarget(item.target_key)); li.append(target);
        } else li.append(node('span', '대상 미확인'));
        list.append(li);
      }
      body.append(list);
    } else body.append(node('p', '표시 가능한 근거 또는 관계가 없습니다.', 'muted'));
    const unmapped = Array.isArray(selected.unmapped) ? selected.unmapped : [];
    body.append(node('p', `표시·대응 보류: ${unmapped.length}개 필드. 원문, 직접 인용, 자유 요약과 외부 링크는 표시하지 않습니다.`, 'field-notice'));
    const names = [...new Set(unmapped.filter(name => typeof name === 'string' && (UNMAPPED_FIELDS.has(name) || (sessionDataset === 'synthetic' && /^[A-Za-z0-9_]{1,80}$/.test(name)))))];
    if (names.length) {
      const un = node('details'); un.append(node('summary', '대응되지 않은 필드 이름 보기'));
      const list = node('ul'); for (const name of names) list.append(node('li', name)); un.append(list); body.append(un);
    }
    const eligibility = selected.field_eligibility;
    if (eligibility && typeof eligibility === 'object' && !Array.isArray(eligibility)) {
      const groups = ['bibliography','own_summary','short_quote','full_text','private_link'];
      const entities = ['source','claim','edition','locator'];
      const states = new Set(['metadata_candidate','unknown','unmapped','redacted_rights_unresolved']);
      if (sessionDataset === 'synthetic') states.add('candidate_visible_local');
      const report = node('details'); report.append(node('summary', '필드별 표시 적격성 보기'));
      const list = node('ul');
      for (const entity of entities) {
        const item = eligibility[entity];
        if (!item || typeof item !== 'object' || Array.isArray(item)) continue;
        for (const group of groups) if (Object.hasOwn(item, group)) {
          const state = safeEnum(item[group], states);
          const scope = sessionDataset === 'synthetic' && state === 'candidate_visible_local' ? '합성 시험용 승인' : '표시 승인 아님';
          list.append(node('li', `${entity} · ${group}: ${state} · ${scope}`));
        }
      }
      report.append(list); body.append(report);
    }
    const primary = node('div', undefined, 'research-detail');
    primary.append(node('p', '연구 후보 · 원본 기록', 'tag'));
    appendPrimary(primary, selected, selected.summary);
    const actionsPanel = node('div', undefined, 'card-actions');
    const evidenceButton = node('button', '근거·출처 보기', 'target-button');
    evidenceButton.type = 'button';
    evidenceButton.addEventListener('click', () => openDrawer('근거·출처', evidencePanel(selected, selected.summary), evidenceButton));
    const verificationButton = node('button', '검증 정보 보기', 'target-button');
    verificationButton.type = 'button';
    verificationButton.addEventListener('click', () => openDrawer('검증 정보', body, verificationButton));
    actionsPanel.append(evidenceButton, verificationButton);
    if (selected.record_kind === 'claim' && safeCoordinate(selected.source_key, 'sources') !== '미확인') {
      const sourceButton = node('button', '연결된 문헌 후보 열기', 'target-button');
      sourceButton.type = 'button';
      sourceButton.addEventListener('click', () => openTarget(selected.source_key));
      actionsPanel.append(sourceButton);
    }
    if (selected.record_kind === 'source' && safeCoordinate(selected.key, 'sources') !== '미확인') {
      const relatedButton = node('button', '이 문헌의 관련 해석 보기', 'target-button');
      relatedButton.type = 'button';
      relatedButton.addEventListener('click', () => openRelatedClaims(selected.key, relatedButton));
      actionsPanel.append(relatedButton);
    }
    primary.append(actionsPanel);
    destination.replaceChildren(primary);
  };
  // Reverse navigation uses only an opaque coordinate and the server's safe
  // projection. It stays in the drawer so the original search position and
  // filters are not lost. Exact source identity is checked again on receipt.
  const openRelatedClaims = async (key, opener, offset = 0) => {
    if (safeCoordinate(key, 'sources') === '미확인') return;
    const current = ++drawerGeneration;
    const holder = node('div');
    holder.append(node('p', '관련 해석을 불러오는 중입니다.'));
    openDrawer('이 문헌의 관련 해석', holder, opener);
    try {
      const query = new URLSearchParams({source_key:key, record_kind:'claim', offset:String(offset)});
      const response = await fetch(`/api/candidates?${query}`, {cache:'no-store',headers:{Authorization:`Bearer ${secret}`}});
      if (!drawer.open || current !== drawerGeneration) return;
      if (!response.ok) throw new Error('unavailable');
      const data = await response.json();
      if (!drawer.open || current !== drawerGeneration) return;
      if (!data || data.dataset !== sessionDataset || !Array.isArray(data.records)) throw new Error('unavailable');
      const linked = data.records.map(row => safeRow(row, data.dataset, data.metadata_projection, data.summary_projection))
        .filter(row => row && row.record_kind === 'claim' && row.source_key === key);
      const total = Number.isSafeInteger(data.total) && data.total >= 0 ? data.total : linked.length;
      const pageSize = Number.isSafeInteger(data.page_size) && data.page_size > 0 ? data.page_size : 100;
      holder.replaceChildren(node('p', `관련 해석 ${total}건 · 출처 연결 기준`, 'subtle'));
      if (!linked.length) holder.append(node('p', '연결된 해석 또는 표시 가능한 본문이 없습니다.', 'empty'));
      const list = node('ul');
      for (const row of linked) {
        const item = node('li');
        const passage = Array.isArray(row.passages) ? row.passages.find(p => p && ['corpus','scheme','reference'].every(k => typeof p[k] === 'string' && p[k].trim())) : null;
        item.append(node('p', passage ? `${passage.corpus} · ${passage.scheme} · ${passage.reference}` : '본문 연결 미확인'));
        const inspect = node('button', '해석 상세 보기', 'target-button'); inspect.type = 'button';
        inspect.addEventListener('click', () => showDetail(row, holder)); item.append(inspect);
        if (passage) {
          const compare = node('button', '이 본문 비교하기', 'target-button'); compare.type = 'button';
          compare.addEventListener('click', () => openComparisonAt(passage)); item.append(compare);
        }
        list.append(item);
      }
      if (linked.length) holder.append(list);
      if (offset > 0 || offset + pageSize < total) {
        const nav = node('nav'); nav.setAttribute('aria-label', '관련 해석 페이지');
        const previous = node('button', '이전'); previous.type = 'button'; previous.disabled = offset <= 0;
        previous.addEventListener('click', () => openRelatedClaims(key, opener, Math.max(0, offset - pageSize)));
        const nextPage = node('button', '다음'); nextPage.type = 'button'; nextPage.disabled = offset + pageSize >= total;
        nextPage.addEventListener('click', () => openRelatedClaims(key, opener, offset + pageSize));
        nav.append(previous, nextPage); holder.append(nav);
      }
    } catch (_) {
      if (drawer.open && current === drawerGeneration) holder.replaceChildren(node('p', '관련 해석을 불러오지 못했습니다.', 'error'));
    }
  };
  // The comparison remains in place while its linked source is read.
  const openSourceDrawer = async (key, opener) => {
    const current = ++drawerGeneration;
    const holder = node('div');
    holder.append(node('p', '연결 문헌을 불러오는 중입니다.'));
    openDrawer('연결 문헌', holder, opener);
    try {
      const query = new URLSearchParams({key});
      const response = await fetch(`/api/candidates?${query}`, {cache:'no-store', headers:{Authorization:`Bearer ${secret}`}});
      if (!drawer.open || current !== drawerGeneration) return;
      if (!response.ok) throw new Error('unavailable');
      const data = await response.json();
      if (!drawer.open || current !== drawerGeneration) return;
      if (!data || data.dataset !== sessionDataset) throw new Error('unavailable');
      const target = Array.isArray(data.records) ? safeRow(data.records.find(row => row && row.key === key), data.dataset, data.metadata_projection, data.summary_projection) : null;
      if (!target) throw new Error('unavailable');
      showDetail(target, holder);
    } catch (_) {
      if (drawer.open && current === drawerGeneration) holder.replaceChildren(node('p', '연결 문헌을 불러오지 못했습니다.', 'error'));
    }
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
      if (!data || data.dataset !== sessionDataset) throw new Error('dataset mismatch');
      const target = Array.isArray(data.records) ? safeRow(data.records.find(row => row && row.key === key), data.dataset, data.metadata_projection, data.summary_projection) : null;
      if (!target) { detail.replaceChildren(node('p', '연결 대상의 표시 가능한 후보가 없습니다.', 'empty')); return; }
      showDetail(target);
    } catch (e) {
      if (current !== detailGeneration || e.name === 'AbortError') return;
      detail.replaceChildren(node('p', e.message === 'dataset mismatch' ? '선택한 자료 버전과 응답이 일치하지 않습니다.' : '연결 대상을 불러오지 못했습니다.', 'error'));
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
  const renderCards = () => {
    const selectedKey = results.querySelector('.candidate[aria-pressed="true"]')?.dataset.key;
    results.replaceChildren();
    const ordered = [...rows];
    const field = pageSort.value === 'title' ? 'source_title' : pageSort.value === 'creator' ? 'source_creator' : null;
    if (field) ordered.sort((a, b) => {
      const left = typeof a[field] === 'string' ? a[field].trim() : '';
      const right = typeof b[field] === 'string' ? b[field].trim() : '';
      if (!left || !right) return left ? -1 : right ? 1 : 0;
      return left.localeCompare(right, 'ko', {sensitivity:'base', numeric:true});
    });
    for (const row of ordered) {
      if (!row || typeof row !== 'object') continue;
      const button = node('button', undefined, 'candidate');
      button.type = 'button'; if (safeRef(row.key) !== '미확인') button.dataset.key = safeRef(row.key); button.setAttribute('aria-pressed', String(Boolean(selectedKey && selectedKey === button.dataset.key)));
      if (row.record_kind === 'claim') {
        const actor = null; // claim-to-speaker verification is not available
        button.append(node('strong', value(actor, '해석 주체 미확인')));
        if (!actor) button.append(node('small', `문헌 작성자 · ${value(row.source_creator, '미확인')}`));
        button.append(node('span', value(row.summary, '해석 요지 표시 보류'), 'candidate-summary'));
        button.append(node('small', `출처 · ${value(row.source_title, '서지 제목 표시 보류')}`));
      } else {
        button.append(node('strong', value(row.source_title, '서지 제목 표시 보류')));
        button.append(node('small', `문헌 작성자 · ${value(row.source_creator, '미확인')}`));
      }
      if (row.candidate_field_states) button.append(node('small', CANDIDATE_STATE_LABELS[row.candidate_field_states.source_title] || CANDIDATE_STATE_LABELS.missing_or_unmapped));
      button.append(node('small', `임시 참조 번호 · ${safeRef(row.key)}`, 'sr-only'));
      button.addEventListener('click', () => showDetail(row));
      results.append(button);
    }
  };
  pageSort.addEventListener('change', renderCards);
  const render = data => {
    // A document creator can be an institution and is not a claim's speaker.
    creatorFilterLabel.textContent = '문헌 작성자';
    rows = Array.isArray(data.records) ? data.records.map(row => safeRow(row, data.dataset, data.metadata_projection, data.summary_projection)).filter(Boolean) : [];
    renderMapping(data.unmapped_summary);
    const visibility = data.visibility_summary;
    const validCount = n => Number.isSafeInteger(n) && n >= 0 && n <= 100000;
    const coverage = data.metadata_coverage;
    const coverageLabels = {source_title:'문헌명',source_creator:'저자',source_publisher:'발행기관',source_year:'출판 연도',community_name:'공동체명'};
    if (isMetadataProjection(data.metadata_projection) && coverage && typeof coverage === 'object' && !Array.isArray(coverage) && Object.keys(coverageLabels).every(key => validCount(coverage[key]))) {
      const scope = data.metadata_projection === CANDIDATE_PROJECTION ? '로컬 후보 필드 검색 범위' : '확인된 필드 검색 범위';
      metadataCoverage.textContent = `${scope} (전체 후보 카드): ${Object.entries(coverageLabels).map(([key,label]) => `${label} ${coverage[key]}건`).join(' · ')}. 표시 보류 필드는 검색되지 않습니다.`;
    } else metadataCoverage.textContent = '서지 검색 범위: 미확인';
    candidateLimits.hidden = true;
    candidateLimitsContent.replaceChildren();
    const restrictions = data.candidate_restriction_summary;
    if (data.metadata_projection === CANDIDATE_PROJECTION && restrictions && typeof restrictions === 'object' && !Array.isArray(restrictions)) {
      for (const [scope,scopeLabel] of [['cards','후보 카드'],['sources','출처 레코드']]) {
        const group = restrictions[scope];
        if (!group || typeof group !== 'object' || Array.isArray(group)) continue;
        const list = node('ul');
        for (const [field,label] of Object.entries(coverageLabels)) {
          const counts = group[field];
          if (!counts || typeof counts !== 'object' || Array.isArray(counts)) continue;
          const reasons = Object.entries(CANDIDATE_REASON_LABELS)
            .filter(([key]) => validCount(counts[key]) && counts[key] > 0)
            .map(([key,reason]) => `${reason} ${counts[key]}건`);
          if (reasons.length) list.append(node('li', `${label}: ${reasons.join(' · ')}`));
        }
        if (list.children.length) {
          candidateLimitsContent.append(node('h3', scopeLabel), list);
          candidateLimits.hidden = false;
        }
      }
    }
    // Until the individual D-10 evidence is independently checked, no real
    // field grant can be inferred from an aggregate or a row-level flag.
    if (visibility && typeof visibility === 'object' && validCount(visibility.metadata_candidate) && validCount(visibility.candidate_visible_local) && (data.dataset === 'synthetic' || visibility.candidate_visible_local === 0)) {
      const conditional = data.dataset === 'D10' && validCount(visibility.conditional_candidate) ? ` · 조건부 후보 ${visibility.conditional_candidate}건` : '';
      if (data.metadata_projection === CANDIDATE_PROJECTION) {
        visibilityStatus.textContent = `원본 적격성 원장: 검토 후보 ${visibility.metadata_candidate}건${conditional}. 비공개 로컬 후보 표시는 이 원장과 별도이며 공개·재배포 승인이 아닙니다.`;
      } else {
        const distinction = data.metadata_projection === METADATA_PROJECTION ? ' 이 원장 집계와 확인된 서지 필드의 표시 범위는 별도입니다.' : '';
        visibilityStatus.textContent = `표시 적격성: 검토 후보 ${visibility.metadata_candidate}건${conditional} · 로컬 표시 승인 ${visibility.candidate_visible_local}건. 검토 후보와 조건부 후보는 표시 승인이 아닙니다.${distinction}`;
      }
    } else {
      visibilityStatus.textContent = '표시 적격성 정보: 미확인';
    }
    const total = Number.isSafeInteger(data.total) && data.total >= 0 ? data.total : rows.length;
    count.textContent = `${total}개 후보`;
    pageSize = Number.isSafeInteger(data.page_size) && data.page_size > 0 ? data.page_size : 100;
    prev.disabled = offset <= 0; next.disabled = offset + rows.length >= total || rows.length === 0;
    pageStatus.textContent = total ? `${offset + 1}–${offset + rows.length} / ${total}` : '';
    connection.textContent = data.dataset === 'synthetic' ? '합성 시험 자료 / 실제 연구 데이터 아님.' : `${data.dataset === 'D12' ? 'D-12' : data.dataset === 'D10' ? 'D-10' : data.dataset === 'D9' ? 'D-9' : 'D-8'} 연구 후보 · 선택한 로컬 자료에서 조회했습니다. 모든 결과는 연구 후보입니다.`;
    empty.hidden = rows.length > 0;
    renderCards();

  };
  const search = async () => {
    clear();
    if (!secret) { connection.textContent = '세션 비밀을 입력해 주세요.'; return; }
    const current = generation;
    controller = new AbortController();
    const query = new URLSearchParams();
    for (const [key, item] of new FormData(form)) if (typeof item === 'string' && item.trim()) query.set(key, item.trim());
    const nameSearchBlocked = () => {
      if (!query.get('community') && !query.get('researcher')) return false;
      if (!verifiedMetadataProjection || !metadataNameCoverage) return true;
      return Boolean((query.get('community') && metadataNameCoverage.community_name === 0) ||
        (query.get('researcher') && metadataNameCoverage.source_creator === 0));
    };
    const showNameSearchBlocked = () => {
      count.textContent = '검색 보류';
      connection.textContent = '요청한 이름 필드에서 검색 가능한 값이 없어 검색이 보류됐습니다.';
      empty.textContent = '요청한 이름 검색은 보류 중입니다. 표시 보류는 일치하는 자료가 없다는 뜻이 아닙니다.';
      empty.hidden = false;
    };
    if (sessionDataset && sessionDataset !== 'synthetic' && nameSearchBlocked()) {
      showNameSearchBlocked();
      return;
    }
    if (offset) query.set('offset', String(offset));
    connection.textContent = '연구 후보를 불러오는 중입니다.';
    try {
      const response = await fetch(`/api/candidates${query.size ? `?${query}` : ''}`, {cache:'no-store', headers:{Authorization:`Bearer ${secret}`}, signal:controller.signal});
      if (current !== generation) return;
      if (response.status === 401 || response.status === 403) { secret = ''; connection.textContent = '세션을 열지 못했습니다.'; showError('세션 비밀을 확인하고, 연속으로 실패한 경우 10초 뒤 다시 시도해 주세요.'); return; }
      if (!response.ok) throw new Error('unavailable');
      const data = await response.json();
      if (current !== generation) return;
      if (!data || !Array.isArray(data.records) || !['D8','D9','D10','D12','synthetic'].includes(data.dataset)) throw new Error('unexpected');
      if (sessionDataset && sessionDataset !== data.dataset) throw new Error('dataset mismatch');
      sessionDataset = data.dataset;
      verifiedMetadataProjection = isMetadataProjection(data.metadata_projection);
      const nameCoverage = data.metadata_coverage;
      metadataNameCoverage = verifiedMetadataProjection && nameCoverage && typeof nameCoverage === 'object' &&
        Number.isSafeInteger(nameCoverage.community_name) && nameCoverage.community_name >= 0 && nameCoverage.community_name <= 100000 &&
        Number.isSafeInteger(nameCoverage.source_creator) && nameCoverage.source_creator >= 0 && nameCoverage.source_creator <= 100000 ? nameCoverage : null;
      if (sessionDataset !== 'synthetic' && nameSearchBlocked()) { showNameSearchBlocked(); return; }
      empty.textContent = '표시 가능한 필드에서 조건에 맞는 후보가 없습니다. 표시 보류된 필드의 일치 여부는 확인할 수 없습니다.';
      render(data);
    } catch (e) {
      if (current !== generation || e.name === 'AbortError') return;
      connection.textContent = '자료를 불러오지 못했습니다.';
      showError(e.message === 'dataset mismatch' ? '선택한 자료 버전과 응답이 일치하지 않습니다.' : '자료를 불러오지 못했습니다. 로컬 서버 상태와 선택한 자료를 확인해 주세요.');
    }
  };
  const comparisonPanel = document.getElementById('comparison-panel');
  const candidateLayout = document.getElementById('candidate-layout');
  const comparisonStatus = document.getElementById('comparison-status');
  const comparisonResults = document.getElementById('comparison-results');
  const comparisonCorpus = document.getElementById('comparison-corpus');
  const comparisonStage = document.getElementById('comparison-stage');
  const comparisonScheme = document.getElementById('comparison-scheme');
  const comparisonReference = document.getElementById('comparison-reference');
  const comparisonTradition = document.getElementById('comparison-tradition');
  const selectionTools = document.getElementById('comparison-selection');
  const selectionStatus = document.getElementById('comparison-selection-status');
  const selectedOnly = document.getElementById('comparison-selected-only');
  const clearSelectionButton = document.getElementById('comparison-clear-selection');
  let selectedClaims = new Set();
  let selectionCards = [];
  let selectionOnly = false;
  const refreshSelection = () => {
    const size = selectedClaims.size;
    selectionStatus.textContent = `비교할 해석 ${size}개 선택 · 2~3개 선택`;
    selectedOnly.disabled = size < 2;
    clearSelectionButton.disabled = size === 0;
    selectedOnly.setAttribute('aria-pressed', String(selectionOnly));
    selectedOnly.textContent = selectionOnly ? '전체 해석 보기' : '선택한 해석만 보기';
    for (const item of selectionCards) {
      item.checkbox.checked = selectedClaims.has(item.key);
      item.checkbox.disabled = !item.checkbox.checked && size >= 3;
      item.card.hidden = selectionOnly && !item.checkbox.checked;
    }
  };
  const clearComparisonSelection = () => {
    selectedClaims = new Set(); selectionCards = []; selectionOnly = false;
    selectionTools.hidden = true; refreshSelection();
  };
  selectedOnly.addEventListener('click', () => {
    if (selectedClaims.size < 2) return;
    selectionOnly = !selectionOnly; refreshSelection();
  });
  clearSelectionButton.addEventListener('click', () => {
    selectedClaims.clear(); selectionOnly = false; refreshSelection();
  });
  const resetComparison = () => {
    closeDrawer();
    comparisonGeneration += 1;
    if (comparisonController) comparisonController.abort();
    comparisonController = null; comparisonPassages = [];
    comparisonResults.replaceChildren();
    clearComparisonSelection();
    for (const select of [comparisonCorpus, comparisonScheme, comparisonReference]) select.replaceChildren(new Option('선택', ''));
    comparisonTradition.replaceChildren(new Option('전체', ''));
    comparisonStatus.textContent = '세션을 열고 본문 비교를 선택하세요.';
  };
  const fillOptions = (select, values) => {
    select.replaceChildren(new Option('선택', ''));
    for (const item of [...new Set(values)].sort()) select.add(new Option(item, item));
  };
  const invalidateComparison = () => {
    closeDrawer();
    comparisonGeneration += 1;
    if (comparisonController) comparisonController.abort();
    comparisonController = null;
    comparisonResults.replaceChildren();
    clearComparisonSelection();
    comparisonStatus.textContent = '본문을 선택하고 해석 비교를 눌러 주세요.';
  };
  const refreshSchemes = () => {
    invalidateComparison();
    fillOptions(comparisonScheme, comparisonPassages.filter(p => p.corpus === comparisonCorpus.value).map(p => p.scheme));
    fillOptions(comparisonReference, []);
    comparisonResults.replaceChildren();
  };
  const refreshReferences = () => {
    invalidateComparison();
    fillOptions(comparisonReference, comparisonPassages.filter(p => p.corpus === comparisonCorpus.value && p.scheme === comparisonScheme.value).map(p => p.reference));
    comparisonResults.replaceChildren();
  };
  const fetchComparison = async (query = null) => {
    comparisonGeneration += 1;
    const current = comparisonGeneration;
    if (comparisonController) comparisonController.abort();
    comparisonController = new AbortController();
    comparisonResults.replaceChildren();
    clearComparisonSelection();
    if (!secret || !sessionDataset) { comparisonStatus.textContent = '먼저 비공개 세션을 열어 주세요.'; return; }
    comparisonStatus.textContent = '본문 후보를 불러오는 중입니다.';
    try {
      const params = new URLSearchParams();
      if (comparisonStage.value === 'd12') params.set('stage', 'd12');
      if (query) for (const [key,item] of Object.entries(query)) params.set(key,item);
      const response = await fetch(`/api/comparison${params.size ? `?${params}` : ''}`, {cache:'no-store',headers:{Authorization:`Bearer ${secret}`},signal:comparisonController.signal});
      if (current !== comparisonGeneration) return;
      if (!response.ok) throw new Error('unavailable');
      const data = await response.json();
      if (current !== comparisonGeneration) return;
      if (!data || data.dataset !== sessionDataset || !Array.isArray(data.passages) || !Array.isArray(data.claims)) throw new Error('unexpected');
      if (!query) {
        comparisonPassages = data.passages.filter(p => p && typeof p === 'object' && ['corpus','scheme','reference'].every(k => typeof p[k] === 'string' && p[k].trim() && p[k].length <= 150) && Number.isSafeInteger(p.claim_count) && p.claim_count >= 0);
        fillOptions(comparisonCorpus, comparisonPassages.map(p => p.corpus));
        fillOptions(comparisonScheme, []); fillOptions(comparisonReference, []);
        comparisonTradition.replaceChildren(new Option('전체', ''));
        if (data.tradition_projection === 'k2-reviewed-tradition' && Array.isArray(data.traditions)) {
          const labels = data.traditions.filter(t => t && typeof t.value === 'string' && t.value.trim() && t.value.length <= 200 && !/[\x00-\x1f\x7f]/.test(t.value) && Number.isSafeInteger(t.claim_count) && t.claim_count > 0).map(t => t.value);
          for (const label of [...new Set(labels)].sort()) comparisonTradition.add(new Option(label, label));
        }
        const multiple = comparisonPassages.filter(p => p.claim_count >= 2).length;
        const links = comparisonPassages.reduce((sum, p) => sum + p.claim_count, 0);
        comparisonStatus.textContent = comparisonPassages.length
          ? `본문 주소 ${comparisonPassages.length}개 · 복수 해석 주소 ${multiple}개 · 본문 연결 ${Number.isSafeInteger(links) ? links : '미확인'}건 · 코퍼스와 장절 체계를 선택하세요.`
          : '비교할 본문 후보가 없습니다.';
        return;
      }
      if (!data.selected || ['corpus','scheme','reference'].some(k => data.selected[k] !== query[k])) throw new Error('unexpected');
      const cards = data.claims.map(raw => ({raw, row:safeRow(raw, data.dataset, data.metadata_projection)})).filter(item => item.row && item.row.record_kind === 'claim');
      comparisonStatus.textContent = cards.length ? `선택한 본문의 연구 후보 ${cards.length}건` : '선택한 본문에 표시할 연구 후보가 없습니다.';
      selectionTools.hidden = cards.length < 2;
      for (const {raw,row} of cards) {
        const card = node('article', undefined, 'comparison-card');
        const selectionKey = safeRef(row.key);
        if (cards.length >= 2 && selectionKey !== '미확인') {
          const choice = node('label', undefined, 'comparison-choice');
          const checkbox = document.createElement('input'); checkbox.type = 'checkbox';
          choice.append(checkbox, node('span', '이 해석을 비교 대상으로 선택'));
          checkbox.addEventListener('change', () => {
            if (checkbox.checked && selectedClaims.size < 3) selectedClaims.add(selectionKey);
            else selectedClaims.delete(selectionKey);
            if (selectedClaims.size < 2) selectionOnly = false;
            refreshSelection();
          });
          selectionCards.push({key:selectionKey, card, checkbox});
          card.append(choice);
        }
        card.append(node('p', '원본 기록 · 독립 확인 전', 'tag'));
        const facts = node('dl', undefined, 'facts');
        fact(facts, '문헌 작성자', row.source_creator);
        const candidateSummary = data.summary_projection === 'k2-reviewed-summary' && raw && raw.summary_status === 'recorded_unverified' && typeof raw.summary === 'string' && raw.summary.trim() && raw.summary.length <= 500 && !/[\x00-\x1f\x7f]/.test(raw.summary) ? raw.summary : null;
        fact(facts, '해석 요지', candidateSummary || '표시 보류 · 권리와 인용 범위 검토 필요');
        fact(facts, '해석 요지 확인', candidateSummary ? '원본 기록 · 독립 확인 전' : '미확인 · 표시 보류');
        fact(facts, '출처 위치', '권리·형식 검토 전 표시 보류');
        fact(facts, '출처 확인', readable(row.source_verification_status));
        fact(facts, '입력 주장 검증', row.verification_status);
        fact(facts, '공식성', row.authority_status);
        fact(facts, '논증 검토', row.argument_status);
        fact(facts, '독립 학술 심사', readable(row.independent_review_status));
        fact(facts, '귀속', readable(row.attribution));
        const tradition = data.tradition_projection === 'k2-reviewed-tradition' && raw && raw.tradition_candidate && raw.tradition_candidate.status === 'recorded_unverified' && typeof raw.tradition_candidate.value === 'string' && raw.tradition_candidate.value.trim() && raw.tradition_candidate.value.length <= 200 && !/[\x00-\x1f\x7f]/.test(raw.tradition_candidate.value) ? raw.tradition_candidate.value : null;
        fact(facts, '원본 전통 라벨 · 귀속 및 공식성 미확인', tradition || '표시 보류 또는 미확인');
        fact(facts, '공동체 참조 역할', row.community_role === 'self' ? '자기 설명' : row.community_role === 'target' ? '외부 비평의 대상' : '미확인');
        fact(facts, '비공개 로컬 표시', row.candidate_field_states && CANDIDATE_STATE_LABELS[row.candidate_field_states.source_title]);
        fact(facts, '공개 · 재배포', '별도 승인 필요');
        appendPrimary(card, row, candidateSummary);
        const actionsPanel = node('div', undefined, 'card-actions');
        const evidenceButton = node('button', '근거·출처 보기', 'target-button');
        evidenceButton.type = 'button';
        evidenceButton.addEventListener('click', () => openDrawer('근거·출처', evidencePanel(row, candidateSummary), evidenceButton));
        const verificationButton = node('button', '검증 정보 보기', 'target-button');
        verificationButton.type = 'button';
        verificationButton.addEventListener('click', () => {
          // Reuse the complete existing detail view so access observations,
          // edition rights and technical references remain available.
          const holder = node('div');
          showDetail(row, holder);
          const existing = [...holder.querySelectorAll('button')].find(button => button.textContent === '검증 정보 보기');
          if (existing) {
            drawerOpener = verificationButton;
            existing.click();
            drawerOpener = verificationButton;
            drawerContent.append(facts);
          }
        });
        actionsPanel.append(evidenceButton, verificationButton);
        if (safeCoordinate(row.source_key, 'sources') !== '미확인') {
          const source = node('button', '연결 문헌 보기', 'target-button');
          source.type = 'button';
          source.addEventListener('click', () => openSourceDrawer(row.source_key, source));
          actionsPanel.append(source);
        }
        card.append(actionsPanel);
        comparisonResults.append(card);
      }
      refreshSelection();
    } catch (err) {
      if (current !== comparisonGeneration || err.name === 'AbortError') return;
      comparisonStatus.textContent = '본문 비교를 불러오지 못했습니다. 로컬 서버와 자료를 확인해 주세요.';
    }
  };
  const openComparisonAt = async passage => {
    // Do not infer equivalence between corpora or numbering systems: select
    // only the exact triple returned by the authenticated candidate API.
    if (!passage || !['corpus','scheme','reference'].every(k => typeof passage[k] === 'string' && passage[k].trim())) return;
    closeDrawer();
    candidateLayout.hidden = true; comparisonPanel.hidden = false;
    document.getElementById('candidate-view').setAttribute('aria-pressed', 'false');
    document.getElementById('comparison-view').setAttribute('aria-pressed', 'true');
    comparisonStage.value = '';
    await fetchComparison();
    if (!comparisonPassages.some(p => p.corpus === passage.corpus && p.scheme === passage.scheme && p.reference === passage.reference)) {
      comparisonStatus.textContent = '같은 코퍼스와 장절 체계의 본문을 확인할 수 없습니다.';
      return;
    }
    comparisonCorpus.value = passage.corpus; refreshSchemes();
    comparisonScheme.value = passage.scheme; refreshReferences();
    comparisonReference.value = passage.reference;
    await fetchComparison({corpus:passage.corpus, scheme:passage.scheme, reference:passage.reference});
    comparisonCorpus.focus();
  };
  document.getElementById('comparison-view').addEventListener('click', () => {
    const returning = comparisonPanel.hidden;
    candidateLayout.hidden = true; comparisonPanel.hidden = false;
    document.getElementById('candidate-view').setAttribute('aria-pressed', 'false');
    document.getElementById('comparison-view').setAttribute('aria-pressed', 'true');
    if (!returning || !comparisonPassages.length) {
      comparisonStage.value = sessionDataset === 'D12' ? 'd12' : '';
      fetchComparison();
    }
  });
  document.getElementById('candidate-view').addEventListener('click', () => {
    comparisonGeneration += 1; if (comparisonController) comparisonController.abort();
    candidateLayout.hidden = false; comparisonPanel.hidden = true;
    document.getElementById('candidate-view').setAttribute('aria-pressed', 'true');
    document.getElementById('comparison-view').setAttribute('aria-pressed', 'false');
  });
  comparisonCorpus.addEventListener('change', refreshSchemes);
  comparisonStage.addEventListener('change', () => { invalidateComparison(); fetchComparison(); });
  comparisonScheme.addEventListener('change', refreshReferences);
  comparisonReference.addEventListener('change', invalidateComparison);
  comparisonTradition.addEventListener('change', invalidateComparison);
  document.getElementById('comparison-form').addEventListener('submit', event => {
    event.preventDefault();
    if (!comparisonCorpus.value || !comparisonScheme.value || !comparisonReference.value) return;
    const query = {corpus:comparisonCorpus.value,scheme:comparisonScheme.value,reference:comparisonReference.value};
    if (comparisonTradition.value) query.tradition = comparisonTradition.value;
    fetchComparison(query);
  });
  document.getElementById('session-form').addEventListener('submit', event => {
    event.preventDefault();
    resetComparison();
    offset = 0;
    sessionDataset = null;
    creatorFilterLabel.textContent = '문헌 작성자';
    verifiedMetadataProjection = false;
    metadataNameCoverage = null;
    secret = secretInput.value;
    secretInput.value = '';
    search();
  });
  document.getElementById('session-close').addEventListener('click', () => {
    secret = ''; sessionDataset = null; verifiedMetadataProjection = false; metadataNameCoverage = null; creatorFilterLabel.textContent = '문헌 작성자'; secretInput.value = ''; clear(); resetComparison(); comparisonPanel.hidden = true; candidateLayout.hidden = false; document.getElementById('candidate-view').setAttribute('aria-pressed', 'true'); document.getElementById('comparison-view').setAttribute('aria-pressed', 'false'); connection.textContent = '세션이 닫혔습니다.';
  });
  form.addEventListener('input', () => { offset = 0; clear(); connection.textContent = secret ? '조건이 변경됐습니다. 후보 검색을 눌러 주세요.' : '세션 비밀을 입력해 주세요.'; });
  form.addEventListener('change', () => { offset = 0; clear(); connection.textContent = secret ? '조건이 변경됐습니다. 후보 검색을 눌러 주세요.' : '세션 비밀을 입력해 주세요.'; });
  form.addEventListener('submit', event => { event.preventDefault(); offset = 0; search(); });
  form.addEventListener('reset', () => { offset = 0; clear(); setTimeout(search, 0); });
  prev.addEventListener('click', () => { offset = Math.max(0, offset - pageSize); search(); });
  next.addEventListener('click', () => { offset += pageSize; search(); });
})();
