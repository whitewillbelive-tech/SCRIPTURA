# I-1 합성 스테이징 보강

실제 D-3는 읽기 전용 검증·dry-run 대상이다. I-1은 D-2 합성 로더의 고정 D-2 차단을 유지하고, 고정 D-3 ZIP SHA-256도 내부 합성 로더의 파일 열기와 DB 접속 전에 거부한다. 004 자체를 변경하지 않는 추가 `db/005_i1_research_guard.sql`은 전용 `scriptura_staging_` DB의 004 `snapshots` 테이블에 D-3 해시 차단 CHECK를 추가한다. 검증에 사용하는 D-3 SHA 자체는 공개된 인계 해시이고 연구 레코드를 읽거나 DB에 쓰지 않는다.

005 rollback은 전용 DB에서 스테이징 이력이 비어 있을 때만 허용하며, 이력이 있으면 guard와 데이터를 유지한다. 005 적용/역순 rollback은 [기존 안전 지침](STAGING_SCHEMA.md)에 명시된 격리된 로컬 테스트 환경에서만 관리자가 실행한다. 005는 004의 synthetic snapshot 조건과 D-2 해시 차단을 변경하지 않으며 자동 정본 적재 기능은 없다.

`tests/i1_staging_guard.py`는 004가 미리 적용된 **빈 별도 폐기용** `scriptura_staging_` DB에서 005 적용·D-3 hash 거부·빈 DB down/up·합성 이력 존재 시 rollback 거부를 검증한다. 소유자 연결 URL `SCRIPTURA_TEST_STAGING_OWNER_URL`과 `SCRIPTURA_STAGING_APPROVED=synthetic-test-only`가 필요하다. 종료 후 합성 테스트용 snapshot 1개가 남으므로 기존 PostgreSQL 스테이징 회귀 테스트 DB와 분리한다. 예시 순서:

```sh
psql -X -v ON_ERROR_STOP=1 "$SCRIPTURA_TEST_STAGING_OWNER_URL" -f db/004_d2_staging.sql
python3 tests/i1_staging_guard.py
```

실행 결과는 [i1-staging.log](../reports/i1-staging.log)와 [i1-staging-unit.log](../reports/i1-staging-unit.log)에 있다. 004/005의 SQL 파일을 직접 실행하는 경우에는 클라이언트 로더의 loopback 및 opt-in 검사를 우회하므로 관리자가 별도 로컬 테스트 DB를 확인해야 한다. snapshot 이름이나 특정 ZIP 해시만으로 재포장된 자료가 합성인지 입증할 수 없다. 고권한 소유자·직접 SQL·의도적인 재포장에 대한 일반적 보안 경계가 아니며, 실자료 적재는 별도 권한 및 설계 이전까지 금지다.
