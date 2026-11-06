# Gate I-2 실행 보고서

기준은 `whitewillbelive-tech/SCRIPTURA`의 `codex/scriptura-i1-d3-receipt` / `e12449adab98eee8421e06d1bb9cca5933991e82`이며 작업 브랜치는 `codex/scriptura-i2-authority`다. 실행 환경은 Linux 클라우드의 격리된 합성 테스트 환경이다. Work D-5는 기다리거나 입력으로 사용하지 않았다. 실제 연구 데이터의 DB 쓰기·정본 승격, 운영 배포, main 병합은 수행하지 않았다.

## 구현과 판정

| 항목 | 판정 | 근거 및 한계 |
|---|---|---|
| D-5 계약과 기존 데이터의 차이 분석 | PASS | [계약 차이](I2_CONTRACT_DIFF.md), [스키마 차이](I2_SCHEMA_DIFF.md). D-5 실제 데이터는 통합하지 않았다. |
| 다층 권위·네 독립 상태 | PASS | 공식 채택, 기관 설명, 역사적 간행물, 개인 견해, 외부 비평, 학술 분석, 미확정을 구분한다. 인용·권위·논증·독립 검수는 별도이며 source_verified만으로 다른 축을 승격하지 않는다. 증거 부족은 미확정이다. |
| PostgreSQL 증거·이력과 제한 역할 | PASS | 006 추가 마이그레이션은 확인 가능한 범위와 네 축을 분리하고 append-only 관찰, 근거 재평가, 마스킹된 제한 조회를 구현한다. 합성 DB에서만 적용·롤백 및 권한을 시험했다. |
| API·합성 UI와 기존 경로 보호 | PASS | 합성 UI `/authority`와 `/api/v1/authority`, 명시적인 database 모드·필터 및 별도 제한 역할을 제공한다. 비합성 자유문은 차단하며 공식 근거가 없는 기존 라벨은 미확정으로 표시한다. |
| 동결 D-4 수신과 격리 | PASS | 원본의 고정 SHA 및 중첩 manifest를 검증하고 읽기 전용 dry-run. 출력은 [집계·행 해시·이유](I2_D4_DRY_RUN.json)만 포함한다. 실제 데이터 DB 쓰기 0, 정본 승격 0. |
| 실존 공식 문헌 및 채택 사실 직접 확인 | PENDING | 환경의 공식 기관 호스트 outbound 미허용으로 공식 문서 두 곳에 대한 프록시 CONNECT 요청이 403으로 차단됐다. 대상 서버 응답에 도달하지 못했으므로 직접 확인을 주장하지 않는다. 대조 가능한 환경에서 판본·정확 locator·관할·기간과 채택 절차를 검토해야 한다. |
| 실제 D-5 자료·행위별 권리·독립 검수 | PENDING | 미수신 D-5를 추정하지 않는다. 9개 행위는 기본 거부이며 실제 자료·메타데이터의 권리 및 개인정보 검토가 필요하다. |
| 운영 인증·전체 직접 DB 권한 경계 | PENDING | 분리된 제한 역할의 합성 시범이다. 기존 광범위 DB 역할, 고권한 소유자, 잘못 합성으로 분류된 실자료와 임의 텍스트의 저작권 판별은 보장하지 않는다. |
| GitHub Actions | PASS | 구현 커밋 `0a547c3bcdc453a2e267abe619d71021b99c405d`의 [실행 42145564930](https://github.com/whitewillbelive-tech/SCRIPTURA/actions/runs/42145564930)에서 4개 작업 모두 성공했다. |
| I-3 통합·운영 배포 | PENDING | D-5 실제 증거와 계약 대조 및 별도 승인 이전에 수행하지 않는다. |

## 동결 D-4 결과

입력 ZIP SHA-256은 `05ab5bdf3fc258f39b926257c771ef4a17138355aa072cb8bc97c56387999beb`이며 실행 전후 동일했다. 바깥 인계 manifest 8/8과 동결 ZIP의 중첩 manifest 72/72 및 기준 비교를 확인했다. 12종의 병합 레코드 3,104개와 별도 수신 항목을 합친 3,254개를 격리했다. 원본 주장 78개 중 기존 상태는 source_verified 74개, candidate 4개, scholarly_reviewed 0개다. 이는 원본의 기록 상태이며 직접 원문 확인, 공식 채택이나 인간 독립 심사의 증명이 아니다. 기존 `official_doctrine` 표기는 2개이나 채택 근거로 자동 처리하지 않았다. 네 축 계약 필드가 주장에 명시적으로 매핑되지 않은 78개를 보류했으며, 관련 증거가 전혀 존재하지 않는다는 뜻은 아니다.

인계 자료의 1,953개 권리 행을 보존·검사하되 조건부·미상 또는 목적·관할·기간이 미확인된 권리는 사용 허가로 바꾸지 않았다. dry-run은 9가지 행위에 대한 실자료 이용을 허용하지 않고 원문을 저장·임베딩·배포하지 않는다. 원본 ZIP 및 비공개 연구 레코드는 저장소에 포함하지 않는다.

## 재현과 자동 검증

실행 명령과 DB 분리 역할은 [README](README.md), [스키마 안내](I2_SCHEMA_DIFF.md)를 따른다. 로그의 SQL 데이터와 UI 예시는 모두 합성 자료다. 명령 및 결과는 `reports/i2-*`에 보존한다.

- Python 기존 회귀와 D-4 합성 검사: 131 PASS, 0 FAIL, 0 SKIP. 그중 I-2 dry-run 시험 29개. [로그](reports/i2-unit-all.log), [I-2 상세](reports/i2-dryrun-tests.log).
- 권위 순수 단위 시험: 13 PASS, 0 FAIL, 0 SKIP. [로그](reports/i2-authority-unit.log).
- 격리 PostgreSQL과 실제 HTTP 권한·마스킹 통합: 8 PASS, 0 FAIL, 0 SKIP. [로그](reports/i2-authority-api.log).
- 독립 제한 DB 역할 검토: 안전 뷰 마스킹, 합성 표시, 원시 접근 및 쓰기 거부 PASS. [시험](tests/i2_safe_view_review.sql), [로그](reports/i2-safe-view-independent.log).
- PostgreSQL 17: 적용 → 29개 예상 거부·16개 assertion block 및 별도 역할 검사 → 빈 구조 롤백·재적용 → 같은 검사 재실행 PASS. 데이터가 있는 경우 롤백 거부 및 데이터 보존 PASS. [로그](reports/i2-db.log).
- production 빌드 PASS. Chromium UI: 기존 데모 4개, PostgreSQL 4개, I-2 권위 5개로 총 13 PASS, 0 FAIL, 0 SKIP. [빌드](reports/i2-final-build.log), [데모](reports/i2-final-ui-demo.log), [DB](reports/i2-final-ui-db.log), [I-2](reports/i2-final-ui-authority.log).
- 기존 API 회귀: 6 PASS, 0 FAIL, 0 SKIP. [로그](reports/i2-final-regression-npm.log).

이 설계는 공식 근거의 존재·범위를 구조화하고 확인이 부족하면 보류하지만, 사람의 자격이나 자료의 진위·저작권을 자동 증명하지 않는다. 006은 현재 발행/개정 및 시작/종료일을 모두 요구하므로 종료일이 없는 실제 문서도 안전하게 보류될 수 있다. 날짜를 임의로 채우지 않는다.

개발 중 API가 변경되는 동안 먼저 실행한 I-2 브라우저 시험은 2 PASS / 3 FAIL이었다. 변경을 반영한 이후 같은 기능을 production 빌드에서 다시 실행해 위와 같이 5 PASS / 0 FAIL을 확인했다. 초기 결과도 [로그](reports/i2-ui-browser-initial.log)에 보존한다.

## GitHub 반영

구현 커밋 `0a547c3bcdc453a2e267abe619d71021b99c405d`를 `codex/scriptura-i2-authority`에 push했다. 기준 브랜치 `codex/scriptura-i1-d3-receipt`를 대상으로 초안 PR 생성을 시도했으나 GitHub GraphQL 요청이 `Forbidden`으로 차단되어 PR 번호는 없다. [브랜치 비교](https://github.com/whitewillbelive-tech/SCRIPTURA/compare/codex/scriptura-i1-d3-receipt...codex/scriptura-i2-authority)에서 변경을 검토할 수 있다. 우회하지 않았다.
