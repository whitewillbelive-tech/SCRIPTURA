# I-2 권위·근거 계약 차이

기준은 `whitewillbelive-tech/SCRIPTURA`의 `codex/scriptura-i1-d3-receipt` / `e12449adab98eee8421e06d1bb9cca5933991e82`다. 인계의 `AUTHORITY_AND_EVIDENCE_v0.1`과 `D5_RECORD_FORMAT_v0.1`은 필드·enum 초안이지 실자료의 승인이나 실제 D-5 결과가 아니다. 동결 D-4는 읽기 전용으로만 검사하고, 권위 누락을 임의로 채우거나 source_verified를 공식 채택·독립 학술 심사로 승격하지 않는다. 인계 문서는 D-5를 병렬 작업으로 명시하며 본 작업은 그 결과를 예상하거나 읽지 않는다.

## 권위와 네 개 독립 축

| 축 | 허용 상태 | 독립적으로 나타내는 것 |
|---|---|---|
| 인용 `quotation_status` | direct_checked, translation_checked, secondary_report, search_only, unchecked | 해당 위치의 직접/번역/전언/검색 확인 수준. 번역 확인은 원어 직접 대조가 아니다. |
| 권위 `authority_status` | adoption_documented, issuer_documented, historical_only, individual_only, disputed, unknown | 누가 어떤 지위로 무엇을 채택·발행했는지. 발행이나 개인 소속은 채택이 아니다. |
| 논증 `argument_status` | documented_argument, externally_challenged, cross_checked, contested, not_assessed | 논증에 대한 기록 및 검토 상태. 교단 지위나 학술지 게재로 역사·언어 사실을 자동 확정하지 않는다. |
| 독립 검수 `independent_review_status` | human_review_documented, published_critique_documented, none, pending | 주장에 대한 문서화된 별도 검수. 논문 게재나 모델 생성 결과는 독립 인간 검수 행위가 아니다. |

인용이 직접 확인되어도 권위·논증·독립 검수는 바뀌지 않는다. 자료가 불충분하면 `unknown` 및 `insufficient_evidence`로 남긴다. 신학적 진실을 전통 간 점수·다수결로 정하지 않으며, 상충 견해와 기준·출처를 함께 보인다. 같은 전통 안에 복수 지역·시대·권위가 있을 수 있으므로 단일 권위를 강제로 선택하지 않는다.

문헌 유형도 `normative_adopted`, `official_institutional_guidance`, `historical_organizational_publication`, `individual_insider_view`, `external_description_or_criticism`, `scholarly_individual_analysis`, `plural_or_unresolved`로 별개다. 기관 자기 설명과 외부의 비판, 공식 교육 자료와 공식 채택 교리, 개인의 소속과 기관의 채택을 서로 치환하지 않는다. 서지 인용은 논증적 지지·반박으로 자동 변환하지 않는다.

## D-5 필드 계약 7종과 기존 기준의 차이

| D-5 계약 데이터 | 계약의 주요 필드/상태 | 001–005 및 수신 경계에서의 보류 |
|---|---|---|
| `authority_registries` | tradition ID·라벨, authority model 8종, scope, 공식 근거 locator, verification status, checked_at | 기존 `traditions`는 종교/교단/운동/학파 계층이지 채택 권위·관할·근거 등록부가 아니다. 라벨 유사성으로 기존 ID를 확정할 수 없다. |
| `authority_documents` | registry, title/issuer/document kind/scope/published_at/edition/locator, 7가지 문헌권위, adoption/verification status | 기존 source·edition·locator는 문서 발행기관과 공동체 채택을 독립적으로 보장하지 않는다. 문서·판본·언어·발행/개정과 적용 기간, 관할, 번역/직접 확인 경로, 정확한 채택 근거가 불충분하면 보류한다. |
| `claim_scope_audits` | baseline claim ID, 네 축 상태, basis locator, checked_at, issuer, scope note | `claim_versions.review_status`는 하나의 출처 검수 축이며 네 상태와 동등하지 않다. baseline claim ID를 claim_version ID로 임의 변환하지 않고 원 이력과 확인 범위를 별도 보존한다. |
| `position_attestations` | tradition/document/passage IDs, 요약, scope 7종, source locator, as-of, verification status | 전통의 자기 문헌, 지역별 입장, 역사적 입장, 개인, 타자 귀속, 복수 및 근거 부족을 구분해야 한다. 기존 claim–passage 연결만으로 공동체 대표성을 증명할 수 없다. |
| `interpretive_evidence` | attestation, discipline(본문비평·언어학·역사·정경/고백신학·문학·기타), kind, locator, 설명, source_checked/contested/pending | 기존 evidence는 주장의 버전 FK에 연결되며 해당 해석의 학문적 방법이나 독립 검수 증거를 자동으로 갖지 않는다. 출처 확인과 논증 평가를 분리한다. |
| `rights_delta` | edition, 9개 action, allowed/conditional/unknown/prohibited, evidence locator, 목적·지역·검토일 | 001의 단일 source storage_policy/license_status는 edition×행위×목적·지역·기간별 근거를 무손실로 나타내지 못한다. 미확인·조건부는 허용이 아니며 한 행위의 허가는 다른 행위로 이전되지 않는다. |
| `source_access_events` | source, 접근 방법·시각·범위, direct_checked/translation_checked/search_only/blocked/unknown | 기존 source_locator 체크는 판본·접근 경로 및 직접/간접·검색의 모든 의미를 보존하지 않는다. 별도 행사와 범위 증거가 필요하며 자동으로 원어 직접 대조로 전환하지 않는다. |

9개 권리 행위는 browse, collect_metadata, store_raw, store_excerpt, index_fulltext, embed, send_to_model, redistribute, public_link다. 이 단계에서 실제 외부 원문 저장·색인·임베딩·모델 전송·재배포 기능은 제공하지 않으며 기본은 전부 거부다. 허용이라고 적힌 입력 행은 그 자체로 목적·지역·기간 검증이나 새로운 이용권의 근거가 아니다.

## 공식 채택의 증거 경계

공식 채택 표현은 같은 공동체의 규정된 절차로 해당 문서가 그 지위로 채택되었다는 추적 가능한 근거에 한정한다. 문서 발행 주체·적용 전통·관할, 발행 및 개정 시점, 유효 범위와 입장 시점, 판본·언어, 직접/번역 확인 경로, 확인된 정확 locator, 공식 채택 및 주체–전통 관계의 근거를 확인해야 한다. 누락·모순·전언만 있으면 공식 채택이라고 표시하지 않는다. 중앙 권위의 존재나 범위가 불명확한 경우에도 좁은 근거 범위를 넘겨 일반화하지 않는다.

동결 D-4 입력에는 `official_doctrine` 귀속 라벨 2건이 존재하지만 이는 원본이 사용한 귀속 라벨의 집계다. 어느 행도 라벨만으로 위의 모든 채택 요건을 충족했다고 판정하지 않는다. 78개 주장 중 source_verified 74·candidate 4·독립 scholarly_reviewed 0은 인계 자료의 검증 단계이며 신학적 진실·공식 채택·저작권 허가의 수가 아니다. 공식 자료와 채택 상태의 실제 확인 여부는 읽기 전용 D-4 dry-run 및 별도 근거 검토로 보고한다.

고정 D-4의 12종·부가 자료와 인계 파일은 실제 연구 메타데이터다. 원본 ZIP, 실제 원문·URL·행을 공개 저장소·CI에 싣지 않고 aggregate/hash와 합성 시험만 공유한다. 이후 Work D-5 자료는 별도 계약 및 I-3 수용 절차에서 비교한다.

## 공식 근거 직접 확인의 현재 범위

실행 환경의 restricted outbound 정책에 인계에 열거된 공식 기관 호스트들이 허용되어 있지 않다. 그중 교리서 및 교단 신앙고백 공식 문서 2곳에 기존 HTTPS 프록시로 요청한 결과 모두 CONNECT 403이어서 실제 기관 서버의 응답에 도달하지 못했다. 이는 인증된 공식 문서의 내용 확인이나 채택 사실 확인이 아니다. 정책을 우회하지 않았고 네트워크 상태가 바뀐 뒤 공식 문서·정확한 위치·시점·관할을 다시 대조해야 한다. 구조적으로 확인할 수 있는 기존 인계의 locator 참조와 원본 상태, 검증되지 않은 채택 상태는 분리해 기록한다.
