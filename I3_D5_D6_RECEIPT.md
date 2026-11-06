# Gate I-3 — 동결 D-5/D-6 수신 및 매핑 기록

기준은 `whitewillbelive-tech/SCRIPTURA`, `codex/scriptura-i2-1-ci-repair`의 `3865a14fd60a64fa9447b52c3e98b6f31991204b`다. I-2.1의 503·늦은 응답·초기화 처리와 CI를 보존하는 별도 브랜치에서 수행한다. Work D-7 자료를 기다리거나 추정하지 않았다. 이 보고서는 원본의 집계와 안전한 수신 경계이며 실제 자료의 신학적 정오, 공식 채택 또는 이용권을 인증하지 않는다.

## 입력 무결성 및 범위

고정 D-6 ZIP의 SHA-256은 `6d94de447eba8517c038f6f709c8b1040e0c6efbdd4676f9e19aea568d3e59da`, 내장 D-5 ZIP은 `4709ddbe914c276e68ebcc66cee1d76e1c096e0071992eb53b9e4c2f03e96d19`, 그 안의 D-4 ZIP은 `05ab5bdf3fc258f39b926257c771ef4a17138355aa072cb8bc97c56387999beb`다. D-5는 D-6 내부에서만 읽으며 중복 반입하지 않는다.

독립 읽기 검토에서 바깥 인계 manifest 6/6, D-6 자체 manifest 32/32, D-5 manifest 53/53, D-4 manifest 72/72, D-3 manifest 69/69가 일치했다. 내장 D-3 SHA는 `baf206d2846544f1e1bb20622ac10c557394b71aa41cfd6e2be5bbafade347be`, D-2 SHA는 `c8b64b9144367a8526c77b121b3343f04a7c683276f9fd239b2cc51458589a47`이다. D-2와 내장 D-1의 `RUN_MANIFEST.json`에 있는 파일 해시·바이트 길이도 각각 65/65, 28/28 일치했다. D-6·D-5·D-3·D-2·D-1 ZIP의 CRC, D-5에 복사된 D-4 병합 기준 12종의 바이트 일치도 확인했다. D-5가 기록한 D-4 고정 SHA도 내장 D-4 해시와 일치했다.

D-6의 `logs/HANDOFF_SHA256SUMS.txt`는 D-6 내부 파일 목록이 아니라 이전 I-2.1 핸드오프의 역사적 manifest다. 같은 세션에서 앞서 제공된 해당 핸드오프 ZIP과 대조한 5/5는 일치한다. 이전 핸드오프가 없는 재현 환경에서는 해당 외부 5항목의 검증은 별도 pending이며 D-6 내부 파일로 대체하지 않는다. 이 대조는 별도 D-5 기준본의 수신이나 DB 적재가 아니다.

## 원본 집계와 검토 의미

검증 도구의 [격리 보고서](I3_QUARANTINE_SUMMARY.json)는 D-4 기준 3,104건, D-5 신규 754건, D-6 신규 584건과 D-6 부가 보고서 65건, 총 4,507개 입력 항목을 실자료 격리 상태로 기록한다. 도구는 2,050개 연결의 자료 계층·테이블·행 번호 기반 대응을 계산했으며, 부가 scope 참조 3건은 기존 확인 범위를 넘어 pending으로 둔다. D-6의 12종 레코드 합계는 584건이다. 공동체 5, 출처 31, 판본 31, 위치 42, 주장 33, 본문 주소 53, 권위 문서 정보 24, 근거 34, 평가 8, 관계 11, 권리 279, 접근 이벤트 33건이다. 별도 JSONL 보고서는 coverage 6, 접근 색인 31, 후보 근거 3, scope coverage 25건이며 각각 겹칠 수 있어 독립 정본 레코드로 합산하지 않는다.

D-5 주요 수신 대상은 권위 registry 19, 문헌 61, 기존 claim 범위 감사 78, 입장 51, 해석 근거 36, 권리 변화 288, 접근 이벤트 110건이다. 기타 D-5 기록에는 출처·판본 각 32, 위치 33, 본문 3, 다른 corpus 주제 1, 감사 충돌 10건이 있으며 전체 D-5 신규 JSONL 기록은 754건이다. 실제 원형과 상태를 바꾸지 않는다.

D-6 주장 33건의 입력 귀속은 공동체 자기 설명 27, 개인 의견 2, 학술 해석 2, 외부 비판 2다. `community_id` 5건은 새 공동체 행이 아니라 D-5 registry의 기존 `tradition_id`를 참조하고, 1건은 null이다. 별도 대상 역할이 표시된 경우 공동체를 발화자로 바꾸지 않는다. 신분·소속이 비어 있는 연구자에게 가짜 소속을 부여하지 않는다.

D-6 문헌 접근 기록의 `source_checked`, `direct_full_text_section_checked`, `source_checked_secondary_transmission`, `collaborator_checked_not_self_checked`는 원본에서 다른 경로다. 이 상태를 모두 직접 원어 대조, 학술적 주장 확인 또는 독립 인간 심사로 통일하지 않는다. 원본의 주장 확인 상태 30건 `source_checked`, 나머지 세 유형 각 1건은 독립 재확인 건수가 아니다.

권리 집계는 D-5 판본 32 × 9행위 = 288건 모두 unknown, D-6 판본 31 × 9행위 = 279건 중 unknown 275·conditional 4다. unknown과 조건부는 허가가 아니며, 원결정의 대소문자·조건·확인 범위를 별도로 보존한다. D-6 53개 주소 레코드는 고유 절 수 또는 정경 간 검증된 대응 수가 아니다. 종교기관의 자기 진술·외부 평가·언론의 진행 중 조사·공식 의결, 직접 반박·공통 구절의 해석 대조는 각각 구분한다.

정확한 ID 공간, 001–006과의 미호환, 각 경계 및 보류 원칙은 [스키마 호환성](I3_SCHEMA_COMPATIBILITY.md)을 참조한다. 실제 D-5/D-6 레코드·원문·개인 정보·미공개 URL 또는 ZIP은 공개 GitHub에 올리지 않는다. 이번 단계에서 실제 자료의 PostgreSQL 쓰기와 정본 승격은 허용하지 않으며 합성 DB만 별도 시험한다. 원자료를 읽기 전용으로 검증한 사실은 자료의 공공 이용·권리 확보를 의미하지 않는다. 공개 요약과 mapping-preview는 원본 ID의 해시를 내보내지 않고 자료 계층·테이블·행 번호로 추적한다. 행 번호와 원 행의 무염 SHA-256은 익명화가 아니다. 원문이 알려진 경우 행 해시를 대조할 수 있고 참조 정보와 결합하면 추론 위험이 있어 접근 범위와 공개 적합성을 별도로 검토해야 한다.

## 재현 명령과 격리 환경

동결 ZIP은 저장소 밖의 읽기 전용 경로로 제공한다. 각 명령은 핀된 D-6에서 내장 D-5·D-4·D-3·D-2를 읽으며 새 파일을 만들 때 기존 경로를 덮어쓰지 않는다.

```sh
python3 scripts/i3_d6_dryrun.py validate /path/to/SCRIPTURA_D6_SCOPE_RESEARCH.zip
python3 scripts/i3_d6_dryrun.py dry-run /path/to/SCRIPTURA_D6_SCOPE_RESEARCH.zip --output /path/to/new-i3-quarantine.json
python3 scripts/i3_d6_dryrun.py mapping-preview /path/to/SCRIPTURA_D6_SCOPE_RESEARCH.zip --output /path/to/new-i3-mapping.json
python3 -m unittest discover -s tests -v
```

PostgreSQL의 007은 로컬의 폐기 가능한 합성 전용 DB(`scriptura_staging_` 접두사)에 004와 005를 선행 적용한 뒤에만 사용한다. 격리 DB 소유자 URL은 환경 변수로만 전달한다. 예시 명령은 **빈 시험 DB에서만** 실행한다.

```sh
psql -X -v ON_ERROR_STOP=1 "$SCRIPTURA_TEST_STAGING_OWNER_URL" -f db/004_d2_staging.sql
psql -X -v ON_ERROR_STOP=1 "$SCRIPTURA_TEST_STAGING_OWNER_URL" -f db/005_i1_research_guard.sql
psql -X -v ON_ERROR_STOP=1 "$SCRIPTURA_TEST_STAGING_OWNER_URL" -f db/007_i3_research_guard.sql
# 쓰기를 중단하고 004의 합성 staging 테이블이 둘 다 비어 있을 때만:
psql -X -v ON_ERROR_STOP=1 "$SCRIPTURA_TEST_STAGING_OWNER_URL" -f db/007_i3_research_guard.down.sql
```

007은 고정 연구 ZIP 해시의 staging 거부를 추가하는 방어 계층이며, 다른 입력이 합성임을 증명하거나 실제 자료를 적재할 권한을 부여하지 않는다. 007 롤백은 데이터가 있으면 거부한다. `tests/i3_staging_pg.py`는 고정된 전용 합성 DB명, 서로 다른 owner/writer URL, `SCRIPTURA_STAGING_APPROVED=synthetic-test-only`를 요구하며 실연구 ZIP을 열거나 저장하지 않는다. 명시된 해시를 넣어 거부 동작을 시험할 뿐이다.

합성 PostgreSQL 시험 [로그](reports/i3-staging-pg.log)는 11 PASS / 0 FAIL / 0 SKIP, 기존 합성 staging 회귀 [로그](reports/i3-staging-regression.log)는 5 PASS / 0 FAIL / 0 SKIP다. 기준 I-2.1 UI의 503·늦은 응답·초기화 회귀를 포함한 Chromium 권위 화면 7개와 기존 데모 화면 4개는 각각 PASS / FAIL 0 / SKIP 0이며 [로그](reports/i3-ui-regression.log)에 기록한다. 실제 연구 DB 시험이나 운영 반영 결과가 아니다. 기존 회귀를 포함한 Python 전체 시험은 166 PASS / 0 FAIL / 0 SKIP이며 그중 I-3 수신 합성 단위 35개를 포함한다. [전체 로그](reports/i3-python-all.log), [I-3 상세 로그](reports/i3-d6-unit.log)를 참조한다. 실자료 세 모드의 읽기 전용 시험 및 입력 전후 해시는 [로그](reports/i3-real-dryrun.log)를 참조한다. 원격 GitHub Actions는 개발 브랜치의 최종 실행 결과를 따른다.
