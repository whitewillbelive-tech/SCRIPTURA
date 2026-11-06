# Gate I-2.1 — 권위 비교 UI 오류 복구

기준 저장소 `whitewillbelive-tech/SCRIPTURA`, 기준 브랜치 `codex/scriptura-i2-authority`, 기준 커밋 `9731013f9675c3e16375db690f9fd09835c5065a`. 수정 브랜치 `codex/scriptura-i2-1-ci-repair`. Work D-5·D-6 및 기존 연구 자료와 운영 DB를 변경하지 않았다. UI 검증은 합성 데이터만 사용했다.

## 실패 조사

실패한 [Actions 42145882624](https://github.com/whitewillbelive-tech/SCRIPTURA/actions/runs/42145882624)의 공개 작업 화면은 `Test demo UI in Chromium` 실패를 보여준다. 상세 step 로그는 HTTP 404로 열리지 않았다. 첨부 인계서가 기록한 오류는 `tests/ui-i2-authority.browser.cjs:68`의 `1 !== 0`이며, 원격 로그에서 독립 확인하지는 못했다. 직전 성공 커밋 `0a547c3bcdc453a2e267abe619d71021b99c405d`와 기준 커밋은 `I2_REPORT.md`만 다르고 UI 및 테스트 blob은 동일하다. [기준 CI 관찰](reports/i2-1-ci-baseline.log).

독립 합성 브라우저에서 원본 테스트를 각 커밋마다 10회 실행했다. `9731013`: 6회 PASS, 4회 FAIL(그중 `1 !== 0` 3회, alert 중복 strict-mode 1회). `0a547c3`: 5회 PASS, 5회 FAIL(그중 `1 !== 0` 3회, alert 중복 2회). 각 실패 실행의 실패는 5개 시험 중 마지막 하나였다. [개별 로그 및 합성 trace·스냅샷](reports/i2-1-baseline/).

503을 의도적으로 보류한 실험에서 기존 범위 없는 `getByRole('alert').waitFor()`가 Next.js route announcer의 shadow DOM 알림에 대해 **503 응답 전에** 끝났다. 따라서 기존 테스트가 실제 오류 처리 완료 전에 카드 개수를 단정할 수 있음을 재현했다. 이후 503 처리 완료 시 실제 오류 안내와 카드 0개를 확인했다. [요청·응답 및 DOM 순서](reports/i2-1-race-repro.log), [재현 스크립트](reports/i2-1-race-reproducer.cjs). 이는 실제 경합의 증거이지만, 원격 회차의 상세 로그가 없어 그 회차에서 정확히 같은 사건 순서를 독립 확정하지는 않는다.

## 수정

- 시험은 실제 503 응답을 기다리고 `해석 비교` 영역의 정확한 오류 안내와 카드 0개를 확인한다. 이후 이미 기본값인 상태에서 초기화를 다시 눌러 실제 200 응답과 결과 복구도 검증한다.
- 이전의 성공·503 응답이 취소를 무시하고 최신 응답보다 늦게 도착하는 합성 시나리오를 시험한다. 기존 결과가 최신 필터나 오류 상태를 덮어쓰지 않아야 한다.
- 화면은 필터 변경/초기화 시 진행 요청을 즉시 취소·무효화하고 실제 `positions` 상태를 비운다. 503에서도 상태를 명시적으로 비우며 최신 요청의 응답만 적용한다. 기본값에서도 초기화로 재요청할 수 있다. 기존 코드 역시 실제 오류 렌더에서는 카드를 숨겼으므로, 이번 제품 보강과 재현된 테스트 경합을 구분한다. 새 결정적 시험을 기존 코드에 적용하면 503 후 오류·빈 카드 검사는 통과하지만 이미 기본값인 상태의 초기화 재시도가 요청을 만들지 않아 복구 검사가 실패했다(6 PASS / 1 FAIL, 복구 timeout 3초). [구 코드 비교](reports/i2-1-repaired-test-on-baseline.log).

## 검증

- Python 전체 회귀 131 PASS, 0 FAIL, 0 SKIP: [로그](reports/i2-1-python.log).
- 권위 단위 13 PASS, 0 FAIL, 0 SKIP: [로그](reports/i2-1-authority-unit.log).
- 수정 UI production 빌드 PASS, Chromium 권위 UI 10회 × 7개 = 70 PASS / 0 FAIL / 0 SKIP: [빌드](reports/i2-1-build.log), [반복 로그](reports/i2-1-ui-repeated.log).
- 기존 Chromium 데모 UI 4 PASS / 0 FAIL / 0 SKIP: [로그](reports/i2-1-ui-demo.log). 기존 API 6 PASS / 0 FAIL / 0 SKIP: [로그](reports/i2-1-npm-test.log).
- GitHub Actions 네 작업의 최종 결과는 수정 브랜치 push 이후 별도로 확인한다.

공식 기관 사이트의 프록시 CONNECT 403은 외부 본문 검증 차단으로 UI 경합과 무관하다. 이전 PR 생성의 GitHub GraphQL `Forbidden`도 별도 접근 차단이며 우회하지 않는다. `main` 병합과 운영 배포는 수행하지 않는다.
