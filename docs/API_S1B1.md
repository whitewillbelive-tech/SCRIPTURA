# S-1B.1 API 및 데이터 분리

이 구현은 로컬 연구 시범용이다. 실서비스 사용자 인증, 접근 통제, 속도 제한 및 운영 보안 검토는 완료되지 않았다. 합성 자료는 실제 학술 자료가 아니며 실제 검증 결과가 아니다. `source_verified`는 출처와 귀속을 확인했다는 뜻이며 주장의 진실이나 신학적 판정을 의미하지 않는다.

## 실행 환경

Node.js 24, PostgreSQL 15 이상. 기존 시스템 DB가 아닌 독립 SCRIPTURA DB에 `db/001_schema.sql`, `db/002_append_only.sql`, `db/003_research_integrity.sql`을 차례로 적용한다. 전용 DB에서는 `psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f db/001_schema.sql`과 같은 방식으로 각 파일을 실행한다. 실제 자료는 포함하지 않으며 자동 수집도 하지 않는다. 마이그레이션 및 롤백 상세는 DB 문서를 따른다.

| 변수 | 용도 |
| --- | --- |
| `DATABASE_URL` | 연구 API의 읽기 전용 PostgreSQL 역할 연결 문자열 |
| `SCRIPTURA_REVIEW_DATABASE_URL` | 같은 데이터베이스의 별도 승인 전용 역할 연결 문자열 |
| `SCRIPTURA_ADMIN_TOKEN` | 관리자 Bearer 토큰. PG 관리자 API는 UTF-8 32바이트 미만일 때 거부한다. 암호학적으로 무작위 토큰을 안전하게 생성·관리해야 한다. |
| `SCRIPTURA_REVIEWER_AGENT_ID` | 서버에서 신뢰할 수 있게 지정한 검수자 agent ID. 요청 본문에 입력한 검수자는 허용하지 않는다. |
| `SCRIPTURA_DEMO_DB` | 기존 JSON 합성 데모 관리자 이벤트용 SQLite 파일 경로. 기본 `.local/demo.sqlite`. |

`.env`, DB 비밀번호, 토큰을 커밋하거나 로그에 남기지 않는다. `npm ci` 후 `npm run dev -- --hostname 127.0.0.1`로 로컬에서만 실행한다. `npm run typecheck`, `npm test`는 기존 데모를 검사한다. PG HTTP 통합은 전용 테스트 DB와 임시 schema/역할 생성·삭제 권한을 가진 계정으로 `DATABASE_URL=... node --test tests/pg-api.integration.mjs`를 실행한다. 테스트가 만드는 데이터는 가상의 테스트 자료이며 테스트 후 제거된다.

## 데이터 모드와 조회

기존 JSON fixture는 기본 모드이며 모든 응답이 합성 경고를 포함한다. `?dataset=database`는 연구 DB 중 `scholarly_candidate`, `source_verified`, `scholarly_reviewed`만 조회하고 미분류·합성 레코드를 숨긴다. DB에서 합성 자료를 검증할 때는 `?dataset=database&data_mode=synthetic`을 명시한다. 이때 합성으로 분류된 데이터만 반환하고 합성 경고를 포함한다. 두 모드 모두 미검증 주장은 기본적으로 숨기며 `include_unverified=true`를 명시하면 별도로 볼 수 있다. 합성 주장은 실제 학술 자료로 승격할 수 없다. 미분류 레코드는 격리되어 어느 모드에서도 반환하지 않는다.

`GET /api/v1/corpora`, `traditions`, `agents`, `reference-schemes`, `passages`, `passages/{id}/interpretations`, `passages/{id}/alignments`, `claims/{id}`, `sources/{id}`, `graph?passage_id=...`에서 모드를 지정한다. 본문 검색은 `scheme_id`, `ref`, `work_id`, 주장 검색은 `tradition_id`, `agent_id`, `agent_kind`, `attribution_kind`를 사용할 수 있다. 주장 귀속 종류는 결과에 명시되며 공식 교리와 개인 의견을 동일한 귀속으로 취급하지 않는다. 전통 소속은 출처가 확인된 명시적 소속만 사용하며 소속 자체가 공식 교리를 뜻하지 않는다. DB 검색·그래프 조회는 최대 500건으로 제한된다. 그래프는 한 단계 이웃 주장과 본문 관계, 근거 노드를 포함하며 각 관계의 상태와 위치를 보여준다.

## 검수 및 감사 권한

읽기 role과 승인 role의 사용자 이름은 반드시 달라야 하고 두 URL은 같은 host, port, DB를 가리켜야 한다. 읽기 role에는 schema `USAGE`와 조회 대상 테이블 `SELECT`만 부여한다. 승인 role에는 schema `USAGE`, `scriptura_review_claim(text,text,text,text,text,text)`에 대한 `EXECUTE`, 그리고 관리자 감사 조회에 필요한 `review_events`/`provenance_events` `SELECT`만 부여한다. 승인 role에 테이블 DML을 주지 않는다. 함수 소유자는 신뢰 가능한 non-login 역할이어야 하고 schema `CREATE`를 신뢰할 수 없는 역할에 부여하지 않는다. 별도 관리자 프로세스가 최소 권한 부여를 수행해야 하며, 코드에 DB 비밀번호를 포함하지 않는다.

`POST /api/v1/admin/reviews?dataset=database`에 `Authorization: Bearer …`와 JSON `{ "claim_version_id": "…", "decision": "approve_source", "rationale": "…" }`를 보낸다. `decision`은 `approve_source`, `approve_scholarly`, `request_changes`, `reject`, `mark_disputed`를 허용한다. 리뷰어 ID는 서버 설정에서만 정해진다. 검증된 귀속·근거와 확인된 출처 위치가 없으면 승인은 실패하고 감사 이벤트도 기록되지 않는다. 성공 시 상태 변경과 감사 이벤트는 같은 트랜잭션에서 기록된다. `GET /api/v1/admin/audit?dataset=database&entity_id=...`는 같은 인증과 승인 역할의 감사 SELECT가 필요하다.

정적 공유 토큰은 시범용이며 개별 계정 인증이나 권한 분리, 토큰 회전, 요청 제한, 조직 단위 감사 체계를 대체하지 못한다. 실제 자료 수집 및 원문 저장, 임베딩, 재배포는 구현되지 않았다. 이를 구현하기 전 자료원별 명시적인 권리 승인과 강제 검사를 추가해야 한다.
