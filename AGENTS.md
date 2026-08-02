# 작업 규칙

## 문서 문체

- 제출용 문서는 명사 또는 명사구로 종결
- `~함`, `~임`, `~음`을 반복하는 기계적 명사화 금지
- 권장 예시: `결측으로 유지`, `MVP 범위에서 제외`, `원본 정의 유지`, `별도 지표로 관리`
- 설명보다 사실과 판단 근거 중심의 간결한 문장 사용

## Google Sheets API 작업

- 브라우저 없는 시트 조회·CSV 대조·서식 확인·업로드 절차는 `docs/P2/P2_구글시트_API_사용가이드.md` 참조
- 단순 확인은 `spreadsheets.readonly` 범위 사용. 업로드 CLI 일반 실행은 대상 탭 초기화와 재작성 작업이므로 명시적 쓰기 요청 없이 실행 금지
- 인증 JSON은 `secret/` 아래 로컬 파일로만 사용하고 내용 출력·채팅 첨부·A2A 전송·저장소 기록 금지

## 문제별 협업

- 전체 문제를 P1~P5로 구분
- 전체 진행 과정은 `사용자 프롬프트 요약 → 결정된 내용 → 실제 결과` 순서로 기록
- 문제 담당 세션에 전달한 핵심 프롬프트를 `docs/작업_타임라인.md`의 `핵심 프롬프트 요약`에 P2~P5별로 기록
- 사용자가 결정한 사안은 반드시 사용자 결정으로 명시하고 에이전트의 검토 결과처럼 표현 금지
- 파일 확인, A2A 확인, 도구 호출 등 내부 작업 내역은 진행 과정에서 제외
- 문제 담당 세션에 범위·결정사항·제외사항·반환 형식을 명시해 인수인계
- 담당 세션의 반환 전까지 해당 문제의 구현 파일과 충돌하는 작업 금지
- 반환 시각, 소요 시간, 결과, 생성·수정 파일, 검증 결과를 `docs/작업_타임라인.md`에 기록
- 문제별 에이전트 기록은 문제당 한 행만 사용하고 후속 작업은 기존 행에 누적
- 반환 결과의 채택·수정·보류 판단은 헤드 에이전트가 문서에 반영

## 파일 배치

- 작업 시작 전 `docs/architecture/FILE_TREE.md` 확인
- 루트 신규 파일 생성 금지
- 루트 허용 항목: `AGENTS.md`, `.gitignore`, `README.md`, 프로젝트 설정, 사용자 실행 진입점, 과제 제공 `TalkFile_*`
- 설계·검토·진행 문서: `docs/`
- 문제별 문서: `docs/P1/`부터 `docs/P5/`
- 구현 코드: `src/` 아래 기능별 디렉터리
- 테스트: `tests/` 아래 기능별 디렉터리
- 실행 스크립트: `scripts/`
- 로컬 입력: `data/input/`
- 정규화 결과: `output/normalized/`
- 보고 결과: `output/reports/`
- 실행·검증 로그: `output/logs/`
- 루트와 `src/` 내부에 실행 결과, 임시 파일, `__pycache__` 생성 금지
- 새 경로 생성 또는 파일 이동 전 A2A `touch` 등록

## 문제별 경로

- P1: `docs/P1/`
- P2: `src/ingestion/`, `src/normalization/`, `src/validation/`, `src/outputs/`, `tests/normalization/`, `tests/integration/`, `docs/P2/`
- P3: `src/metrics/`, `tests/metrics/`, `docs/P3/`
- P4: `src/comparison/`, `tests/comparison/`, `docs/P4/`
- P5: `src/reporting/`, `tests/reporting/`, `docs/P5/`
- 전체 파이프라인과 공통 설정: 헤드 에이전트 관리
