# Gate I-3 — D-5/D-6 수신 계약과 기존 스키마 호환성

기준 `whitewillbelive-tech/SCRIPTURA`, `codex/scriptura-i2-1-ci-repair` / `3865a14fd60a64fa9447b52c3e98b6f31991204b`. 동결 D-6은 D-5 ZIP을 이미 내장한다. D-5를 중복 반입하거나 원형 레코드·상태·평가자를 바꾸지 않는다. 이 문서의 건수는 입력 검토 집계이며 원본 연구 레코드의 공개나 실제 DB 적재 승인이 아니다. 새 D-7 결과는 입력하지 않았다.

## D-5 주요 계약과 기존 스키마

| D-5 데이터 | 원본 관계와 검토 건수 | 001–006 대응 및 보류 |
|---|---|---|
| `authority_registries` | 19건. registry 고유 ID와 별도 `tradition_id`를 모두 보존한다. `tradition_id`는 registry 행의 ID가 아니다. | 001 `traditions`는 계층이지 중앙·분권 권위 모형, 절차, 관할과 증거의 registry가 아니다. 이름 일치만으로 공동체 ID를 생성·병합하지 않는다. |
| `authority_documents` | 61건, 전부 registry ID 참조. 문헌 locator는 D-5 locator 또는 기존 D-4 locator를 가리키며 baseline source/edition은 일부만 존재한다. | 006 문서와 부분 대응하지만 적용기간·관할·언어·개정일·발행기관 ID·형식적 채택의 완결 조건이 부족한 경우가 있다. 006의 엄격한 FK·시점 요구를 맞추려고 값을 합성하거나 입력 상태를 승격하지 않는다. |
| `claim_scope_audits` | 78건 모두 기준 claim과 근거 위치에 연결되며 일부만 문헌 ID를 갖는다. 인용·권위·논증·독립검수는 별도 값이다. | 001 claim/version과 006 attestation에 맞추어 `baseline_claim_id`를 version ID로 추정하지 않는다. 축별 원래 평가자·시각과 근거를 보존한다. 원본 `source_checked`나 게재 사실로 독립 인간 검수를 만들지 않는다. |
| `position_attestations` | 51건 모두 D-5 문헌을 가리킨다. passage와 locator는 D-5와 D-4 네임스페이스에 걸치며 baseline claim은 34건에만 존재한다. | 006 attestation은 한 버전·문헌·전통·주체의 정확한 ID와 확인 가능한 범위를 요구한다. 문헌·발행·공식 채택과 개인 입장을 구분하고 부족하면 격리한다. |
| `interpretive_evidence` | 36건 모두 attestation에 연결된다. locator는 D-4 또는 D-5에 있고 추가 locator, 해당 기준 claim은 선택적이다. | 001 claim_evidence는 이 다형 참조·분야·접근 범위·독립심사 여부를 무손실 보장하지 않는다. 서지 인용·공통 주제를 직접 논증적 지지나 반박으로 변환하지 않는다. |
| `rights_delta` | 판본 32 × 9행위 = 288건, 전부 `unknown`. `evidence_locator_id`에 들어 있는 공통 결손 표시는 실제 locator ID 집합에서 확인되지 않는다. | 001 source의 단일 license/storage 필드는 판본 × 행위 × 목적 × 지역 × 시점의 원본 결정을 표현하지 못한다. 결손 표시를 유효 FK나 허가로 취급하지 않고 원문·사유를 보존한다. |
| `source_access_events` | 110건이며 접근 방식·한계·평가자·확인 범위가 다양하다. | 001 provenance/review는 원본 접근 결과와 전문 저장 바이트, 간접 확인을 완전하게 표현하지 않는다. 사람의 독립 학술 심사와 기계적 접근 확인을 혼동하지 않는다. |

D-5 `authority_documents`가 기록한 `normative_adopted` 7건, 주장 감사가 기록한 `adoption_documented` 2건은 **원본의 자체 상태 집계**다. I-3가 외부 공식 문헌, 채택 범위 및 현재 효력을 독립 확인했다는 뜻은 아니다. 006의 충분 근거 조건을 통과하지 못한 원본 표기도 그대로 보존하며 별도 pending 판정한다.

## D-6 12종 수신과 관계

| 파일 | 건수 | 대상·관계·유의점 |
|---|---:|---|
| `communities` | 5 | 자기 명칭·별칭·관계·설립/지도자 확인 상태를 보존한다. 별칭은 신원 병합이나 소속 증명이 아니다. 기존 D-5 registry의 전통 참조는 새 community 행이 아니며 중복 생성하지 않는다. |
| `sources` | 31 | 서지 메타데이터 및 접근 상태를 보존한다. source에 게시됐다는 사실만으로 발언·공식 채택·재배포 권한을 부여하지 않는다. |
| `editions` | 31 | 전부 D-6 source를 참조한다. 언어·판본·발행 시점은 원본 유무 그대로 기록한다. |
| `locators` | 42 | 전부 D-6 edition을 참조한다. 직접/번역/검색·전언과 정확 위치/확인 시각을 구별한다. |
| `claims` | 33 | self explanation 27, 개인 2, 학술 해석 2, 외부 비판 2. community 참조는 D-6 행 27, D-5 registry의 전통 참조 5, null 1이다. 별도로 대상 역할로 표시된 참조는 발화 공동체가 아니다. 모든 source locator는 D-6 locator를 가리킨다. |
| `passages` | 53 | 코퍼스·원 주소·장절 체계·판본 검증 및 정렬 상태를 유지한다. 적어도 42건은 미정렬 또는 pending이며 나머지도 서로 다른 체계 사이의 확정 정렬이 아니다. 1개 claim은 기존 D-4 passage도 참조한다. |
| `authority` | 24 | 판본·발행기관·관할·공식 채택 여부와 원형의 각 선택적 locator 필드를 구별한다. community는 D-6 8, D-5 전통 3, 누락 13이며, 없는 issuer·채택 사실을 만들어 채우지 않는다. |
| `evidence` | 34 | claim과 locator를 각각 D-6 ID로 연결하며 passage 목록은 선택적이다. 근거 종류·확인 경로와 관계를 보존한다. |
| `assessments` | 8 | 평가 주체, 평가 대상, 발표/평가 시점, 상태 및 출처는 독립 실체다. 대상은 D-6 community 6, D-5 전통 2다. 조사 진행 보도·종교기관 결의·학술 비평은 서로 다르다. |
| `relationships` | 11 | subject는 claim 또는 assessment, object는 claim·assessment·community·edition·D-5 문헌/전통·D-4 claim 등 다형 참조다. locator는 D-6 또는 D-5에 있다. 후보·공유 주제·출처 보도·직접 겨냥 관계를 보존하고, 특정 상대를 겨냥한 근거 없는 대조를 반박으로 표시하지 않는다. |
| `rights` | 279 | 31판본 × 9행위: `unknown` 275, `conditional` 4. 원본 대소문자·원결정과 조건, 결손 locator는 변환 없이 남긴다. 둘 다 실사용 허가가 아니다. |
| `source_access_events` | 33 | source/edition/locator 및 source_locator 등 필드는 입력 종류에 따라 선택적이다. 직접 원문·번역·2차 전언·검색·접근 차단·원문 저장 여부와 평가 주체를 독립 보존한다. |

9개 행위는 browse, collect_metadata, store_raw, store_excerpt, index_fulltext, embed, send_to_model, redistribute, public_link다. 입력 상태가 unknown 또는 conditional인 경우 실제 이용 권한은 기본 거부다. 이번 단계는 권리 미확인 원문을 수집·저장·전송·재배포하지 않는다.

## 무손실 수신 및 격리 경계

1. 실제 ZIP은 해시·manifest·인코딩·JSONL·ID·참조 및 값 관계를 **읽기 전용** 검사하고 raw ZIP과 원행은 공개 저장소·PostgreSQL에 넣지 않는다. 원형 보존은 불변 입력, 행 해시, 원본 파일/행 추적을 통한 검토 계약을 뜻하며 공개 요약만으로 원본을 재구성할 수 있다는 뜻이 아니다.
2. 본문·평가자는 독립 식별자와 참조 역할을 사용한다. `community_id`가 대상인 경우 발화자가 아니며 null인 외부 학술 주장을 가상의 소속으로 채우지 않는다. 전통 registry의 `tradition_id`와 registry 행 ID를 분리한다.
3. 직접 반박·상호 참조·공유 본문 대조·유사 주제와 출처의 보도, 공동체 자기 설명 및 외부 평가의 방향·범위·시간·근거를 각각 구분한다. 검증 범위가 부족한 경로는 원 상태와 함께 `quarantined`/`pending`으로 표시한다.
4. 평가 주체의 논평, 언론의 진행 중 조사 보도, 기관의 실제 결의는 각각 독립 출처·행위자·시점·효력 범위를 필요로 한다. 종교적 평가나 혐의를 아카이브 자체의 확정 분류로 바꾸지 않는다.
5. I-2의 `authority_documents`/`authority_attestations`, 001 단일 행위 권리, 기존 claim relation enum 및 passage scheme만으로 12종·다형 ID·평가 주체·정확한 관할과 원 상태를 무손실 DB 투영할 수 없다. 실제 자료 import 및 공식 승격 기능은 제공하지 않으며, 합성 격리 시험 결과를 실자료 승인으로 해석하지 않는다.
6. 결과 요약의 카운트·해시·이유는 접근 범위와 추적 식별자의 공개 가능성을 별도 검토해야 하며, 판본별 권리·개인정보·자료 진위와 독립 검토를 자동 증명하지 못한다. 사용자 신학적 승인 없이 확인 가능한 사실도 근거가 실제로 확보되지 않았다면 pending이다.

## 007 합성 staging 보강의 한계

`007_i3_research_guard.sql`은 004/005가 선행된 전용 합성 staging의 고정 D-4·D-5·D-6 ZIP SHA만 추가 거부한다. 기존 CLI는 자체 생성 합성 스냅샷만 받아 메타데이터와 출처 해시를 저장하며 D-5/D-6 실자료 importer가 아니다. 007은 재포장된 ZIP이나 다른 연구 파일, 합성이라고 속인 기록을 자동 인식하지 못하고, 고권한 사용자나 직접 DB 접근까지 전반적으로 차단하지 않는다. 실제 자료의 수신·권리 및 DB 쓰기는 계속 금지한다. 전용 빈 시험 DB에서만 역방향 마이그레이션이 가능하며 staging 관찰/기록이 있을 때는 데이터 보존을 위해 롤백을 거부한다.

### 공개 보고서의 해시 식별 위험

공개 격리 보고서와 `mapping-preview`에는 추측 가능한 ID의 무염 해시를 내보내지 않고 자료 계층·테이블·행 번호로 참조한다. 원 행 SHA-256과 행 번호는 원문을 직접 포함하지 않지만 **익명화가 아니다**. 원문이 알려진 경우 무염 행 해시를 대조할 수 있으며 원본 접근 범위, 매핑·연결 정보와 결합하면 추론 위험이 커진다. 공개 적합성·추적 목적·보존 기간·접근 범위를 별도로 검토해야 한다. 이 문서에 참조 해시가 있다는 사실이 개인정보·권리나 무조건적 공개 승인을 의미하지 않는다.

### 매핑 좌표의 계층 해석

`mapping-preview`의 source/target `layer=base`는 D-6 안에 내장된 D-5 ZIP의 `baseline/records/{table}.jsonl`을 뜻한다. `layer=d5`는 그 D-5 ZIP의 `d5/records/{table}.jsonl`, `layer=d6`은 D-6 ZIP의 `d6/records/{table}.jsonl`이다. `row`는 해당 JSONL에서 1부터 세는 원본 행 번호다. 기존 registry의 전통 참조는 `target_table=authority_registries`, `target_field=tradition_id`를 가리키며 registry 행의 자체 `id`와 구별한다. 어느 좌표도 새로운 공동체나 DB 레코드의 생성·승격을 뜻하지 않는다.
