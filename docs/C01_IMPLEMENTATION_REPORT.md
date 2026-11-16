# C-01 구현 및 검증 범위

기준 브랜치는 `codex/scriptura-k37-private-candidate-fix`, 기준 커밋은 `a64b7d5f59261cfebf50fa64ac539c898ff7e934`이다. 기존 비공개 탐색기에 추가했으며 운영 배포 또는 `main` 병합은 하지 않는다.

## 구현

- `c01_receipt_adapter`는 신뢰된 기존 D13/D14~D16 전용 읽기 경로와 K3 JSONL 수신을 명시적으로 구분한다. `ResearchCatalog`는 인증된 기준 스냅샷으로부터 단일 프로세스에서 낙관적 비교와 원자적 메모리 세대 전환을 제공한다. [수신 계약](C01_RECEIPT_CONTRACT.md), [어댑터](C01_ADAPTER_CONTRACT.md)
- 지식 그래프는 정확한 코퍼스·장절 체계와 주소를 사용하고 출처 사슬 및 신뢰된 검증 없이 발화자·공식성·직접 반론·정렬을 확정하지 않는다. [그래프 계약](C01_GRAPH_CONTRACT.md)
- `GET /api/research-graph`는 기존 안전한 본문 비교 투영의 주장 연결만 미확정 후보로 반환한다. 아직 모든 연구 관계와 DB를 연결하지 않는다.
- `POST /api/research-analysis`는 인증된 로컬 요청과 안전한 메타데이터만 사용한다. 모델 공급자는 기본 미연결이며 분석이 생성됐다고 표시하지 않는다. 공급자 계약의 인용 검사는 식별자의 존재만 검증하므로 의미적 근거 일치와 모든 프롬프트 인젝션 방어를 보증하지 않는다. 외부 모델 전송은 구현하지 않았다.
- 기존 비교 화면에 질문 및 관련 주장 경로를 추가했다. 확인되지 않은 관계를 직접 반박으로 표시하지 않는다.
- `db/004_c01_graph_provenance.sql`은 수신 버전과 출처 기여자·기관 관계를 추가한다. 로컬 합성 PostgreSQL에서만 검증했다. 실제 정본 DB 적재와 행별 영속 버전 연결은 구현하지 않았다.

## 재현 및 결과

- Python 합성 전체: `python3 -m unittest discover -s tests -v` — 625 PASS / 0 FAIL / 0 SKIP. [로그](../reports/c01/python.log)
- 합성 브라우저: `CHROMIUM_PATH=/usr/bin/chromium node --test tests/ui-real-integration.browser.cjs` — 8 PASS / 0 FAIL / 0 SKIP. [로그](../reports/c01/browser-synthetic.log)
- 합성 그래프 및 기존 비교 성능: `python3 scripts/benchmark_c01_graph.py --records 200000`, `python3 scripts/benchmark_k7_comparison.py --records 200000`; 1만·10만·20만 건 각각 별도 실행. [그래프](../reports/c01/graph-200000.log), [비교](../reports/c01/comparison-200000.log)
- PostgreSQL 17 일회성 합성 환경에서 001~004 적용, `tests/database_c01.sql`, 빈 004 롤백·재적용과 데이터가 있을 때 롤백 거부를 확인했다. 운영 DB는 사용하지 않았다.
- 실제 Work ZIP을 읽기 전용으로 사용한 Linux Chromium 표본 시험에서 제목·작성자 검색, 본문 비교 두 그룹, 허용 논거의 안전 투영 일치, 관련 주장 이동과 모델 미연결 응답을 확인했다. 원본 ZIP은 불변이었고 외부 요청은 0건이었다. 구형 하네스는 모든 논거가 보류돼야 한다는 가정 때문에 실패했으며, 현재 기준 정책을 반영해 재검증했다. 표본 검사는 전체 데이터의 비노출을 증명하지 않는다. [비식별 로그](../reports/c01/private-browser-acceptance.log)
- 이전 사용자 Windows 수용 결과와 이번 Linux 자동시험은 별개다. 이번 변경의 사용자 Windows 실기기 검증은 미실행이다.

실제 Work ZIP과 연구 내용은 커밋이나 공개 CI에 포함하지 않는다. Work 원본을 완전한 공통 정본으로 손실 없이 변환하는 어댑터, 다중 프로세스·영구 정본 관리자, 실제 모델 연결과 의미 검증, 외부 AI 전송 권리 승인, 전체 DB·UI 지식 그래프 연결은 아직 미구현이다. 실제 자료 검증은 합성 결과와 별도 집계한다.
