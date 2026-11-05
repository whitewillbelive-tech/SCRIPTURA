# MVP API 계약 초안 — Gate S-1B

이 문서는 신규 독립 개발 환경의 API 초안이다. 아직 서비스 구현은 없다. 반환값은 반드시 출처·검증 상태·권리 제한을 포함해야 한다.

## 읽기 API (초안)

- `GET /api/v1/corpora` — 성경/꾸란/기타 코퍼스 목록
- `GET /api/v1/reference-schemes?corpus_id=` — 선택 가능한 주소 체계
- `GET /api/v1/passages?scheme_id=&ref=` — 정확한 주소 검색, 동일 표기 시 다중 후보 응답
- `GET /api/v1/passages/{id}/alignments` — 다른 체계의 대응 주소와 매핑 상태
- `GET /api/v1/passages/{id}/interpretations?tradition_id=&method=` — 본문에 대한 주장, 귀속(공식/개인), 검증 상태
- `GET /api/v1/claims/{version_id}` — 주장의 특정 버전/귀속/근거/반론/원문 위치
- `GET /api/v1/graph?passage_id=&depth=1` — nodes/edges with edgeType, sourceLocatorId, reviewStatus
- `GET /api/v1/sources/{id}` — 서지·이용 권리·허용 범위. 원문 전체 반환은 별도 라이선스 검사 필요

## 관리자 전용 (초안)

- `POST /api/v1/admin/imports/validate` — 사전 검증 및 수집 정책 시뮬레이션
- `POST /api/v1/admin/claims` — 검수 전 상태로 등록
- `POST /api/v1/admin/reviews` — 검증·반려 이벤트 append-only 등록
- `GET /api/v1/admin/audit?entity_id=` — 데이터 원천·변경 내역

## 불변 조건

- 일반 조회는 기본적으로 `source_verified` 이상의 주장을 중심으로 제공하되, 검증 대기 자료는 관리자 또는 명시적인 사용자 선택으로만 보여준다.
- 검증된 원본 출처와 AI 요약은 서로 다른 타입으로 표현한다.
- 그래프의 모든 연결에는 `relation_type`, `review_status`, `rationale`, 가능한 한 `source_locator_id`가 있다.
- 타 전통의 주장에 대한 비판은 평가의 발화 주체·시점이 있는 `claim`으로 저장한다.
- 저작권 미확인 원문, 전문 텍스트, 허용 범위를 넘는 자동 요약은 응답하지 않는다.
- 출처 없는 자동 AI 답변은 이 Gate의 구현 대상이 아니다.

## 응답 모델 예시(합성 형식)

```json
{
  "passage_id": "psg:isa714",
  "reference_scheme_id": "ref:osis-demo",
  "external_ref": "Isa.7.14",
  "interpretations": [
    {
      "claim_version_id": "clv:demo-a-1",
      "attribution_kind": "individual_opinion",
      "review_status": "extracted",
      "display_warning": "SYNTHETIC / UNVERIFIED / NOT A REAL SCHOLARLY CLAIM",
      "source_locator_ids": ["loc:demo-a"]
    }
  ]
}
```

운영에서는 위 합성 자료를 실제 학술 주장처럼 노출하면 안 된다.
