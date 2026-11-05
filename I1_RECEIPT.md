# Gate I-1 — 동결 D-3 수신 검증 기록

기준은 `whitewillbelive-tech/SCRIPTURA`의 `codex/scriptura-d2-staging-bridge` 커밋 `0d39b743be21612f11fe25c16c53765a197088db`다. 독립 개발 브랜치에서 작업했다. Work D-4는 기다리거나 예측하지 않았다. 실제 D-3는 읽기 전용 검증·dry-run·쓰기 없는 가상 매핑에만 사용했고, 실제 자료의 DB 적재·정본 승격·운영 배포·main 병합은 0건이다.

## 수신·격리 결과

D-3 ZIP SHA-256 `baf206d2846544f1e1bb20622ac10c557394b71aa41cfd6e2be5bbafade347be`는 인계값 및 실행 전후 해시와 일치한다. 내부 manifest 69개와 내장 D-2 ZIP SHA `c8b64b9144367a8526c77b121b3343f04a7c683276f9fd239b2cc51458589a47`, 기준 12종 파일의 바이트 보존, baseline + delta = merged를 확인했다. 12종 2,528행과 별도 서지 인용 11행·정경 coverage 80행, 합계 **2,619항목 전부 격리**, 정본 적용 가능 0건이다. DOI 중복, ID·FK, 권리 CSV 15필드, coverage CSV/JSON 및 본문별 연결 건수를 검사했다.

[D3_MAPPING_REPORT.json](D3_MAPPING_REPORT.json)은 14종 가상 필드 매핑, 입력 집계·해시·검증 결과를, [QUARANTINE_SUMMARY.json](QUARANTINE_SUMMARY.json)은 행 번호·해시와 유형별 보류 사유를 담는다. 서지 인용은 주장 지지/반박과 분리한다. 서지 출처확인 7건 중 간선 자체 확인일 없는 2건은 원상태를 유지하고 별도 사유로 격리했다. 사유는 중복될 수 있다.

원 ID·참조·원본 파일/행·해시·원래 검증 상태 및 9행위 권리 결정과 본문/전통별 비교는 로컬 전용 `.local/i1/D3_PRIVATE_REVIEW_FINAL.json`에 있다. 디렉터리 0700, 파일 0600이며 Git에서 제외한다. 근거 없는 공식 교리를 생성하지 않으며 연구자 소속에 따른 주장 집계는 소속의 확정 여부와 주장 귀속 유형을 분리한 연관 관찰일 뿐 시기상 적용이나 공식 교리를 의미하지 않는다. 저장소의 공개 보고에는 실제 원 ID·URL·원문을 싣지 않았다.

## 입력의 의미와 한계

자료원은 180건이며 종류별 수는 매핑 보고서에 있다. 108개 DOI는 정규화 후 고유 식별자 108개이며, 입력상의 DOI metadata 상태는 source_checked 16·search_result_only 4·미기재 88이다. 확인된 locator와 연결된 DOI source 98건은 출처 메타데이터 경로이며 DOI의 독립 재검증이나 원문 확보·이용 허가가 아니다. 별도 외부 접근 검증은 수행하지 않았다. DOI 중복 검사는 대소문자·공백·일반 접두어 정규화 범위이며 퍼센트 인코딩이나 Unicode 변형까지 모두 판정하지 않는다.

12종 입력 2,528행에는 `data_class`가 명시되어 있지 않아 `metadata_candidate`로 임의 승격하지 않는다. 주장 40건 중 원본 검증 상태는 `source_verified` 36, 후보 4, 독립 `scholarly_reviewed` 0이며 나머지 2,579항목은 이 브리지의 분류상 unclassified로 보존한다. 출처 대조는 학술적 진실이나 심사 승격이 아니다. 각 주장에는 evidence가 연결되어 있고 36건은 verified evidence와 확인된 locator를 갖지만, 이는 구조 검사지 내용의 참이나 독립 심사 증명이 아니다. 정경 coverage 80행 중 주소 기록은 partial 13·미기록 67이며, 본문 79 및 주장–본문 연결 41은 행별 재계산했다. 기관별 목록 비교는 정경 동일성·본문 대응 확정이 아니다.

판본별 9행위 권리 판단은 unknown 1,588·conditional 46·allowed 4다. allowed 4는 browse/collect_metadata 각 2건으로, 저장·발췌·색인·임베딩·모델 전송·재배포·공개 링크에 전파하지 않는다. 독립 권리 승인 전 9행위는 모두 default deny다. 임의 자유 텍스트에 숨겨진 저작권 원문이나 사람 심사의 진정성을 자동 판별하지 않는다. 텍스트 원문·연구 ZIP/JSONL은 저장소에 싣지 않았다. [매핑 및 보류 상세](docs/I1_MAPPING_NOTES.md).

## 재현과 시험

`python3 scripts/i1_bridge_cli.py validate <D3.zip>`, `dry-run <D3.zip>`, `ingest-preview <D3.zip>`은 고정 해시만 받고 DB 연결·쓰기를 하지 않는다. `--output <새 파일>`, `--quarantine-output <새 파일>`, `--private-trace <이름.json>`으로 별도 산출물을 만들 수 있다. 비공개 파일은 `.local/i1`의 0700 디렉터리에서 0600·덮어쓰기 금지로 생성한다. 파일명에 외부 경로를 허용하지 않는다. 이 방식은 적대적인 로컬 사용자의 디렉터리 경합에 대한 완전한 보안 경계는 아니다.

- I-1 신규 합성 단위 **47 PASS / 0 FAIL / 0 SKIP**, 기존 포함 Python 전체 **102 PASS / 0 FAIL / 0 SKIP**: [신규 테스트](reports/i1-new-tests.log), [전체 테스트](reports/i1-unit-all.log).
- 별도 synthetic PostgreSQL 17에서 005 가드·롤백 8단계, 기존 004 롤백 7단계·제한 역할 적재 5개·CLI 멱등 2회 PASS: [i1-staging.log](reports/i1-staging.log), [i1-staging-ci-sequence.log](reports/i1-staging-ci-sequence.log). 실제 D-3를 DB로 전송하지 않았다.
- S-1B.2 기준 합성 회귀에서 Python 55, 권리 3, 기존·PostgreSQL API 각 6, 기존·PostgreSQL UI 각 4 PASS. 기존 DB 무결성 14·S-1B.1 26그룹·주소 4, 001–003 적용/롤백/재적용 및 빌드 PASS. [회귀 로그](reports/)의 `i1-regression-*` 참조.
- 합성 복합 부하 10,381행 0.291초/43,640 KiB, 103,855행 3.312초/295,420 KiB PASS. 그래프·권리·FK를 함께 확장한 각 1회 검증기 시험이며 실제 자료·DB 성능이 아니다. [규모 시험](docs/I1_SCALE_TEST.md), [10k](reports/i1-benchmark-10k.json), [100k](reports/i1-benchmark-100k.json).
- 세 읽기 명령과 입력 해시 보존: [i1-d3-receipt-check.log](reports/i1-d3-receipt-check.log). CI는 합성 자료만 사용하도록 구성했으며 현재 실행 상태는 원격 workflow를 참조한다.

[005 가드 안내](docs/I1_STAGING_GUARDS.md)는 고정 D-3 해시의 합성 적재 경로 차단과 운영 보안상 한계를 설명한다. 내부 테스트 API에 대한 임의 재포장이나 고권한 DB 직접 SQL까지 방지한다고 주장하지 않는다. 사람의 학술·권리 심사, 적대적 동시성, 실제 자료 정본 적재 및 공개는 **PENDING**이다.
