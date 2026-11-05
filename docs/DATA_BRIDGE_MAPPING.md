# D-2 → S-1B.2 데이터 브리지 매핑 검토

기준은 읽기 전용 동결본 `SCRIPTURA-D11-D2-20261105-v1`이다. ZIP SHA-256은 `c8b64b9144367a8526c77b121b3343f04a7c683276f9fd239b2cc51458589a47`, 내부 manifest에는 65개의 해시 대상 파일이 있다. 이 문서는 D-2 자료를 현행 주 데이터베이스에 적재하거나, 자료의 저작권·사실성·독립 학술 검수를 승인하지 않는다. 연구 ZIP 및 실제 행은 저장소에 포함하지 않는다. D-3는 아직 접수하지 않았다.

아래 표의 001~003은 기존 `db/001_schema.sql`, `db/002_append_only.sql`, `db/003_research_integrity.sql`을 뜻한다. 오른쪽은 **가능한 개념 대응과 차이**이지 주 DB에 대한 실행 매핑이나 승인 지시가 아니다. 원본 ID·필드·상태·관계를 그대로 보존하고 변환 근거가 없는 항목은 격리한다. 결측값에 빈 문자열이나 추정한 정경·판본·귀속을 넣지 않는다.

| D-2 JSONL (행 수) | 001~003 대상과 무손실 여부 | 보류 또는 별도 검토가 필요한 이유 |
|---|---|---|
| sources (96) | `sources`: `id`, `title`, `creator`, `url`→`source_url`, `doi` 등은 개념상 대응. D-2 `kind`의 상세 유형은 `source_kind` enum과 1:1이 아니다. 001의 정규화 없는 `lower(doi)` 유일 인덱스만으로 DOI URL 접두어 등 중복을 모두 판별할 수 없다. 003 `data_class` 기본값은 `unclassified`. | 포털·표준·자료 등록부와 논문을 모두 학술 논문으로 바꾸지 않는다. 자료원 96개는 논문 96개가 아니다. 기존 필드에 없는 수집 범위·발견·출처 식별·메타데이터 provenance를 버리거나 저작권 상태를 만들어내지 않는다. |
| editions (97) | `text_editions`: `id`, `source_id`, `label`→`edition_label`, `language`→`language_code`는 대응 가능하나 001은 `work_id`, `corpus_id`, `witness_or_translation`을 필수로 요구한다. D-2 `version_status`(confirmed/partial/unknown)에는 직접 대응 열이 없다. | 문헌 판본이 경전 판본과 반드시 같지 않다. 누락된 work/corpus/종류·판본을 가짜로 만들지 않는다. 판본 상태와 버전·식별·권리 범위를 보존한다. 현재 82 partial, 11 unknown, 4 confirmed. |
| locators (131) | `source_locators`: D-2 `edition_id`→`text_editions`→`source_id` 경로를 풀어야 한다. `location`→`locator_value` 가능성이 있으나 001의 필수 `locator_type` 및 확인 방식의 대응이 별도 문제다. 001은 checked/unverified/disputed이고 D-2는 source_checked/edition_checked/unchecked/disputed다. | source_checked와 edition_checked의 검증 범위를 단일 checked로 합쳐버리면 손실이다. 판본·언어·날짜·위치·검사 방법·직접/간접 경로를 보존하고 불확실한 경우 보류한다. 003의 verified 관계는 checked, 검증 날짜, 비어 있지 않은 위치를 요구한다. |
| rights (873) | 기존 `sources.storage_policy`와 `license_status`는 자료원별 단일 값이며 판본 × 9행위 × 목적·지역·기간의 개별 결정을 표현하지 못한다. | action별 원 결정·조건·증거 URL·확인 시점·범위를 따로 보존한다. unknown/conditional을 허가 또는 boolean true로 변환하지 않는다. URL만으로 권리를 입증했다고 보지 않는다. `allowed`도 해당 판본·행위·조건에만 적용된다. |
| passages (75) | D-2의 `corpus`, `work`, `reference_scheme`, `reference` 문자열은 001에서 `corpora`, `works`, `reference_schemes` FK와 `external_ref`, 필수 `granularity`로 표현한다. work 및 scheme은 같은 corpus를 참조해야 한다. | 문자열에서 실제 정경·책·절 체계 ID와 granularity를 추측하지 않는다. 판본 포함·부재 및 coverage/segment 범위를 구별한다. 일치가 확정되지 않은 것은 격리한다. |
| alignments (35) | D-2 `from_passage_id`, `to_passage_id`는 001의 passage FK에 대응한다. D-2 `equivalent_segment`, `addition`, `omission`은 001 `alignment_type` enum(equivalent/overlapping/partial/uncertain)에 없고, `partial_pending` 역시 001 review_status enum에 없다. | 한쪽에 추가·누락된 범위, 검증 범위와 근거를 보존한다. `equivalent_segment`를 정경·신학적 동일성이나 양방향 전면 동등성으로 바꾸지 않는다. 35건 모두 `partial_pending`이며 양쪽 판본 대조가 확정된 것은 아니다. |
| agents (24) | `agents.id`, `name`→`display_name`은 개념 대응. 001 `agent_kind`는 person/institution/collective만 허용하며 D-2 `literary_voice`가 없다. | 문학적 화자를 역사적 개인이나 공식 기관으로 강제 변환하지 않는다. 문학적 화자와 관련 주장 1건은 표현 확장 또는 격리한다. |
| affiliations (0) | 001 `agent_affiliations`에는 `agent_id`, `tradition_id`, `relation_type`, 출처 locator가 필요하다. D-2는 소속 문자열과 locator를 사용한다. | 원본에 실제 소속 행이 없다. 소속이나 교단 전체의 공식 견해를 저자명·출판처로부터 추론하지 않는다. 전통 식별 및 근거 확인 전 격리한다. |
| claims (30) | 001은 하나의 D-2 claim을 `claims` + `claim_versions` + `claim_attributions` + 다수 `claim_passages`로 나눠야 하며 각 행 ID·개정 사유·추출 방식·FK 등이 필요하다. 001은 `candidate`, `textual_narrative`, `community_explanation`, `external_criticism`을 같은 의미로 직접 표현하지 못한다. | 하위 ID·revision·발화 주체·근거를 임의 생성하거나 원본 statement를 빈 문자열로 채우지 않는다. 공식 교리는 별도 official basis locator를 필요로 한다. `source_verified` 26건은 출처 대조 상태이며 `scholarly_reviewed` 0건을 사람의 독립 심사 완료로 둔갑시키지 않는다. |
| evidence (30) | 001 `claim_evidence`는 claim **version** FK, `evidence_role`, `explanation`, locator/passage/related-claim 중 적어도 하나를 요구한다. 원본 `claim_id`와 locator/role/status를 version으로 연결하려면 명시적인 버전 매핑이 필요하다. | 인용 위치와 검증 범위가 빠지지 않게 보존한다. 003에서 verified evidence는 확인 날짜와 위치가 있는 checked locator를 필요로 한다. 원문 없이 출처 확인이라고 확정하지 않는다. |
| relations (2) | `claim_relations`는 양쪽 claim **version** FK와 `relation_type`, locator, status, rationale을 요구한다. 원본 claim ID를 version ID로 자동 치환할 수 없다. | 출처 미확인 관계를 verified로 승격하지 않는다. 서지의 인용 관계는 저자의 해석 주장에 대한 supports/rebuts 관계와 다르다. 검증된 관계도 출처 범위 및 전언 한계를 함께 보존한다. |
| reviews (32) | 001 `review_events`는 `reviewer_agent_id` FK와 `approve_source`/`approve_scholarly` 등의 decision enum 및 rationale을 요구하고 002는 변경·삭제·TRUNCATE를 금지한다. D-2 reviewer·decision·시간·목적·독립성은 동등하게 직렬화되지 않는다. | 사건 ID·원 시각·검수자 표기·목적·방법을 보존한다. 문자열 reviewer를 임의의 실명 계정으로 만들지 않으며, source review를 approve_scholarly로 변환하지 않는다. 독립 인간 심사의 진정성은 별도 절차로 확인한다. |

## 권리 판단: 판본 × 행위 × 목적·지역·기간

D-2의 9개 행위는 `browse`, `collect_metadata`, `store_raw`, `store_excerpt`, `index_fulltext`, `embed`, `send_to_model`, `redistribute`, `public_link`이다. 판본마다 별도 행이 있고, 행위 사이에 권리가 전파되지 않는다. 특히 다음 7개는 각각 독립하여 검사한다.

| 행위 | 보수적 기본값 | D-2 관찰 |
|---|---|---|
| `store_raw` | 명시적 허가와 적용 조건이 증명되지 않으면 거부 | allowed 0 / 97 |
| `store_excerpt` | 동일 | allowed 0 / 97 |
| `index_fulltext` | 동일 | allowed 0 / 97 |
| `embed` | 동일 | allowed 0 / 97 |
| `send_to_model` | 동일 | allowed 0 / 97 |
| `redistribute` | 동일 | allowed 0 / 97 |
| `public_link` | 동일 | allowed 0 / 97 |

`browse`와 `collect_metadata`는 각각 97개 판본 중 2개만 `allowed`다. 전체 873개 결정 중 unknown 823, conditional 46, allowed 4이며 조건부는 무조건 허가가 아니다. 같은 판본의 browse 허가나 일반 라이선스 확인은 저장·색인·임베딩·모델 전송·재배포·공개 링크 권한을 만들어내지 않는다. 실제 원문 취득·저장·모델 전송을 이 단계에서 수행하지 않는다. 구조화된 연구 메타데이터의 취급도 별도 권리 판단을 대신하지 않는다.

## 현재 staging 표현의 한계

현재 준비 중인 `scriptura_d2_stage`는 원본 전문이나 JSON payload를 저장하지 않는 격리 인덱스다. snapshot·원본 ZIP/파일 해시·파일/행·ID·검증 상태·격리 사유와 권리 행의 판본/action/decision을 보존한다. 나머지 선택 필드와 권리 조건·증거의 전체 복원은 이 인덱스만으로 할 수 없으며 동결된 원본 ZIP이 필요하다. 따라서 staging 인덱스를 무손실 원본 저장소나 이용권 부여 근거로 취급하지 않고 정규 주 DB에 자동 투영하지 않는다. 저작권·정확성의 독립 검증과 실제 자료 저장은 이 단계 범위가 아니다.

## 무결성·출처·격리 기준

1. 입력 ZIP 및 내부 manifest의 경로·크기·해시와 12개 JSONL의 행 수, ID 유일성·참조를 검사한다. D-1.1 정정본과 D-2 delta의 합집합이 merged와 일치해야 한다. 부정 데이터 및 오류 보고서에는 원문이나 전체 실제 레코드를 출력하지 않는다.
2. 데이터 원본의 ID, snapshot, 원래 ZIP 및 파일 해시, origin 파일과 행 번호, 원 상태, 행위별 권리 결정을 보존한다. 무손실 대응이 없거나 미승인·미확인인 항목은 확정형 주 DB가 아닌 격리에 남긴다.
3. 동일 snapshot·동일 내용의 재실행은 중복 없는 재현 결과여야 한다. 같은 snapshot의 내용이 달라지거나 ID 충돌이 있으면 실패하고 별도 새 snapshot 또는 검토를 요구한다. 실제 D-2에 대해서는 로컬 검증 및 dry-run만 수행한다.
4. `source_verified`는 출처 기록의 정확성에 대한 상태이고 `scholarly_reviewed`는 별도 독립적 인간 심사 상태다. 데이터 자체에 문자열이 있다는 사실만으로 심사의 실제 독립성·권리 허가·학술적 진실을 보장할 수 없다.
5. 격리 시험 적재는 운영 DB와 분리된 사전 생성 임시 DB, `scriptura_staging_` 이름, loopback, 명시적 승인 환경과 제한 DB 권한을 충족해야 한다. 인증·동시성·저작권 판별은 각 독립 통제와 사람의 검토가 필요하다.

## D-3 인계와 Gate I-1

Work D-3는 별도 연구 트랙이다. 이 브리지는 D-3 결과를 예측하거나 자동 수집·병합하지 않는다. 후속 인계 시 (1) 새 snapshot 식별자·계약 버전·생성 시각과 부모 D-2 해시를 제시하고 원본 파일 및 manifest의 경로/크기/해시를 고정한다. (2) 생산자와 수신자가 JSONL 종류·필드/enum·FK·권리 action·상태 의미·이전 버전과의 추가/삭제/변경 및 도구의 지원 버전을 대조해 호환성을 협상한다. 호환되지 않거나 미확인인 변경은 중단 또는 격리하며 기본값으로 채우지 않는다. (3) 별도 환경의 수신 검증, 권리·판본·주소·귀속·관계·리뷰 이력과 합성/실자료 분리, 중복·변조·재실행 검사를 실시한다. (4) 자료권리와 독립 학술 검수를 사람이 수행하고 출처 확인과 학술 심사를 따로 기록한다. (5) 관리 Chat의 Gate I-1 수용 결정을 기다린다. 이 절차가 자동 승격, 기존 DB 이식, 기존 브랜치 병합이나 운영 공개를 허가하지 않는다.
