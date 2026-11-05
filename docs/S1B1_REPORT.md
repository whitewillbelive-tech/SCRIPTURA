# Gate S-1B.1 검증 보고서

기준 `gate/s1b-verified`의 `0b04cb017212440767e852448ed4a21e8a0b68df`를 보존하고 별도 개발 브랜치에서 작업했다. 실행 환경은 Codex 클라우드 Linux, Node 24, PostgreSQL 17 격리 DB 및 Chromium이다. Windows 검증과 운영 배포는 수행하지 않았다.

## Work 자료의 통합 범위

요청된 `SCRIPTURA_S1A_RESEARCH.zip`은 제공된 첨부나 작업 공간에서 발견되지 않아 내용을 검토하거나 그 데이터·제안을 통합하지 못했다. 실제 연구 후보나 학술 검증 완료 데이터를 만들어 넣지 않았다. 기존 v0.1 표준과 스키마에 근거한 독립 구현만 반영했다. Work ZIP을 받으면 실제 데이터의 출처·검증·권리를 별도로 검토하고 스키마 제안과 대조해야 한다.

## Gate 항목별 판정

| 항목 | 판정 | 근거 및 남은 일 |
|---|---|---|
| Work S-1A 표준·스키마 제안 분석 | PENDING | ZIP 미제공. 기존 표준만 검토. |
| 합성·실제 후보·검증·권리 미확인 분리 | PENDING | 분류와 모드 분리, 미분류 기본 숨김 및 권리 메타데이터를 구현·합성 자료로 검증. 실제 자료·권리 검수는 미수행. |
| PostgreSQL 읽기 API와 UI 연결 | PASS | 격리 PostgreSQL과 실제 HTTP·Chromium으로 검증. 실제 연구 자료는 없음. |
| 전통·연구자·귀속별 필터 | PASS | 명시된 전통 소속·연구자·귀속 유형 필터를 합성 DB에서 검증. 소속을 공식 교리로 추론하지 않음. |
| 정경·장절 체계 검색 및 다대다 대응 | PENDING | corpus·scheme·정확한 외부 주소 검색 및 양방향 대응 조회 구현. 권·장·절 개별 파싱 및 Work의 실제 대응 사례 검증은 미완료. |
| 주장·근거·반론·상호 참조 그래프 | PASS | 합성 DB에서 근거 노드, 주장 관계와 본문 상호 참조 및 방향을 검증. 1-hop 및 500건 제한. 실제 학술 관계는 검증하지 않음. |
| 확인되지 않은 관계 비확정 표시 | PASS | 검증 상태뿐 아니라 확인된 날짜·비어 있지 않은 출처 위치를 검사하고 불충분한 관계는 확정으로 표시하지 않음. |
| 관리자 승인·감사 및 인증·권리 통제 | PENDING | 분리 DB 역할, 서버 고정 검수자, 최소 32바이트 토큰, 원자적 승인·append-only 감사를 시험. 개인별 인증·운영 권한·토큰 회전·다중 작성자 동시성·실자료 권리 강제는 미완료. |
| 미허가 자료 공개 방지 | PENDING | 외부 원문 수집·임베딩 기능 및 실제 자료를 포함하지 않음. JSON fixture 정책 검사는 네 가지 원문/임베딩 필드와 명시적 합성 상태만 확인하며 전체 저작권 판별이 아님. |
| 자동 테스트·GitHub Actions | PENDING | 로컬 테스트와 workflow 설정 완료. 원격 Actions 실행 및 결과는 아직 확인되지 않음. |

전체 Gate는 **PENDING**이다. 출처 검증은 그 출처를 정확히 기록했음을 뜻하며 주장이나 신학적 진실을 판정하지 않는다.

## 테스트 결과

- Python 계약·fixture 정책: 14 PASS / 0 FAIL / 0 SKIP. 권리 정책 함수: 3 PASS / 0 FAIL / 0 SKIP. [s1b1-unit.log](../reports/s1b1-unit.log)
- 기존 데모 HTTP API: 6 PASS / 0 FAIL / 0 SKIP. [s1b1-demo-tests-elevated.log](../reports/s1b1-demo-tests-elevated.log)
- PostgreSQL HTTP·역할·승인·감사: 6 PASS / 0 FAIL / 0 SKIP. [s1b1-api.log](../reports/s1b1-api.log)
- PostgreSQL 새 무결성 검사 26 그룹, 기존 스키마 14개 및 주소 매핑 4개 PASS. 빈 전용 DB 마이그레이션 적용·롤백·재적용 및 분류 데이터 보존 거부 확인. [s1b1-postgres.log](../reports/s1b1-postgres.log)
- Chromium 기존 데모 4 PASS, PostgreSQL UI 4 PASS, 각각 0 FAIL / 0 SKIP. [s1b1-ui-demo.log](../reports/s1b1-ui-demo.log), [s1b1-ui-db.log](../reports/s1b1-ui-db.log)
- Next.js 빌드 PASS: [s1b1-build.log](../reports/s1b1-build.log). 패치 후 `npm audit --omit=dev` 취약점 0건.

초기 PG UI 테스트는 로딩 대기 및 중복 텍스트 선택 문제로 2 PASS / 2 FAIL이었으며 테스트 동기화 수정 후 재실행했다. [초기 로그](../reports/s1b1-ui-db-initial.log). 기존 데모 HTTP 테스트의 기본 샌드박스 실행은 루프백 바인딩 제한으로 실패해 권한 조정 후 재실행했다. [초기 로그](../reports/s1b1-demo-tests.log). 최종 테스트의 실패는 0건이다.

명령, 환경 변수 및 권한은 [API 안내](API_S1B1.md)와 [DB 안내](DB_S1B1.md), CI 순서는 [workflow](../.github/workflows/verify.yml)를 참조한다. 검증된 데이터의 분류와 근거 변경을 여러 작성자가 동시에 수행하는 경우의 직렬화는 아직 검증되지 않았다. 실자료를 받기 전 운영 인증·권리 강제·역할 검토와 동시성 검증이 필요하다.
