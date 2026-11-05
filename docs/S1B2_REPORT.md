# Gate S-1B.2 — D-2 수신 준비 및 검증

기준은 `gate/s1b-1-integration`의 `755bbe5d793d72e9f15c898f3b3cbc0cb12f9fce`다. 작업은 별도 `codex/scriptura-d2-staging-bridge` 브랜치에서 수행했다. D-3 결과를 기다리거나 예측하지 않았고, 실제 D-2는 로컬 읽기 전용 검증과 dry-run에만 사용했다. 운영 DB 적재, main 병합, 운영 배포와 실제 D-2 원본의 저장소 반입은 수행하지 않았다.

## 고정 데이터와 보류

D-2 ZIP SHA-256 `c8b64b9144367a8526c77b121b3343f04a7c683276f9fd239b2cc51458589a47`와 snapshot `SCRIPTURA-D11-D2-20261105-v1`이 일치했고 원본의 작업 전후 해시도 같다. 내부 manifest 65개, 12종 총 1,425행, D-1.1 + D-2 delta = merged, ID·참조·행 수 등을 확인했다. [DRY_RUN_REPORT.json](../DRY_RUN_REPORT.json)은 실제 ID·URL·내용 없이 각 행 번호·줄 해시·사유와 집계를 기록한다.

정본 자동 적용 가능 0건, 격리 1,425건이다. 9개 권리 행위는 모두 독립 권리 심사 전 기본 차단된다. 원본 873건의 판단은 unknown 823, conditional 46, allowed 4다. allowed는 browse와 collect_metadata에 각 2건뿐이며 저장·발췌·색인·임베딩·모델 전송·재배포·공개 링크의 허가로 전파하지 않는다. 출처 확인 26건과 후보 4건은 현재 주장 상태이며 `scholarly_reviewed`는 0건이다. 리뷰 이벤트의 숫자는 원본 이력으로 따로 유지한다. 정경/주소 대응 35건은 모두 partial_pending이며 교단 소속 행은 없다.

판본·locator·정경/장절 ID·논증 관계·문학적 화자·9개 행위 권리를 001–003으로 무손실 변환할 수 없으므로 임의의 기본값이나 양방향 확정을 하지 않는다. 각 12종의 차이와 D-3 후속 버전 협상·Gate I-1 절차는 [DATA_BRIDGE_MAPPING.md](DATA_BRIDGE_MAPPING.md)에 있다. D-3 결과의 자동 통합은 구현하지 않았다.

## 명령과 안전 경계

`python3 scripts/d2_bridge_cli.py validate <고정-D2.zip>` 또는 `python3 scripts/d2_bridge_cli.py dry-run <고정-D2.zip> --output <새-보고서.json>`은 DB에 쓰지 않고, ZIP 해시·snapshot을 고정한다. 기존 보고서는 덮어쓰지 않는다. `python3 scripts/stage_synthetic.py`는 외부 ZIP을 받지 않으며 자체 생성 합성 자료만 시험한다. 필수 opt-in·loopback URL·별도 임시 DB·제한 역할과 rollback 단계는 [STAGING_SCHEMA.md](STAGING_SCHEMA.md)에 있다.

004에는 합성 시험의 ZIP·파일·행 해시와 ID·행 번호·검증 상태·행위별 결정을 기록하지만 본문과 payload는 저장하지 않는다. 스키마는 원본 완전 복원 수단이 아니며, 사람의 독립 검수·권리 판정을 대신하지 않는다. 내부 Python 시험 API의 이름만으로 입력이 합성인지 증명할 수 없고, 직접 SQL·DB 소유자나 악의적 동시 쓰기에 대한 운영 보안 경계가 아니다. `psql`로 수동 실행하는 004는 서버 측 loopback을 강제하지 않으므로 관리자가 전용 로컬 DB인지 확인해야 한다. 임의 자유 텍스트에 숨겨진 저작권 원문의 자동 판별은 지원하지 않으며 미검증 행은 모두 격리한다.

## 시험 결과

- 신규 합성 단위 테스트 41 PASS / 0 FAIL / 0 SKIP, 기존 포함 Python 전체 55 PASS / 0 FAIL / 0 SKIP: [s1b2-unit.log](../reports/s1b2-unit.log), [s1b2-unit-all.log](../reports/s1b2-unit-all.log).
- 004 격리 PG17: rollback·추가 객체 보존 7단계, 최소 권한 writer 통합 5개, 합성 CLI 두 차례 멱등 PASS. 실제 연구 ZIP 적재 0건: [s1b2-staging.log](../reports/s1b2-staging.log).
- 기존 기준 회귀: Python 14, 권리 함수 3, 데모 HTTP 6, PostgreSQL HTTP 6, 데모 UI 4, PostgreSQL UI 4 PASS, FAIL/SKIP 0. PG 기존 스키마 14, 003 무결성 26그룹, 주소 대응 4와 001–003 적용·역순 rollback·재적용 PASS. Next.js 빌드 PASS. 각 `reports/s1b2-regression-*.log` 참조. 최초 독립 사본의 의존성 심볼릭 링크가 Turbopack 경계 밖이어서 데모 API 기동이 실패했고, 의존성 복사 후 통과한 기록을 보존했다.
- 생성 합성 source 10,000개(+18행) 검증 0.257초·최대 RSS 52,212 KiB, 100,000개(+18행) 3.109초·366,768 KiB PASS. 각 1회 클라우드 실행이며 source 편중 검증기 부하로, 실자료나 PostgreSQL 적재 성능을 뜻하지 않는다. [계획과 한계](S1B2_SCALE_TEST.md), [10k JSON](../reports/s1b2-benchmark-10k.json), [100k JSON](../reports/s1b2-benchmark-100k.json).
- GitHub Actions는 기존 작업에 합성 10k/100k 검사와 별도 loopback PG staging job을 추가했다. 원격 실행 상태는 해당 브랜치 실행 기록을 확인해야 한다.

| 항목 | 판정 | 제한 |
|---|---|---|
| 고정 D-2 무결성·12종 매핑 차이·dry-run | PASS | 정본 적재 승인 아님 |
| 권리 및 검증 상태 분리·격리 | PASS | 명시 필드 검사와 전 행 보류; 숨겨진 원문 및 실제 권리의 자동 판정 불가 |
| 합성 격리 스테이징·멱등·롤백 보호 | PASS | 별도 임시 DB·제한 역할 시험 범위 |
| S-1B.1 회귀·합성 부하 | PASS | 실제 자료·대량 DB 부하 아님 |
| D-3 접합·독립 학술 심사·실자료 정본 적재 | PENDING | 별도 Gate I-1과 사람의 검수 및 권리 결정 필요 |
| 운영 보안·실자료 처리·대량 스테이징 | PENDING | 승인·격리·동시성·권리 강제 설계 필요 |
