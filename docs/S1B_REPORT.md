# Gate S-1B 실행 보고서

검증 환경: Codex 클라우드 Linux, Node 24.22.1, npm 11.9.0, Python 3.12.14, PostgreSQL 17.11(격리 Unix 소켓), Playwright 1.62.1 및 Chromium 155. Windows 실행은 검증하지 않았다. 테스트 및 웹 서버는 종료했다. 운영 사이트 게시 없음. 모든 데이터는 합성이며 학술 자료가 아니다. 원본 fixture는 외부 공개 승인이 없다.

| S-1B 항목 | 판정 | 근거 및 남은 일 |
|---|---|---|
| 독립 프로젝트와 브랜치 | PASS | `/workspace/scriptura`, `feature/gate-s1b`. 다른 저장소와 별개. 원격 저장소/PR은 생성하지 않았다. |
| PostgreSQL 적용·롤백·관계 무결성 | PASS | 격리 PG 17.11에서 적용, 롤백, 재적용 및 검사 14개 통과. 데이터 또는 감사 이력 존재 시 롤백 거부 확인. |
| 권/장/절과 주소 체계 검색 | PASS | 합성 fixture에서 scheme_id와 ref 조합 검색 검증. 서로 다른 체계 간 실제 데이터는 없음. |
| 본문·전통·주장·출처·검증 상태 검색 | PENDING | 본문 및 claim/source 상세와 검증 필터가 있으나 전체 항목에 대한 범용 검색은 없다. 합성 데이터에 주장-전통 소속이 없어 필터 결과가 비어 있다. |
| 주장→증거→반론 관계 그래프 | PENDING | 주장 간 방향 관계와 출처 상세를 보여주지만 독립 증거 노드와 실제 반박 fixture가 없다. 예시 관계는 `qualifies`이며 반박으로 추정하지 않는다. |
| 공식 교리와 개인 의견 구분 | PASS | 귀속 유형을 그대로 보여주고 단일 라벨로 합치지 않는다. fixture 검증기는 개인에게 공식 교리 귀속을 금지한다. |
| 가짜 원문·허위 출처 검증 | PENDING | fixture 계약 검사와 관리자 외부 원문 입력 거부가 있다. 실제 출처 검증·인간 검수와 운영 수집 파이프라인은 미구현. |
| 검증 대기 및 권리 상태 UI | PASS | 명시적 미검증 토글과 각 출처의 저장 정책·권리 상태를 표시한다. 기본 조회는 검증된 주장만 반환한다. |
| 인증·관리자 승인·감사 로그 | PENDING | 관리자 토큰, 합성 샘플 생성, 추출·검수·승인 이벤트와 SQLite 감사 수정/삭제 차단을 검증했다. 이벤트는 주장 상태를 승격하지 않는다. 실제 사용자 인증·승인 워크플로, PostgreSQL 앱 통합, 운영 역할 분리는 미구현. DB 소유자/슈퍼유저는 트리거를 우회할 수 있다. |
| 저장·임베딩·재배포 권리 검사 | PENDING | 기능 자체를 제공하지 않고 default-deny 정책 함수를 제공한다. 향후 작업별 권한을 강제하고 실제 권리 기록을 검수해야 한다. |
| 테스트 및 실행 기록 | PASS | 아래 로그와 README 재현 절차를 참조한다. |

전체 Gate: **PENDING**. PASS는 합성 데이터 기반의 시범 범위에서만 유효하다. 외부 콘텐츠, 운영 공개, AI 자유 응답 및 최종 신학 판정은 수행하지 않았다.

## 테스트 기록

- Fixture 검증: PASS, [fixture.log](../reports/fixture.log).
- Python 계약 단위 테스트: 11 PASS, 0 FAIL, 0 SKIP, [unit.log](../reports/unit.log).
- PostgreSQL 통합: 14 assertion PASS, 0 예상 밖 실패, 0 SKIP; 데이터가 있는 롤백 2건의 거부는 예상된 결과. [postgres-test.log](../reports/postgres-test.log).
- 실제 로컬 HTTP API 통합: 6 PASS, 0 FAIL, 0 SKIP, [api.log](../reports/api.log).
- Chromium UI: 4 PASS, 0 FAIL, 0 SKIP, [ui.log](../reports/ui.log). 별도 Playwright 및 Chromium 필요.
- `npm run build`: 성공. 개발 서버나 테스트와 동시에 실행하면 `.next` 충돌이 발생하므로 순차 실행한다.

세부 설치, API, 환경 변수, 마이그레이션과 역순 롤백 명령은 [README](../README.md), 스키마 보정안 및 롤백 보호는 [DB_MIGRATION_NOTES](DB_MIGRATION_NOTES.md)를 참조한다. 검증은 이 클라우드 인스턴스에서 수행했으며 새 작업의 복원이나 운영 배포는 검증하지 않았다.
