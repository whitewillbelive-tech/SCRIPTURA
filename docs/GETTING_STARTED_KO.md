# SCRIPTURA 착수 절차 — 실행 안내

## 착수 전 확인

현재 결과물은 '데이터 표준 + DB DDL 초안 + 합성 테스트 데이터 + 자동 계약 테스트 + 작업 지시'까지 완료된 단계입니다. GitHub 저장소나 Site를 새로 게시하지 않았으며, 실제 외부 학술 자료도 아직 가져오지 않았습니다.

## 사용자가 수행할 작업

**1.** 압축파일 `SCRIPTURA_STARTER_v0.1.zip`을 내려받습니다.

**2.** 새로운 ChatGPT Work 작업에서 `prompts/WORK_S1.md` 내용을 붙여 넣고, 같은 ZIP 파일을 첨부합니다. 제목 예: `SCRIPTURA — 01 학술 자료·원천 조사`. 작업의 목표는 자료원·저작권·본문 주소 구조·시범 본문 2개의 검증 가능한 자료 확보입니다.

**3.** 새로운 Codex 개발 대화에서 `prompts/CODEX_S1.md`를 붙여 넣고, 같은 ZIP 파일을 첨부합니다. 제목 예: `SCRIPTURA — 02 데이터·UI 개발`. 신규 저장소가 필요하지만 기존 앱과 분리하여 작업합니다. Codex가 GitHub PR 권한을 갖지 못하면 코드 산출물과 차단 보고서를 우선 확보합니다.

**4.** Work와 Codex는 **독립적으로 동시 진행 가능**합니다. Codex는 처음에 합성 fixture를 사용하고, Work가 제공할 실제 자료를 검증 후 나중에 접합하도록 지시했습니다. Work의 권리 검토가 끝나기 전 실제 원문을 자동 수집하거나 서비스를 공개하면 안 됩니다.

**5.** 완료 보고서들을 관리 Chat에 가져오면 S-1A/S-1B Gate를 검수합니다. 그 후 두 시범 본문의 실제 학술 자료를 접합하고, AI 검증 단계인 S-2로 넘어갑니다.

## 로컬 개발자를 위한 실행

```bash
cd SCRIPTURA_STARTER_v0.1
python scripts/validate_fixture.py fixtures/demo_valid.json
python -m unittest discover -s tests -v
```

Python 3.10 이상 권장. 별도의 외부 패키지/네트워크 없음. PostgreSQL 서버에서 DDL을 실행·검증하는 작업은 Codex 단계의 범위입니다.

## 사용자에게 불필요한 작업

현 단계에서는 Windows에 PostgreSQL을 직접 설치하거나, 학술 논문 원문을 수작업으로 다운받거나, 새 웹사이트를 직접 게시할 필요가 없습니다.

## 결정 유보 사항

- 최종 프로젝트 명칭 SCRIPTURA (현재 가칭)
- 운영 서버 및 호스팅/도메인
- 유료 학술 콘텐츠 이용 계약
- AI가 내릴 평가의 최종 신학적 권위와 사용자에게 보여줄 기본 판정 기준
- 대규모 자료 수집 시작 시점
