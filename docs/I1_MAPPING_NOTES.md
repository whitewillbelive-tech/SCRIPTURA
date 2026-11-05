# Gate I-1: D-3 데이터와 현행 스키마의 대응 검토

## 기준과 범위

읽기 전용 D-3 입력 ZIP의 SHA-256은 `baf206d2846544f1e1bb20622ac10c557394b71aa41cfd6e2be5bbafade347be`다. 내부 `logs/FILE_SHA256SUMS.txt`의 69개 파일은 해시가 일치하고 미목록 파일이 없었다. 첨부된 D-2 기준 ZIP의 SHA-256은 `c8b64b9144367a8526c77b121b3343f04a7c683276f9fd239b2cc51458589a47`과 같았다. 열두 종류 모두 D-2 기준 원본이 보존됐고, D-2 기준 + D-3 delta가 D-3 merged와 레코드 단위로 같았다. 이는 구조 및 바이트 무결성 검사이며, 자료의 역사적 사실·독립 학술 검수·이용권을 승인하지 않는다.

D-3은 12종 merged 데이터 외에 **서지 인용 그래프 11행**과 **정경 목록 비교·보유 범위 80행**을 별도 산출한다. 신규 14종의 의미를 기존 12종의 claim 논증 그래프로 합치면 안 된다. D-4 내용은 추정하거나 반영하지 않았다. 실제 ZIP과 연구 원문은 공개 저장소에 포함하지 않는다.

## 12종과 PostgreSQL 001–003

| 종류 | 기준 → 증분 → 병합 | 기존 대응·차이 및 격리 원칙 |
|---|---:|---|
| sources | 96 → 84 → 180 | `sources`의 `source_kind`, 제목·제작자·URL·DOI는 개념상 대응한다. D-3의 자료원 종류·서지 출처·수집 범위·신원 확인·상충 기록은 단일 enum과 메타데이터만으로 무손실 변환되지 않는다. 포털·표준·서지 레코드를 모두 독립 학술 논문으로 취급하지 않는다. |
| editions | 97 → 85 → 182 | `text_editions`는 `work_id`, `corpus_id`, `witness_or_translation` 등을 요구하지만 D-3 자료원 판본에 이들을 안전하게 지정할 근거가 부족하다. 판본 상태는 partial 165, unknown 11, confirmed 6이며 확인된 범위를 임의 확대하지 않는다. |
| locators | 131 → 95 → 226 | edition을 통해 source를 찾아야 하는데, 기존 `source_locators`는 source ID와 locator 유형을 요구한다. `source_checked` 177, `edition_checked` 24, `unchecked` 25를 단일 checked 상태로 뭉개지 않고 판본·위치·검사 범위를 보존한다. |
| rights | 873 → 765 → 1,638 | 182개 판본 × 9개 행위의 결정은 `sources.storage_policy`/`license_status` 단일 값에 무손실 대응하지 않는다. 원본 결정·범위·검수 상태를 독립 보존하고 권리가 불확실하면 거부한다. |
| passages | 75 → 4 → 79 | 문자열 corpus/work/reference scheme/reference는 기존의 corpus/work/scheme 외래키와 granularity로 자동 확정할 수 없다. 76행은 scheme 상태가 명시되지 않고 3행은 partial이다. 표기 차이나 대소문자 유사성만으로 동일 정경·판본·주소를 만들지 않는다. |
| alignments | 35 → 4 → 39 | `equivalent_segment` 32, `partial` 6, `addition` 1은 기존 enum과 일치하지 않는다. 원본 상태는 partial_pending 35, verified 4다. verified는 원본이 주장하는 확인 수준을 보존할 뿐 모든 방향·판본·신학적 동일성을 보증하지 않는다. 추가분·위치·출처와 양방향 범위를 각각 검토한다. |
| agents | 24 → 8 → 32 | 기존 enum은 person/institution/collective만 허용하고 literary_voice를 허용하지 않는다. 현재 원본의 문학적 화자 1명을 개인이나 교단 기관으로 강제 변환하지 않는다. |
| affiliations | 0 → 12 → 12 | 기존 `agent_affiliations`는 tradition ID와 별도 relation enum·기간·출처 FK가 필요하다. D-3은 verified 8, candidate 4이며 tradition 문자열과 시대 구분은 별도 식별·근거 검증이 필요하다. 개인 소속은 해당 전통의 공식 교리가 아니다. |
| claims | 30 → 10 → 40 | D-3 claim ID는 기존 `claims`·`claim_versions`·`claim_attributions`·`claim_passages`에 일대일 자동 대응하지 않는다. `claim_id`를 `claim_version_id`로 치환하거나 버전·귀속·공식 교리를 추측하지 않는다. 원본 상태는 source_verified 36, candidate 4, scholarly_reviewed 0이다. |
| evidence | 30 → 10 → 40 | 기존 `claim_evidence`는 claim **version** FK 및 출처 위치·검증 상태를 요구한다. D-3 claim ID와 버전 연결을 지정하지 않은 상태에서 그 근거를 임의 이전하지 않는다. |
| relations | 2 → 0 → 2 | 기존 `claim_relations`는 양쪽 claim **version** FK를 요구한다. 두 행은 별도 원본 상태와 locator를 보존하고, 서지 인용을 해석 지지·반박·영향으로 추론하지 않는다. |
| reviews | 32 → 26 → 58 | 원본의 review 이벤트는 source_verified 52, candidate 6이다. 이력 이벤트 수는 현재 claim 상태의 건수와 다르며 대체할 수 없다. reviewer 문자열을 계정 ID나 독립 인간 검증 사실로 임의 확정하지 않는다. |

기존 `003`의 source_verified와 scholarly_reviewed는 별도 단계다. 출처 대조 상태는 저작물에 기술된 주장의 정확성에 관한 것이며 주장의 진실, 권리 허가 또는 독립적 인간 학술 심사 완료를 뜻하지 않는다.

## 추가 서지 인용 그래프 11행

`d3/graph/bibliographic_edges.jsonl`은 자료원 A에서 자료원 B를 향하는 **서지 인용**과 A 판본의 locator를 나타낸다. 11행 중 원본 상태는 source_checked 7, partial_pending 4다. 원본상 source_checked 7건 중 2건은 간선 자체의 checked_at이 없어 이를 채워 넣지 않고 별도 보류한다. 구조 검증에서 양쪽 source FK, locator와 그 edition이 A source에 속하는지 확인했고 불일치는 발견하지 않았다. 이는 대상 서지의 식별 또는 해석학적 관계에 대한 독립 확증이 아니다. 기존 `claim_relations`의 claim-version FK와 논증 enum에 들어갈 수 없으며 `supports`, `rebuts`, `historically_influenced_by` 같은 관계로 변환하지 않는다. 서지 간선의 ID·출처 위치·검증 상태·전언 또는 불확실 범위를 별도로 추적한다.

## 추가 정경 커버리지 80행

`d3/coverage/CANON_COVERAGE_D3_FINAL.jsonl`은 판본의 절별 동일성이 아니라 기관별 **목록 비교 단위**다. 기존 corpus/work/verse 및 `passage_alignments`의 확정 레코드로 승격하지 않는다. 80행 중 D-3 주소 보유 범위는 partial 13, not_recorded 67이다. 원본에서 대응된 본문 레코드 합 79, claim 연결 합 41은 중복될 수 있는 연결 횟수이므로 41개의 독립 주장이나 본문 전체의 완전 검증을 뜻하지 않는다.

목록별 원본 상태의 집계는 OPC/WCF listed 66·not_in_66_list 14, USCCB listed 73·included_within_book 2·not_in_usccb_73_list 5, Chabad listed 39·outside_tanakh_corpus 27·not_in_chabad_24_list 14다. OCA 관련 11행은 해당 기관 설명에 포함된 범위, 69행은 not_checked다. 각각의 기관·목록별 표현을 유지하며 전체 교파·정교회 전체·모든 판본의 폐쇄 목록으로 일반화하지 않는다.

## 원본 자료원 종류 집계

| 원본 `kind` | 개수 | 원본 `kind` | 개수 |
|---|---:|---|---:|
| platform_or_resource_registry_candidate | 20 | bible_translation | 5 |
| reference_work | 1 | document | 3 |
| commentary | 22 | official_document | 2 |
| homily | 2 | article | 1 |
| scholarly_article | 61 | scholarly_chapter | 2 |
| dataset | 1 | dataset_documentation | 1 |
| translation | 1 | scholarly_bibliographic_record | 44 |
| historical_theological_work | 2 | web_comment | 1 |
| biographical_or_institutional_statement | 11 | 합계 | 180 |

이는 원본 라벨의 단순 집계이며 해당 기록이 독립적으로 학술 심사됐거나 논문의 내용을 입수·검증했다는 판정이 아니다.

## DOI·권리·격리 기록

D-3 merged의 DOI 값은 정규화 기준 108개이고 중복은 0이다. 입력 자체는 새 DOI 64개 중 6개에 확인된 locator가 없다고 구분한다. 108개 중 원본 metadata_status는 source_checked 16, search_result_only 4, 미기재 88이다. 이는 입력의 표시값이며 DOI 존재·유일성 또는 날짜만으로 출처 대조, 실제 문헌의 접근권 또는 학술 검증을 입증하지 않는다.

각 판본의 `browse`, `collect_metadata`, `store_raw`, `store_excerpt`, `index_fulltext`, `embed`, `send_to_model`, `redistribute`, `public_link`는 독립적이다. 전체 원본 결정 1,638개는 unknown 1,588·conditional 46·allowed 4로, allowed는 browse·collect_metadata에만 있다. 어느 행위도 다른 행위의 허가로 확장하지 않는다. 원문·발췌·인덱스·임베딩·모델 전송·재배포·공개 링크는 별도 권리 검토 전 모두 차단한다.

004는 전용 합성 시험용 격리 인덱스이며 12개 D-2 테이블과 `d2/records_merged/` 경로만 허용한다. D-3의 `d3/records_merged/` 경로·서지 간선·정경 보조표를 강제 축약해 넣을 수 없다. 실제 D-3은 읽기 전용으로만 검증하며 PostgreSQL 쓰기 시험은 합성 자료로만 한다. 분류가 불가능하거나 스키마·권리·검수 조건이 충족되지 않은 항목은 누락이나 추측 없이 `quarantined`로 보고한다. 원본 ID를 추적할 수 있도록 신뢰된 비공개 원본 ZIP에 남기고, 공개 저장소의 산출물은 원본 ID나 원문 대신 파일 경로·행 번호·원본 파일/행 해시 및 사유를 사용한다. 004에 저장된 일부 인덱스 메타데이터만으로는 입력 레코드를 무손실 재구성하지 못한다.

D-3 표와 실제 출처 이용은 별도 사람의 권리·판본·귀속 검토와 명시적 수용에 달려 있다. 운영 DB 반영, main 병합, 공개 서비스, D-4 수집 결과의 자동 통합은 이 문서가 승인하지 않는다.
