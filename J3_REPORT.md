# Gate J-3 — D-9 비공개 탐색과 연구 경계 기록

기준 저장소는 `whitewillbelive-tech/SCRIPTURA`, 기준 브랜치는 `codex/scriptura-j2-private-candidate-preview`다. 별도 개발 브랜치에서 고정 D-9과 내장 D-8을 읽기 전용으로 검토하고 Work D-10을 기다리거나 추정하지 않는다. 정본 승격, 운영 DB 쓰기, 공개 배포와 `main` 병합은 승인하거나 수행하지 않는다.

## 처리 범위

기존 D-8의 주장 170건과 서지 338건을 유지하면서 D-9 신규 주장 6건과 출처 14건을 별도 단계로 수신하도록 구현한다. D-9 ZIP은 기존 기준본을 포함하므로 이를 중복 반입하지 않는다. 자료 구조·중복·권리·출처·공동체 자기 진술·개인 의견·외부 평가와 상호 참조는 원래 단계·대상·범위를 구별한다. 실제 자료의 진실, 공식 교리, 인적 학술 심사나 이용권을 자동 확정하지 않는다.

인계에 기록된 D-9 필드 관찰 1,270건은 `unmapped` 510, `unknown` 751, `metadata_candidate` 9, `candidate_visible_local` 0이다. 후보 9건은 화면 표시 허가가 아니다. `candidate_visible_local`에는 필드·판본·행위·목적·관할·증거·검토 주체 등 개별 근거가 필요하며, 누락·충돌 또는 목적 밖 사용은 거부한다. Work D-10의 결과는 입력하지 않으며 합성 자료로만 장래 승인 구조를 검증한다.

Windows 설치·한 줄 시작·수용 확인은 [Windows 안내](docs/J3_WINDOWS_ACCEPTANCE_KO.md)를 참조한다. 이 실행 환경에는 Windows 호스트가 없어 실제 Windows 실행은 **NOT_RUN**이다. 실행기 모의 시험은 Windows 실기기 성공을 뜻하지 않는다. 클라우드 localhost는 사용자 PC의 주소가 아니다.

## 연구 경계 사고 — FAIL

이전 Work D-9의 자체 보고에는 한시 수신 파일의 일부 헤더와 Base64 일부가 모델 대화 문맥에 들어갔다는 기록이 있다. 이 보고서는 해당 내용이나 식별 정보를 재현하지 않는다. 이후 사본을 삭제해도 이미 있었던 전달을 되돌릴 수 없으며, 이 기록만으로 공개 유출이나 법적 침해가 독립적으로 확정된 것은 아니다.

이번 J-3 개발 중에도 별도의 사고가 발생했다. D-8 처리 함수의 반환형을 잘못 다뤄 ID·URL·자유 노트·서지 필드가 포함된 연구 메타데이터가 도구 출력으로 나갔다. 원 출력은 약 11,941토큰이었고 모델에 전달된 출력은 500토큰 예산으로 잘려 실제 전달 레코드 수는 확인되지 않는다. 전문이 전달됐다는 증거는 없으며 부분 인용 여부도 확인되지 않았다. 이 문서에는 실제 값·문헌 ID·주소·경로·원시 해시를 재현하지 않는다. 이미 도구·모델 문맥에 전달된 내용을 삭제로 되돌릴 수는 없고, 이 기록만으로 공개 유출이나 법적 침해를 확정할 수 없다.

실자료를 DB나 Git에 쓰려는 작업은 수행하지 않았지만 공개 변경분에 실제 내용이 남지 않았다는 주장은 별도 검증이 필요하다. 이후에는 검사 값을 모델이나 로그로 출력하지 않고 메모리 내 집계와 합성 자료를 사용한다. 이 사고 때문에 **`RESEARCH_BOUNDARY`는 FAIL**이다. 후속 재발 방지나 CI 성공으로 과거 노출이 없어지는 것은 아니다.

## 확인 상태

| 검증 항목 | 판정 | 근거 또는 제한 |
|---|---|---|
| 동결 D-9 수신과 기존 D-8 보존 | PASS | 메모리 검증에서 D-8 후보 508개가 보존되고 D-9 신규 주장 6개·출처 14개가 별도 후보로 연결됐다. |
| 개별 표시 적격성 | PASS | D-9 입력의 `candidate_visible_local`은 0이며, `metadata_candidate`만으로 실제 필드를 표시 승인하지 않는다. 이후 승인 구조는 합성 자료로 검증한다. |
| 원본 의미·출처/근거 유형 대응 | PENDING | 엄격한 안전 enum에 맞지 않는 기존 후보 투영의 `source_kind` 400건과 `evidence.kind` 126건은 미분류다. 기존 분류별 검색의 세분화가 줄어들며 값을 추정해 복원하지 않는다. 실제 D-8·D-9의 DOI·출판 연도·문헌 위치도 개별 표시 자격이 없어 가려지며 값 기반 검색은 불가하다. 권리·공식성·학술 심사와 실제 원문 이용은 별도 검토가 필요하다. |
| 연구 데이터의 모델 문맥 경계 | **FAIL** | 이번 개발 중 별도 연구 메타데이터 출력 사고가 발생했으며 위에 기록했다. 이후 검증 통과로 과거 전달을 되돌릴 수 없다. |
| Windows 실기기 | NOT_RUN | Windows 호스트가 없어 합성 모의 실행기 시험과 사용자가 수행할 수용 절차만 제공한다. |
| 최종 GitHub Actions | PENDING | 최종 개발 브랜치의 자동 검증을 별도 확인한다. |

- Windows 실행기: 합성 모의 흐름 **8 PASS / 0 FAIL / 0 SKIP**. [로그](reports/j3-windows-launcher.log). 최초 시험에서는 병렬 개발 중 바뀐 loader 함수명 때문에 7개 중 2개가 오류였고, [초기 로그](reports/j3-windows-launcher-initial.log)를 보존한 뒤 최종 함수명에 맞춰 재실행했다. 실제 Windows는 **NOT_RUN**이며 진입점과 수용 절차는 [Windows 안내](docs/J3_WINDOWS_ACCEPTANCE_KO.md)를 따른다.
- J-3 합성 브라우저: 시스템 Chromium으로 **9 PASS / 0 FAIL / 0 SKIP**. [로그](reports/j3-ui-browser-independent.log). 처음에는 Playwright의 기본 브라우저가 설치되지 않아 6개가 실패했다. [초기 로그](reports/j3-ui-browser-initial.log). 병렬 수정 중 backend의 구문 오류로 시작하지 못했던 [별도 중간 로그](reports/j3-ui-during-edit.log)도 보존한다. 시스템 Chromium을 명시한 최종 코드 재실행이 위와 같이 통과했다. 실제 연구 ZIP과 원문은 CI에 넣지 않는다.
- 기준 J-2 합성 브라우저 14개, 기존 Next 데모 4개, I-2.1 권위 UI 7개, 기존 합성 API 6개 PASS / FAIL 0 / SKIP 0. [J-2 로그](reports/j3-j2-ui-regression.log), [데모 로그](reports/j3-prior-demo-ui.log), [권위 UI 로그](reports/j3-prior-i2-ui.log), [API 로그](reports/j3-prior-api-regression.log). Next production build는 격리된 기준 커밋 사본에서 [PASS](reports/j3-next-build.log)했다.
- 최종 전체 Python 합성·기존 회귀 **318 PASS / 0 FAIL / 0 SKIP**. [전체 로그](reports/j3-python-all.log). API와 UI를 보강하던 중 실행한 317개 테스트도 [중간 로그](reports/j3-python-during-edit.log)에 보존한다.
- 실제 D-9 로컬 조회: 메모리에서 원본을 읽기 전용으로 확인한 결과 D-8 후보 508개가 보존되고 D-9 신규 주장 6개와 출처 14개를 포함한 후보 528개가 확인됐다. 신규 판본 15개와 권리 판단 135개, 신규 주장 6개의 출처 연결을 대조했다. 인증된 루프백 브라우저에서 실제 주장과 문헌 후보를 각각 열고 이름·권리의 보류 상태를 확인했다. [실자료 집계 로그](reports/j3-real-local.log)는 민감한 기록·경로·비밀이나 스크린샷을 포함하지 않는다. 자동 승격은 없다.
- GitHub Actions, PR 및 공개 변경분의 독립 누출 검사는 개발 브랜치의 최종 결과를 따로 확인한다.
