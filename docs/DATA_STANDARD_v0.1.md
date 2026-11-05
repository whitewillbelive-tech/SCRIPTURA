# SCRIPTURA 데이터 표준 제안 v0.1

상태: **초안(DRAFT)**. 1차 구현 및 자료 실증에서 검증한 뒤 v1.0으로 승격한다.

## 1. 데이터 계층과 필수 ID

- `corpus`: 성경, 꾸란, 미드라시 등 개별 문헌 집합. 장절 체계의 강제 공유를 금지한다.
- `work`: '이사야서' 같은 추상적 저작/책. 판본과 구별한다.
- `reference_scheme`: 정경·장절·절 번호 체계를 명시한다(예: OSIS 관례에 기초한 특정 체계). 다른 체계와 동일하다고 추정하지 않는다.
- `passage`: `reference_scheme + work + reference` 조합으로 식별한다. 범위, 복합 구절, 단어·절·문단 단위는 `granularity`로 표현한다.
- `passage_alignment`: 두 주소의 대응(동등/부분중복/불확실)과 그것을 검증한 출처를 가진다. 자동 변환 성공은 의미 동일성을 보증하지 않는다.
- `text_edition`: 특정 원문 판본/번역본. 별도의 사용 권리와 라이선스가 적용된다.
- `tradition`: 유대교, 가톨릭, 정교회, 개신교 등 종교·학파·교단의 계층형 분류. 다중/모호한 분류를 허용한다.
- `agent`: 개인 또는 기관(출판사·교단 기관·학술단체). 이름과 실제 주장자를 구분한다.
- `affiliation`: 개인/기관과 전통의 연결. 날짜, 관련 역할, 근거 출처를 저장한다. 소속 ≠ 공식 교리 채택이다.
- `source`: 출판물, 논문, 영상, 공식 문서. DOI/URL, 서지, 권리 상태, 콘텐츠 정책을 저장한다.
- `source_locator`: 원본의 특정 위치(쪽수, 장/절, 문단, 타임스탬프). 인용과 주장의 정확한 검증 기준이다.
- `claim`: 한 가지 검증 가능한 주장을 나타내는 논증 노드. 의견의 진위와 입장 정보를 별도로 저장한다.
- `claim_version`: 주장 설명을 수정할 때 버전을 추가한다. 과거 판본을 덮어쓰지 않는다.
- `claim_attribution`: 해당 주장을 **누가, 무슨 자격으로 했는지** 기록. `official_doctrine`, `institutional_statement`, `scholarly_interpretation`, `individual_opinion`, `reported_view`를 구분한다.
- `claim_evidence`: 주장과 근거 자료 또는 구절을 연결한다. 논거/반례/인용/해석 대상으로 구분하며 정밀 출처를 명시한다.
- `claim_relation`: 두 주장 간 지지·모순·한정·반박·역사적 영향 등을 구분한다. 방향이 중요하다.
- `passage_relation`: 구절 간 인용·암시·주제적 평행·논쟁적인 연관 등을 분리한다.
- `review_event`: 주장 버전 검증/반려/수정 요구와 검수자·근거를 남긴다.
- `provenance_event`: 도입/가공/생성/검수 등 과정에 대해 입력 자료·도구·모델 버전·시점을 남긴다 (W3C PROV-O 개념 참고).
- `ai_assessment`: 특정 질문·데이터 스냅샷·판정 기준·사용 출처를 근거로 하는 AI의 일시적 평가 결과. 원천 주장으로 승격하지 않는다.

## 2. ID와 참조 규칙

- 데이터베이스 기본키는 불변의 내부 ID를 사용한다(예: `clm:...`, `src:...`, `psg:...`). 화면 표시 주소는 변경 가능한 별도 속성이다.
- OSIS(예: `Isa.7.14`)는 `reference_scheme`이 명시된 경우에만 외부 표기로 허용한다. **OSIS ID 하나만으로 판본·정경·장절 체계의 혼란을 해결할 수 없다**.
- 장절 번호가 어긋나거나 합쳐지는 경우 `passage_alignment`에 다대다 대응 및 `confidence`/`status`를 둔다.
- 절 범위와 단어 범위는 `work` + 명시적 주소 표현으로 저장하고, 검색 정규화 결과는 별도 테이블에 저장한다(1차 구현에서는 일반 절 단위만 사용자에게 노출 가능).
- 권·장·절이 없는 문헌에도 `passage`를 부여할 수 있어야 한다.

## 3. 주장·귀속·의미 구분

- 하나의 `claim_version.statement`는 단일 핵심 주장만 포함한다. 긴 주석은 분해하며 원문의 뉘앙스 보존을 위해 원본 위치를 남긴다.
- `claim_attribution`은 추론하지 않는다. 공식 교리로 등록하려면 기관의 공식 문헌/결의 등 명확한 근거가 필요하다.
- `official_doctrine`: 해당 기관이 공식적으로 채택한 것으로 확인.
- `institutional_statement`: 공식 채널의 견해이나 교리화 여부 미확정.
- `scholarly_interpretation`: 저자의 연구 견해. 소속 학파 전체의 견해로 일반화 금지.
- `individual_opinion`: 개인의 주장. 개인의 종교/교단 소속과 분리.
- `reported_view`: 외부인의 서술(오해·왜곡 가능). 직접 주장으로 승격 불가.
- 현재의 교단적 판단과 과거 문헌의 역사적 맥락을 함께 저장한다.

## 4. 출처·저작권 상태

- `source.storage_policy`: `metadata_only | link_only | snippet_only | full_text_allowed`.
- `source.license_status`: `verified | pending_review | restricted | unknown`.
- `source.license_identifier`, `license_url`, `rights_holder`, `access_checked_at`, `retention_limit_days`, `attribution_notice`를 관리한다.
- `source_locator`에는 정확한 위치를 입력한다. 원본 확인 전 인용 확인 상태는 `unverified`로 표시한다.
- 직접 인용은 원본과 대조된 텍스트만 사용한다. 권리 불명/제한 자료는 재현 가능한 서지·주소 메타데이터만 저장한다.
- 임베딩 생성·장기 캐시도 자료원 권리 확인 대상이다. 저장이 불가하면 검색은 메타데이터 수준으로 제한한다.

## 5. 지식 그래프 관계

`claim_relation.relation_type`의 초안:

- `supports`: A가 B에 논증적으로 도움을 줌
- `contradicts`: A와 B가 동일한 질문·조건에서 양립 불가
- `qualifies`: A가 B의 범위를 한정함
- `rebuts`: A가 B를 명시적으로 반박함
- `depends_on`: A가 B를 전제함
- `historically_influenced_by`: A가 B의 문헌/전통으로부터 영향받음 (추정 불가, 사료 필요)

`passage_relation.relation_type`의 초안:

- `quotes`: 직접 인용/언급
- `alludes_to`: 암시/간접 언급
- `parallel`: 장르적·서사적·언어적 평행
- `interpretively_linked`: 해석자에 의해 연결됨 (누가 연결했는지 필수)

**각 관계는 출처 위치·검증 상태가 있어야 하며 단순 유사도는 정식 관계가 아니다.**

## 6. 절차별 검수

1. `imported`: 후보 원본/메타데이터 입수 (수집 권리 확인)
2. `extracted`: AI나 사람이 단일 주장을 추출 (검수 전)
3. `source_verified`: 원문의 주장·정확한 위치·귀속·인용 검증 완료
4. `scholarly_reviewed`: 논증/해석 전통/반론에 대한 내용 검토 완료
5. `disputed`: 직접 출처가 상충하거나 귀속/번역/연결에 쟁점 존재
6. `retired`: 이전 버전이나 부정확한 레코드. 기록 보존하되 기본 검색 제외

`source_verified`는 **주장이 진실임을 뜻하지 않고 그 출처의 주장을 정확히 기록했다는 뜻**이다.

## 7. AI 평가(정답 판단) 계약

AI 응답은 다음을 포함한다.

- 사용자 질문과 판정 모드: 역사언어학 / 본문비평 / 정경적 / 선택 교단 교리 / 논리 비판 / 혼합(명시)
- 연구 기준과 해석의 전제(사용자 선택 또는 모델이 명확히 밝힘)
- 각 주장에 대한 근거/반례, 개별 본문·출처 위치 링크
- 논증의 취약점, 전통 간 차이, 미확인 쟁점
- 직접 확인된 사실과 모델 추론의 명확한 분리
- 결론: `better_supported | conditional | contested | insufficient_evidence` 중 하나(정량 점수는 보류)
- 질문에 답하는 데 사용한 데이터 스냅샷과 모델 버전

기본 답변 모드는 **역사·언어·자료의 검증 가능한 의미**를 중심으로 하고, 특정 신앙 전제의 교리적 결론은 별도 모드로 제시한다. AI 평가는 `ai_assessment`에만 저장하고 원본 기록을 덮어쓰지 않는다.

## 8. 시범 입력의 합격 요건

- 최소 두 개의 다른 전통/연구자 관점이 **실제로 원문으로 확인**되어야 한다.
- 해석마다 저자/기관·출처·정확 위치·서지 식별정보·원본 권리 상태가 있어야 한다.
- 구절 연결과 반론의 관계 유형이 명시되어야 한다.
- 본문 체계 및 번역·판본의 차이를 숨기지 않는다.
- AI가 검증되지 않은 주장에 근거하여 확정적인 학술 판정을 내리지 않도록 해야 한다.
