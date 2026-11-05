# 자료원 수집·권리·검증 정책 v0.1

## 수집 이전 조건

- 자료원별 이용 약관, 데이터 판본, 라이선스, 이용 목적/지역/기간, 크롤링·API·캐시·임베딩·재배포 제한을 확인한다.
- 합법적 접근과 복제 권한은 별개다. 무료 공개 PDF라도 전문 보관·AI 색인·배포가 허용된 것은 아니다.
- 무허가 수집을 지시하지 않는다. `metadata_only`를 기본값으로 시작한다.
- 단편 인용을 포함한 저장·공개는 해당 국가의 법률 및 실제 약관에 맞게 검토한다.
- '개인 연구용', '비상업적' 표시만으로 이용이 무조건 허가되지 않는다.
- 수집할 수 있는 범위를 벗어나는 외부 API 우회, 인증 우회, 속도제한 회피를 금지한다.

## 현재 파악한 자료원별 특징 (2026-11-05 확인)

- STEPBible-Data: 프로젝트 전체 데이터 저장소가 CC BY 4.0을 표기하고 있으며, 사용 시 출처 표시와 변경사항 기록을 요청한다. 실제 하위 데이터의 출처·세부 예외도 검토한다. https://github.com/STEPBible/STEPBible-Data
- Sefaria: 문헌 및 판본 **각각** 라이선스가 다르며 전체 통합 라이선스가 없다. 개별 버전의 `license` 필드 확인 필요. https://github.com/Sefaria/Sefaria-Export-Archive/blob/master/LICENSE.md
- Crossref: 공개 REST API로 서지 메타데이터 검색 가능. 일부 초록은 저작권 영향이 있을 수 있다. https://www.crossref.org/documentation/retrieve-metadata/rest-api/
- OpenAlex: 학술 서지와 연구 관계 메타데이터 소스 후보. 호출 예산/약관은 사용 직전 확인. https://help.openalex.org/api/
- Quran Foundation API: 2026-10-11 갱신된 개발자 약관에 따르면 일반 API 응답의 콘텐츠 보관 기간 제한(일반적으로 1주 이내)과 오프라인 동기화 별도 정책이 있고, 무단 장기 미러링/대량 데이터 재배포 및 독립 크롤링 제한이 있다. **프로토타입에 실제 경전 본문을 대량 수집하지 않는다.** https://api-docs.quran.foundation/legal/developer-terms/

## 시범 프로젝트의 실제 수집 원칙

- 처음에는 자료원 메타데이터만 등록한다.
- 권리가 검증된 일부 공개 자료에 한하여 원문을 수집한다.
- 저작권 제한 문헌은 DOI, 서명, 학술 검색 주소, 자료 위치, 저자가 주장한 바에 대한 독자적인 짧은 요약으로 연결한다. 요약을 원문 대체 서비스로 배포하지 않는다.
- 생성 모델 입력에도 필요한 권한이 있는지 확인한다.
- 검수 없이 자동 작성된 주장과 관계는 `extracted` 상태로만 적재한다.
- 제3자 개인에 대한 비방·위험한 낙인으로 악용되지 않도록 '평가 주체가 누구인지'를 항상 표시한다.

## 승인 문서

신규 자료원으로부터 실제 본문을 일괄 수집하려면 다음 항목의 레코드가 있어야 한다: source_owner, endpoint/URL, terms_url, license, attribution, cache_retention, permitted_uses, prohibited_uses, reviewer, reviewed_at, approved_storage_policy. 누락 항목이 있으면 `pending_review` 상태에서 수집을 제한한다.
