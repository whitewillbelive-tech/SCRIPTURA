# Gate J-1 — D-7 실제 자료 수신 기록

기준 저장소 `whitewillbelive-tech/SCRIPTURA`, 기준 브랜치 `codex/scriptura-i3-d6-contract`, 기준 커밋 `939faaa77b47b004741d458d1e468e746d623908`. 이번 작업은 별도 개발 브랜치에서 Work D-8을 기다리지 않고, 첨부 동결 D-7 자료의 읽기 전용 검증과 합성 데이터 시험으로 수행한다. 이 보고서는 자료의 신학적 진실, 공식 채택, 사람의 독립 학술 심사 또는 자료 이용권에 대한 승인이 아니다.

## 동결 입력과 계층

사용자가 첨부한 파일명은 `SCRIPTURA_D7_download.zip`이지만 별도 래퍼가 아닌 D-7 연구 ZIP 자체다. 최초 읽기 SHA-256은 `8a8fb8d4efde68f639b99ab8edb9eab14c320b4bc9e64e0aab882af7ee0a4820`이며 ZIP CRC와 D-7 manifest 42/42를 확인했다. 고정 D-7이 내장한 D-6의 SHA-256은 I-3 기준 `6d94de447eba8517c038f6f709c8b1040e0c6efbdd4676f9e19aea568d3e59da`와 일치한다. D-7 검증기는 D-1부터 D-7까지 각각 28·65·69·72·53·32·42개 manifest 항목을 대조하고, D-4 기준 3,104·D-5 754·D-6 584·D-6 부가 65·D-7 770·D-7 부가 149건을 구분한다. [격리 요약](J1_QUARANTINE_SUMMARY.json)의 5,426개 입력 항목은 모두 격리 상태다. 로컬 mapping-preview의 3,637개 연결은 원 ID 대신 원본 좌표를 사용한다. D-6 부가 scope 참조 3건과 D-7 부가 scope 참조 1건은 보류다. D-6 안의 D-5를 포함한 중첩 기준본은 재반입하거나 정본으로 쓰지 않는다. D-7의 `logs/HANDOFF_SHA256SUMS.txt`는 D-7 자체 manifest가 아니라 이전 I-3 인계의 외부 목록이다. D-7에 들어 있는 대응 항목 3/6만 D-7 단독으로 대조할 수 있으며, 이전 사용자 첨부를 별도로 읽는 경우 6/6이 일치한다. 재현 환경에 그 이전 첨부가 없으면 나머지 3개는 외부 검증 대기다. 내장 D-6의 역사적 인계 목록 역시 해당 ZIP 자체에서는 대응 2/5만 확인 가능하고 나머지 3개는 이전 인계를 필요로 하므로 별도 pending으로 기록한다. 원본 ZIP과 개별 연구 레코드·원문은 저장소에 포함하지 않는다.

D-7 신규 15종 JSONL 레코드는 총 770행이다: 공동체 0, 출처 37, 판본 37, locator 51, 주소 60, 주장 42, 외부 평가 5, 권위 34, 근거 42, 관계 8, 권리 333, 접근 행사 39, 감사 관찰 79, 철회된 정정 후보 1, 조사 공백 2. 별도 JSONL 보고서 149행은 D-6–D-7 대응표 41, 주소 범위 13, 보수적 발화 문헌 집계 21, 접근 색인 37, 중복 검토 37이며 정본 신규 레코드와 중복해 합산하지 않는다. 60개 주소는 겹치는 범위와 서로 다른 체계를 포함하므로 고유 구절 수가 아니다.

기존 D-6의 감사 대상은 주장 33개와 평가 8개로 총 **41개**다. 새 감사 관찰은 79개이며, 주장에 관한 63개와 평가에 관한 16개다. 대응표는 고유 대상 41개에 고유 감사 79개를 연결한다. 원본 주장의 `verification_status`와 평가에 실제 존재하는 `verification_status` 또는 `source_verification`(둘 다 없으면 null)을 감사의 이전 상태 필드와 비교하면 감사 79건과 대응표 41건이 모두 일치한다. 이 유형별 일치는 추가 검토 이벤트가 원본을 덮어쓰거나 다른 네 권위·검증 축을 자동 승격한다는 뜻이 아니다.

## 의미와 중복의 경계

신규 주장 입력 귀속은 공동체 자기 설명 31, 개인 의견 8, 학술 해석 2, 외부 비판 1이다. 공동체가 발화자인지 외부 평가의 대상인지, 출판과 정식 채택인지 명확히 나누며 누락된 주체·관할을 만들어내지 않는다. 출처 확인은 공식 교리의 자동 확정이나 인적 학술 심사가 아니다. 접근 경로가 원문·번역·초록·검색·AI 번역 대기 중 무엇인지 원 상태를 보존한다.

D-7 37판본에 대해 9개 행위의 판단 333건이 존재한다. 원본의 `unknown` 327건과 `conditional` 6건을 모두 기본 거부로 두며 목적·지역·조건 검토 없이 이용 허가로 변환하지 않는다. 모든 행위가 독립된 권리이며 하나의 출판자 선언을 다른 삽화·자료·판본에 확장하지 않는다.

제공된 중복 검토에서 D-6 또는 D-7 내부의 정규화 URL 정확 중복은 0건이며 동일 저작 가능성에 관한 후보 4건은 별도로 남아 있다. 독립된 제목 공백·대소문자 정규화 검사에서 D-6–D-7 동일 제목 1쌍도 후보로 발견했지만 같은 저작·판본이라는 뜻은 아니다. URL·제목만으로 우회 주소나 의미가 같은 저작 전체를 탐지하지 못한다. 신규 37개 출처와 원본 보고서가 보수적으로 꼽은 21개 발화 문헌은 서로 다른 집계이고 저자·기관이 서로 독립적이라는 증명이 아니다.

기존 스키마와 다형 참조, 공동체 자기 진술·외부 평가·후대 문서·직접 반박의 차이, 주소·이력·권리에 대한 미호환 및 pending은 [J-1 스키마 호환성](J1_SCHEMA_COMPATIBILITY.md)에 정리했다. ZIP의 행·좌표·해시 기반 공개 요약은 원본을 재구성하지 않지만, 원본을 가진 사람이 연결할 수 있으며 익명화를 보장하지 않는다. 실제 원문·개인정보·권리 미확인 자료가 공개 저장소에 들어오지 않도록 별도 점검한다.

## 재현 및 검증

실제 ZIP은 저장소 밖에 읽기 전용으로 두고 세 명령을 실행한다. `--output`은 존재하지 않는 새 경로만 허용한다.

```sh
python3 scripts/j1_d7_dryrun.py validate /path/to/SCRIPTURA_D7_RESEARCH.zip
python3 scripts/j1_d7_dryrun.py dry-run /path/to/SCRIPTURA_D7_RESEARCH.zip --output /path/to/new-quarantine-report.json
python3 scripts/j1_d7_dryrun.py mapping-preview /path/to/SCRIPTURA_D7_RESEARCH.zip --output /path/to/new-mapping-preview.json
```

합성 DB에서는 전용 빈 테스트 DB에 004 → 005 → 007 → 008 순서로 적용한다. 008의 빈 구조 롤백은 `psql -X -v ON_ERROR_STOP=1 "$DATABASE_URL" -f db/008_j1_research_guard.down.sql`이며, 이력이 있는 경우 롤백은 거부된다. 합성 격리 DB에서 008 적용·빈 롤백·재적용, 고정 해시 거부, 원자적 롤백 및 제한 역할 검사는 12 PASS / 0 FAIL / 0 SKIP이다. [로그](reports/j1-staging-pg.log). 기존 합성 staging 회귀 5 PASS / 0 FAIL / 0 SKIP이다. [회귀 로그](reports/j1-staging-regression.log). 해당 가드는 알려진 고정 해시의 추가 방어이며 재포장된 실자료나 부정확한 합성 분류를 자동 판별하지 않는다.

기준 I-2.1 UI의 503·늦은 응답·초기화 회귀를 포함한 Chromium 권위 UI 7 PASS, 기존 데모 UI 4 PASS, 기존 API 6 PASS이며 모두 FAIL 0 / SKIP 0이다. [API 로그](reports/j1-api-regression.log). 격리 production 빌드도 PASS다. [UI 로그](reports/j1-ui-regression.log), [빌드 로그](reports/j1-build.log). 격리 사본의 초기 빌드 두 차례는 각각 의존성 심볼릭 링크와 TypeScript 실행 문제로 실패했으며 그 결과도 [첫 로그](reports/j1-build-initial.log)와 [두 번째 로그](reports/j1-build-sandbox.log)에 보존한다. `validate`, `dry-run`, `mapping-preview` 세 모드는 고정 D-7에서 구조 검사 PASS이고 입력 전후 해시가 같았다. [실자료 읽기 전용 로그](reports/j1-real-dryrun.log). J-1의 합성 부정·단위 검사는 32 PASS / 0 FAIL / 0 SKIP이다. [로그](reports/j1-d7-unit.log). 최종 Python 전체 회귀는 198 PASS / 0 FAIL / 0 SKIP이다. [전체 로그](reports/j1-python-all.log). 원격 CI 결과는 개발 브랜치 실행을 별도로 확인한다. 실자료는 읽기 전용 검증·dry-run에만 사용하고 PostgreSQL 쓰기와 롤백·승인 경로는 분리된 합성 데이터 환경에서만 시험한다. I-3의 성공한 4개 CI 작업과 I-2.1의 오류 복구 회귀를 유지한다. 실제 연구 DB 쓰기, 정본 자동 승격, `main` 병합과 운영 배포는 수행하지 않는다.
