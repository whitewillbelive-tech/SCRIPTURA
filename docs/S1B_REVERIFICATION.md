# Gate S-1B 재검증

기존 구현 커밋 `59896e47cd22870edd6b43dcb907021d76f4a58c`을 보존한 채 2026-11-05 클라우드 Linux에서 재검증했다. 합성 데이터는 실제 학술 데이터가 아니며 공개 승인되지 않았다. 운영 배포와 외부 콘텐츠 수집은 수행하지 않았다. Windows에서는 실행하지 않았다.

| 항목 | 판정 | 근거와 남은 범위 |
|---|---|---|
| 독립 프로젝트 | PASS | 로컬 독립 Git 저장소에서 원본 작업 보존. |
| PostgreSQL 마이그레이션·롤백·무결성 | PASS | 격리 PostgreSQL 17.11에서 적용, 빈 DB 롤백, 재적용; 제약·감사 14개 통과, 데이터가 있거나 감사 이력이 있는 롤백은 예상대로 거부. |
| 주소 다대다 매핑 | PASS | 합성 주소 A1→B1/B2, A2→B1 및 제약 4개 검증. 동일 출발·도착·유형의 중복은 허용되며 추가 유일성 검토 필요. |
| 주소 체계 기반 권·장·절 검색 | PENDING | API는 scheme_id와 ref의 선택적 정확 일치만 지원하며 권·장·절 파싱과 필수 체계 선택 UI는 없다. |
| 본문·전통·주장·출처·검증 상태 검색 | PENDING | 상세 조회와 필터는 있으나 전 항목 검색 및 합성 전통 소속 데이터가 없다. |
| 주장→근거→반론 그래프 | PENDING | 주장의 방향 관계는 표시하나 독립 근거 노드 및 반박 fixture가 없다. 예시 `qualifies` 관계는 반박이 아니다. |
| 공식 교리·개인 의견 구분 | PASS | 귀속 유형을 별도 표시하고 fixture 계약은 개인에게 공식 교리를 귀속하지 못하게 검증한다. |
| 실제 출처·원문 검증 | PENDING | 합성 계약과 외부 원문 입력 거부만 검증했다. 실제 자료 수집 및 인간 출처 검수 미구현. |
| 검증 대기·권리 상태 UI | PASS | 미검증 토글과 권리 상태를 Chromium에서 확인. |
| 관리자 인증·승인·감사 | PENDING | 로컬 토큰 및 SQLite 추출·검수·승인 이벤트와 불변 트리거 시험. 승인 이벤트는 주장을 승격하지 않으며 실제 계정, 운영 승인, PostgreSQL 통합 및 역할 분리는 미구현. DB 소유자·슈퍼유저는 트리거 우회 가능. |
| 저장·임베딩·재배포 권리 강제 | PENDING | 설계 함수의 각 action 기본 거부와 조건을 단위 시험. 실제 기능과 작업별 권리 강제는 미구현. |

전체 Gate **PENDING**. 이전 `S1B_REPORT.md`의 검색 PASS는 합성 데이터에서 정확 일치 조회만 검증한 것으로 한정하며, 위 판정이 최종 재검증 결과다.

## 결과 및 재현

- fixture 검증 PASS: [reverify-fixture.log](../reports/reverify-fixture.log).
- Python 계약: **11 PASS / 0 FAIL / 0 SKIP**, [reverify-unit.log](../reports/reverify-unit.log).
- API 및 인증·감사 통합: **6 PASS / 0 FAIL / 0 SKIP**, [reverify-api.log](../reports/reverify-api.log).
- 권리 정책 함수: **3 PASS / 0 FAIL / 0 SKIP**, `node tests/rights-policy.test.cjs`, [reverify-rights.log](../reports/reverify-rights.log).
- PostgreSQL 마이그레이션 및 무결성: **14 assertions PASS / 0 FAIL / 0 SKIP**, 롤백 거부 2건은 기대한 결과, [reverify-postgres.log](../reports/reverify-postgres.log). 최초 샌드박스 소켓 제한 로그는 [별도 보존](../reports/reverify-postgres-sandbox.log).
- PostgreSQL 주소 매핑: **4 PASS / 0 FAIL / 0 SKIP**, 빈 전용 DB에 001 적용 후 `psql -X -v ON_ERROR_STOP=1 "$DATABASE_URL" -f tests/reverify-alignments.sql`, [reverify-alignments.log](../reports/reverify-alignments.log).
- Chromium UI: **4 PASS / 0 FAIL / 0 SKIP**, [reverify-ui.log](../reports/reverify-ui.log). 환경 제공 Playwright와 Chromium을 사용했다.

자세한 설치·실행·환경 변수·마이그레이션 및 롤백 명령은 [README](../README.md), DB 보정안은 [DB_MIGRATION_NOTES](DB_MIGRATION_NOTES.md) 참조. 재검증 서버는 모두 종료했다.
