# D-2 합성 전용 스테이징

이 코드는 전용 임시 PostgreSQL에서 **생성된 합성 자료만 시험**한다. 고정 D-2 연구 ZIP은 `validate`/`dry-run`으로만 처리하며 실제 D-2나 D-3를 스테이징하거나 기존 정규 테이블·운영 DB로 이식하지 않는다. 사람의 검수나 `source_verified`를 `scholarly_reviewed`로 승격하지 않는다. Work 자료와 실제 원문을 저장소에 커밋하지 않는다.

## 보존 범위와 권리

`004_d2_staging.sql`은 독립 `scriptura_d2_stage` 스키마에 `snapshots`와 `records`를 만든다. 테스트 스냅샷 ID, 원본 ZIP 이름과 SHA-256, 각 JSONL의 경로·원본 파일 SHA-256·행 번호·줄바꿈을 포함한 원본 행 SHA-256, 원본 레코드 ID, 원래 검증 상태, 격리 사유와 권리별 edition/action/decision을 기록한다. 원문, 해석 주장, 출처 제목 등 JSON 행 payload는 **저장하지 않는다**. 따라서 이 스키마의 메타데이터만으로 원본 레코드를 무손실 재구성할 수 없다. D-2 원본은 안전하게 별도 보존해야 하며 실제 적재와 재구성은 향후 별도 수용 설계가 필요하다.

9개 action의 원래 판단은 구분해 보존한다. 아직 판본·목적·지역·기간과 독립 승인 여부를 강제할 권리 모델이 없으므로 이 브리지의 `action_allowed`는 `allowed`를 포함한 **모든 행위에 대해 False**를 반환한다. raw·excerpt 저장, fulltext 색인, 임베딩, 모델 전송, 재배포, 공개 링크를 실행하는 기능도 없다. 다른 판본의 권리를 빌리거나 conditional/unknown을 허가로 변환하지 않는다.

## 안전한 합성 시험 준비

아래 단계는 다른 프로젝트 DB와 무관한 **로컬 폐기용** DB에서만 관리자/소유자와 제한 writer를 분리해 실행한다. PostgreSQL 15 이상 및 `psql`이 필요하다. 기존 운영 DB나 `DATABASE_URL`을 덮어쓰지 않는다. 이 코드에서 단지 DB 이름을 바꾸는 것만으로 운영 DB가 안전해지는 것은 아니다.

1. 별도 클러스터/인스턴스의 loopback에 `scriptura_staging_`로 시작하는 빈 DB와 non-superuser·non-owner·non-CREATEDB·non-CREATEROLE·non-REPLICATION·non-BYPASSRLS 로그인 writer를 미리 생성한다. writer는 DB/schema 소유자나 그 역할의 멤버가 아니어야 하며 다른 테이블·뷰가 없는 전용 DB여야 한다.
2. 안전하게 관리되는 **소유자 연결 정보**를 사용하여 `psql -X -v ON_ERROR_STOP=1 "$SCRIPTURA_TEST_STAGING_OWNER_URL" -f db/004_d2_staging.sql`을 실행한다. 예시는 `SCRIPTURA_TEST_STAGING_OWNER_URL`을 테스트용으로만 사용한다.
3. 소유자 세션에서 사전에 만든 writer에만 다음 권한을 부여한다. 실제 역할 이름에 맞게 변경한다.

```sql
GRANT USAGE ON SCHEMA scriptura_d2_stage TO scriptura_stage_writer;
GRANT SELECT, INSERT ON scriptura_d2_stage.snapshots, scriptura_d2_stage.records TO scriptura_stage_writer;
```

4. 다음 환경 변수를 설정하고 공개 합성 CLI를 실행한다. 실제 비밀번호·토큰은 파일이나 Git에 넣지 말고 안전하게 공급한다.

```sh
export SCRIPTURA_STAGING_APPROVED=synthetic-test-only
export SCRIPTURA_STAGING_DATABASE_URL='postgresql://scriptura_stage_writer@127.0.0.1:5432/scriptura_staging_example'
python3 scripts/stage_synthetic.py
python3 scripts/stage_synthetic.py
```

CLI는 외부 ZIP 경로를 받지 않고 합성 테스트 factory를 내부 호출한다. 실행 전 같은 ZIP 스냅샷에 대한 hash·manifest·JSONL 검증을 수행한다. 동일 snapshot/ZIP/메타데이터 재실행은 기존 건을 검증하고 중복하지 않는다. 같은 snapshot의 hash나 내용이 다르면 transaction 전체를 거부한다. PostgreSQL에 전달되는 것은 행의 문자열 본문이 아닌 검증된 메타데이터다.

`SCRIPTURA_STAGING_DATABASE_URL`의 호스트는 `localhost`, `127.0.0.1` 또는 `::1`만 허용하고 DB 이름은 `scriptura_staging_` 접두어가 필수다. `localhost`는 127.0.0.1로 고정하며 libpq 연결을 바꾸는 상속 `PG*` 변수는 제거한다. `DATABASE_URL`, `SCRIPTURA_PRODUCTION_DATABASE_URL`, `SCRIPTURA_REVIEW_DATABASE_URL`이 존재하고 같은 host/port/DB를 가리키면 사용자 이름이 달라도 거부한다. 알 수 없는 별칭으로 같은 DB를 가리킬 가능성도 포트·DB 이름이 같으면 거부한다. writer의 소유권·상위 역할·과도한 권한·DB의 다른 사용자 테이블/뷰를 연결 후 확인한다. 대상 URL만으로 운영 환경이 없음을 증명할 수 없으므로 실행자도 별도 테스트 인스턴스를 확인해야 한다.

마이그레이션을 `psql`로 **직접** 실행할 때는 loader의 URL 검사·승인 환경 변수가 적용되지 않으며, SQL 자체는 DB 이름 접두어와 빈 DB만 확인한다. Docker 포트 포워딩에서는 서버가 로컬 클라이언트를 내부 NAT 주소로 보기도 하므로 SQL은 서버의 `inet_client_addr`로 loopback 여부를 보장하지 않는다. 관리자에게는 전용 로컬 DB인지 직접 확인할 책임이 있다.

`stage_synthetic()` 내부 Python 함수는 재현 테스트를 위해 ZIP 경로 및 검증 pin을 인자로 받는다. `TEST-SYNTHETIC-` 이름만으로 재포장된 실자료가 합성임을 증명할 수 없으므로 이 내부 API는 신뢰된 테스트 코드 전용이며 보안상 합성 판별기나 범용 외부 입력 경로가 아니다. 공개 CLI에 외부 파일 인자를 연결하거나 미래 Work 자료를 이 함수에 자동 공급하지 않는다.

## 테스트와 롤백

빈 전용 DB에 `SCRIPTURA_STAGING_APPROVED=synthetic-test-only` 및 `SCRIPTURA_TEST_STAGING_OWNER_URL`을 설정하고 `python3 tests/s1b2_staging_rollback.py`를 실행하면 004 적용, 추가 객체 존재 시 rollback 거부 및 전체 보존, 테스트 객체 제거 후 빈 DB rollback과 재적용을 확인한다. 스키마가 이미 있거나 DB가 비어 있지 않으면 시작 단계에서 실패하며 기존 객체를 삭제하지 않는다. 재적용된 스키마에 위 writer 권한을 부여한 뒤 `SCRIPTURA_STAGING_DATABASE_URL`을 설정하고 `python3 tests/s1b2_staging_pg.py`를 실행하면 합성 적재, 파일·행 해시와 9개 권리 결정, 멱등성, 스냅샷 충돌, 역할 분리, 이력 변경 및 데이터 존재 시 rollback 거부를 검사한다.

수동 rollback은 모든 writer를 중지하고 **빈 전용 DB에서만** `psql -X -v ON_ERROR_STOP=1 "$SCRIPTURA_TEST_STAGING_OWNER_URL" -f db/004_d2_staging.down.sql`로 수행한다. 데이터가 있으면 거부하고, 추가 객체나 외부 의존 객체가 있으면 `RESTRICT`가 transaction 전체를 되돌린다. 데이터 삭제를 자동 수행하지 않는다. owner·superuser는 PostgreSQL 보호 장치를 바꿀 수 있고 writer DB 자격을 직접 가진 자는 INSERT를 실행할 수 있으므로 감사 변조 불가능성이나 적대적 사용자에 대한 보안 경계로 사용해서는 안 된다.

합성 1만/10만 건 성능 시험은 검증기 기준이며 스테이징은 전체 메타데이터를 메모리와 단일 transaction으로 처리한다. 대규모 스테이징의 메모리 사용, 처리량, 동시성은 검증하지 않았다. 현재 브리지의 입력 ZIP 제한은 32 MiB다.
