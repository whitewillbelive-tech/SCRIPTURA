# SCRIPTURA — Gate S-1B 합성 시범

**합성 데모 / 실제 학술 데이터 아님. 외부 공개 금지.** 이 독립 프로젝트는 첨부된 S-0 초안과 합성 fixture를 이용하는 개발용 시범이다. 실제 문헌 수집, AI 답변, 신학 판정, 운영 배포는 하지 않는다. 원본 `fixtures/demo_valid.json`은 공개 승인되지 않았다. 검증 상태는 출처 검증을 뜻하며 신학적 사실을 판정하지 않는다.

## 실행

Node.js 24, npm 및 Python 3.10 이상이 필요하다. PostgreSQL 검증은 15 이상을 대상으로 한다. 프로젝트 루트에서:

```sh
npm ci
npm run build
npm run start -- --hostname 127.0.0.1 --port 3000
```

개발 중에는 `npm run dev -- --hostname 127.0.0.1 --port 3000`을 사용한다. 개발 서버와 빌드·API 테스트는 `.next`를 공유하므로 동시에 실행하지 않는다. 루프백에서만 사용하고 공개 네트워크에 바인딩하지 않는다. UI 기본값은 검증된 주장만 표시한다. 샘플은 모두 미검증이어서 명시적 토글이 필요하다. fixture에는 주장-전통 소속과 반박이 없으며, 제안된 `qualifies` 관계를 반박으로 바꾸지 않는다.

| 변수 | 용도 | 기본값 |
|---|---|---|
| `SCRIPTURA_ADMIN_TOKEN` | 관리자 API Bearer 토큰. 미설정 시 관리자 API 사용 불가 | 없음 |
| `SCRIPTURA_DEMO_DB` | 관리자 샘플 및 감사 이벤트용 SQLite 파일 경로 | `.local/demo.sqlite` |
| `DATABASE_URL` | 별도 PostgreSQL 테스트 DB 연결 문자열 (`psql` 명령에만 사용) | 없음 |
| `SCRIPTURA_TEST_URL` | 브라우저 테스트 대상 서버 | `http://127.0.0.1:3107` |
| `CHROMIUM_PATH` | 브라우저 테스트용 Chromium 실행 파일 경로 | Playwright 기본값 |

비밀 값은 환경에만 설정하고 파일이나 Git에 넣지 않는다. 관리자 API는 `Authorization: Bearer <token>`이 필요하다. `POST /api/v1/admin/claims`는 기존 합성 `fixture_version_id`만 받아 샘플을 생성하며, `GET /api/v1/admin/claims`와 `/api/v1/admin/claims/{id}`로 조회한다. `/api/v1/admin/reviews`와 `/api/v1/admin/audit`는 데모 이벤트를 기록·조회한다. 승인 이벤트는 실제 주장의 검증 상태를 변경하지 않는다. 이 단일 토큰과 로컬 SQLite는 운영 인증·계정·PostgreSQL 통합을 대체하지 않는다.

읽기 API는 `/api/v1/passages`, `/api/v1/passages/{id}`, `/api/v1/passages/{id}/interpretations`, `/api/v1/claims/{version_id}`, `/api/v1/graph?passage_id=...`, `/api/v1/traditions`, `/api/v1/sources/{id}` 등을 제공한다. `scheme_id`와 `ref`로 주소를 찾는다. 합성 미검증 예시는 `include_unverified=true`일 때만 반환한다. 외부 원문 저장·임베딩·재배포 기능은 없으며, 관련 정책 함수는 기본 거부 설계다. 실제 기능을 만들 때는 작업별 권한과 저장 정책, 라이선스를 트랜잭션 경계에서 확인해야 한다.

## PostgreSQL 마이그레이션

반드시 새 전용 테스트 DB에서 다음 순서를 사용한다. 롤백은 데이터가 있으면 거부된다. 자세한 제한은 [DB_MIGRATION_NOTES.md](docs/DB_MIGRATION_NOTES.md)를 참조한다.

```sh
psql -X -v ON_ERROR_STOP=1 "$DATABASE_URL" -f db/001_schema.sql
psql -X -v ON_ERROR_STOP=1 "$DATABASE_URL" -f db/002_append_only.sql
psql -X -v ON_ERROR_STOP=1 "$DATABASE_URL" -f tests/database.sql
# 쓰기를 중단하고, 빈 테스트 DB에서만 역순 실행
psql -X -v ON_ERROR_STOP=1 "$DATABASE_URL" -f db/002_append_only.down.sql
psql -X -v ON_ERROR_STOP=1 "$DATABASE_URL" -f db/001_schema.down.sql
```

## 검증

```sh
python3 scripts/validate_fixture.py fixtures/demo_valid.json
python3 -m unittest discover -s tests -v
npm test
```

`npm test`는 임시 DB와 루프백 서버를 사용한다. 브라우저 검증은 Playwright와 Chromium이 별도로 필요하다. 테스트 서버를 3107번 포트에서 실행한 후 `node --test tests/ui.browser.cjs`를 실행한다. 환경별 결과와 Gate 판정은 [S1B_REPORT.md](docs/S1B_REPORT.md)에 기록한다. 첨부의 문서는 시작 시점 초안으로 보존했다.

## S-1B.1 PostgreSQL 탐색

`/explore`에서 명시적으로 연구 자료 또는 합성 자료를 선택해 검색한다. PostgreSQL 설정, 마이그레이션, 별도 읽기·검수 역할과 관리자 API는 [S-1B.1 API 안내](docs/API_S1B1.md)와 [DB 보안 안내](docs/DB_S1B1.md)를 참조한다. 이는 개발 및 검증용 구현으로 개인별 운영 인증을 제공하지 않는다. Work의 S-1A 연구 ZIP은 이번 작업에 제공되지 않아 실제 자료와 제안은 통합되지 않았다.

## S-1B.2 D-2 수신 검증

D-2 동결 ZIP은 저장소에 포함하지 않는다. 원본을 변경하지 않는 검증과 적재 계획은 다음과 같이 실행한다. 출력 파일이 이미 있으면 덮어쓰지 않는다.

```sh
python3 scripts/d2_bridge_cli.py validate /path/to/SCRIPTURA_D11_D2_RESEARCH.zip
python3 scripts/d2_bridge_cli.py dry-run /path/to/SCRIPTURA_D11_D2_RESEARCH.zip --output /path/to/new-report.json
```

실제 D-2 입력은 로컬 dry-run만 허용하며 주 DB로 승격하지 않는다. `scripts/stage_synthetic.py`는 외부 ZIP을 받지 않고 내부 합성 자료만 생성한다. 전용 임시 DB·분리 역할·명시적 시험 승인과 로컬 연결이 필요하며, [스테이징 안내](docs/STAGING_SCHEMA.md)와 [12종 매핑 검토](docs/DATA_BRIDGE_MAPPING.md)를 참조한다. 원문 및 임의 자유 텍스트의 저작권을 자동 판정하지 않는다.

## Gate I-1 D-3 수신 검사

동결 연구 ZIP은 저장소에 포함하지 않는다. 다음 명령은 정확히 고정된 D-3와 내장 D-2 원본만 읽으며, 정본 DB에 연결하거나 쓰지 않는다. 결과 파일은 새 경로에만 생성하고 기존 파일은 덮어쓰지 않는다.

```sh
python3 scripts/i1_bridge_cli.py validate /path/to/SCRIPTURA_D3_DATA_RESEARCH.zip
python3 scripts/i1_bridge_cli.py dry-run /path/to/SCRIPTURA_D3_DATA_RESEARCH.zip
python3 scripts/i1_bridge_cli.py ingest-preview /path/to/SCRIPTURA_D3_DATA_RESEARCH.zip --output /path/to/new-mapping-report.json --quarantine-output /path/to/new-quarantine-summary.json --private-trace D3_PRIVATE_REVIEW.json
```

공개 가능한 보고서는 집계·행 해시·보류 사유만 담는다. `--private-trace`는 원 ID·참조·파일/행, 원래 검증·권리 상태 및 본문별 비교를 `.local/i1/`에 접근 권한 0600으로 생성한다. 이 파일과 실제 ZIP은 커밋하거나 외부에 배포하지 않는다. 문서 [I-1 매핑 검토](docs/I1_MAPPING_NOTES.md), [합성 스테이징 보호](docs/I1_STAGING_GUARDS.md), [I-1 수신 기록](I1_RECEIPT.md)을 참조한다. 합성/실자료 원문의 임의 자유 텍스트 저작권 판별이나 사람의 독립 학술 심사를 자동으로 수행하지 않는다.
