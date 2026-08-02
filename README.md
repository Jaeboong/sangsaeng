# 상생 마케팅 리포트 자동화 MVP

광고 채널별 원본 CSV를 공통 형식으로 정규화하고 CPA·ROAS·전환율과 전주 대비 증감을 계산한 뒤, 로컬 CSV와 구글시트에 반영하는 Windows 실행 파일.

## 제출물

1. [설계 메모](설계메모.md)
2. [동작 결과물](Sangsaeng_Report_Automation.exe) · [Google Sheets 결과](https://docs.google.com/spreadsheets/d/1fInri5U_FMkxOEE0x4ChEBXyV6MkdY3dPLUgZAoNXMw/edit?usp=sharing)
3. [AI 활용 기록](AI_활용기록.md)

## 구현 범위

- 지원 채널: GA4, Meta, 네이버 검색광고, 네이버 GFA, 카카오 모먼트
- P2: 채널 자동 판별, 공통 스키마 정규화, 구글시트 채널별 탭 반영
- P3: CPA·ROAS·전환율 계산
- P4: 동일 채널·캠페인의 전주 대비 증감과 증감률 계산
- P1 제외: 채널 API 연동 자산 부재에 따른 관리자 화면 수집 자동화 제외
- P5 제외: 주요 변화 선택과 성과 맥락 해석을 사람의 판단 영역으로 유지

## 처리 흐름

```text
data/input의 원본 CSV
→ 헤더 기반 채널 판별
→ 채널별 공통 스키마 정규화
→ CPA·ROAS·전환율 계산
→ 전주 대비 비교
→ 전체 결과 검증
→ 로컬 CSV 저장
→ 구글시트 6개 탭 반영과 재조회 검증
→ output/logs 실행 기록
```

## 사전 준비

### 1. 실행 환경

- Windows 10 이상
- 인터넷 연결: 실제 구글시트 업로드 시 필요
- 최종 사용자 Python 설치 불필요

### 2. 환경 파일

실행 파일과 같은 디렉터리의 `.env` 사용. 새 환경에서는 `.env.example`을 복사해 `.env`로 이름 변경 후 값 입력.

주요 설정:

```dotenv
DATA_INPUT_DIR=data/input
NORMALIZED_OUTPUT_DIR=output/normalized
REPORT_OUTPUT_DIR=output/reports
LOG_DIR=output/logs

GOOGLE_SHEETS_SPREADSHEET_ID=your_spreadsheet_id
GOOGLE_APPLICATION_CREDENTIALS=secret/service-account.json

UPLOAD_ENABLED=true
DRY_RUN=false

CURRENT_WEEK_START=
REFERENCE_DATE=
```

| 설정 | 의미 |
|---|---|
| `DATA_INPUT_DIR` | 원본 CSV 투입 디렉터리 |
| `NORMALIZED_OUTPUT_DIR` | 채널별 정규화 CSV 저장 디렉터리 |
| `REPORT_OUTPUT_DIR` | 파생 지표와 전주 비교 CSV 저장 디렉터리 |
| `LOG_DIR` | 실행 성공·실패 로그 저장 디렉터리 |
| `GOOGLE_SHEETS_SPREADSHEET_ID` | 구글시트 URL의 `/d/`와 `/edit` 사이 값 |
| `GOOGLE_APPLICATION_CREDENTIALS` | 서비스 계정 JSON 파일 경로 |
| `UPLOAD_ENABLED` | `true`이면 구글시트 반영, `false`이면 로컬 결과만 생성 |
| `DRY_RUN` | `true`이면 시트 입력 데이터 검증까지만 진행 |
| `CURRENT_WEEK_START` | 금주로 사용할 월요일. 예: `2026-07-20` |
| `REFERENCE_DATE` | 해당 날짜 기준으로 완전히 종료된 최신 주간 선택 |

`CURRENT_WEEK_START`와 `REFERENCE_DATE`는 둘 중 하나만 사용. 모두 비어 있으면 입력 데이터에서 확인되는 최신 완전 주간 선택.

### 3. 구글 서비스 계정

1. Google Cloud에서 Google Sheets API 사용 설정
2. 서비스 계정 JSON을 저장소의 `secret/` 아래 배치
3. JSON의 `client_email` 값을 대상 구글시트의 편집자로 등록
4. 대상 구글시트 ID와 JSON 경로를 `.env`에 입력

서비스 계정 JSON, `.env`, 원본 데이터와 실행 결과는 Git 제외 대상.

## 원본 CSV 준비

1. `data/input/`의 이전 CSV 제거
2. 새로 내려받은 채널별 CSV 저장
3. 지원 채널 5종의 파일 존재 확인

파일명보다 CSV 헤더 조합을 기준으로 채널 판별. 같은 날짜·채널·캠페인 키가 둘 이상이면 자동 합산 없이 실행 중단.

## 실행 방법

### 더블클릭 실행

[`Sangsaeng_Report_Automation.exe`](Sangsaeng_Report_Automation.exe) 실행.

별도 Python 설치와 터미널 명령 없이 실행. 완료 또는 실패 결과를 대화상자로 표시. 실패 시 대화상자에 실제 원인과 로그 위치 표시.

코드 서명 인증서가 없는 실행 파일이므로 다른 PC에서 Windows SmartScreen 경고가 표시될 수 있음. 저장소 출처와 SHA-256 확인 후 `추가 정보 → 실행` 선택.

### 개발자용 소스 실행

```powershell
scripts\run_pipeline.bat --no-pause
```

### 원격 쓰기 없는 사전 검증

`.env`에서 `DRY_RUN=true`로 변경한 뒤 실행 파일 더블클릭. 개발자용 명령:

```powershell
scripts\run_pipeline.bat --no-pause --dry-run
```

정규화·계산·로컬 결과 생성과 6개 탭 입력 검증까지 진행. 구글시트 변경 없음.

### 로컬 결과만 생성

`.env`에서 `UPLOAD_ENABLED=false`로 변경한 뒤 실행 파일 더블클릭. 개발자용 명령:

```powershell
scripts\run_pipeline.bat --no-pause --no-upload
```

## 결과 확인

### 로컬 파일

| 결과 | 경로 |
|---|---|
| GA4 정규화 | `output/normalized/ga4_normalized.csv` |
| Meta 정규화 | `output/normalized/meta_normalized.csv` |
| 네이버 검색광고 정규화 | `output/normalized/naver_search_normalized.csv` |
| 네이버 GFA 정규화 | `output/normalized/naver_gfa_normalized.csv` |
| 카카오 모먼트 정규화 | `output/normalized/kakao_moment_normalized.csv` |
| CPA·ROAS·전환율 | `output/reports/derived_metrics.csv` |
| 전주 비교 | `output/reports/weekly_comparison.csv` |
| 실행 로그 | `output/logs/pipeline_*.log` |

### 구글시트

- 채널 탭: `GA4`, `Meta`, `네이버 검색광고`, `네이버 GFA`, `카카오 모먼트`
- 비교 탭: `전주비교`
- 기존 대상 탭의 값 초기화 후 전체 재작성
- 첫 행 고정, 필터, 숫자 형식, 열 너비, 기술 메타데이터 열 숨김
- 업로드 직후 API 재조회와 로컬 입력값 대조

`derived_metrics.csv`는 로컬 보고 결과. `전주비교` 탭에는 P3 계산 규칙을 재사용한 주간 파생 지표 포함.

## 계산과 데이터 보존 기준

- `CPA = 비용 합계 ÷ 전환 합계`
- `ROAS = 매출 합계 ÷ 비용 합계`
- `전환율 = 전환 합계 ÷ 클릭 합계`
- 행별 비율 평균이 아닌 원천 지표 합계 후 비율 계산
- 원본에 없는 값은 `0`이 아닌 결측으로 유지
- 0 분모, 필수 값 결측, VAT 기준 혼합, 전환 정의 혼합 시 계산 제외와 사유 기록
- GA4 주요 이벤트와 광고 채널 구매 전환의 강제 통합 제외
- VAT 포함·제외 금액의 강제 환산 제외

## 오류 처리

다음 조건에서 구글시트 쓰기 전 실행 중단:

- 입력 CSV 부재
- 지원 채널 누락
- 채널 판별 실패
- 날짜·채널·캠페인 중복
- 공통 스키마 불일치
- 파생 지표 또는 주간 비교 계산 실패
- 시트 입력 데이터 검증 실패
- 실제 업로드 설정에서 시트 ID 또는 인증 파일 부재

구글시트 업로드 후 값이 로컬 입력과 다르면 실패 처리. 원인 확인 전 반복 업로드 금지.

## 테스트

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m unittest discover -s tests/metrics -v
python -m unittest discover -s tests/comparison -v
python -m unittest discover -s tests/integration -v
```

검증 범위:

- 파생 지표 계산과 결측·0 분모·정의 혼합 경계값
- 최신 완전 주간, 명시 주간, 신규·미집행·전주 0 비교
- 5개 채널 입력부터 6개 구글시트 탭까지의 통합 흐름
- 검증 실패 후 업로드 차단
- 업로드 후 값 재조회 불일치 탐지

## 개발자용 실행 파일 재빌드

최종 사용과 무관한 개발자 절차.

```powershell
python -m pip install google-api-python-client google-auth pyinstaller
scripts\build_executable.bat
```

빌드 결과: 저장소 루트의 `Sangsaeng_Report_Automation.exe`.

## 프로젝트 구조

```text
src/pipeline.py                         전체 실행 제어
src/normalization/normalize_csvs.py     채널 판별과 정규화
src/metrics/calculate_metrics.py        CPA·ROAS·전환율
src/comparison/weekly_comparison.py     전주 비교
src/outputs/google_sheets.py            구글시트 출력
Sangsaeng_Report_Automation.exe         최종 사용자 실행 파일
scripts/executable_launcher.py          실행 파일 진입점
scripts/build_executable.bat             실행 파일 빌드
scripts/run_pipeline.bat                개발자용 소스 실행 진입점
tests/                                  단위·통합 테스트
docs/                                   설계·구현·작업 기록
```

## 관련 문서

- [설계 메모](docs/설계.md)
- [통합 파이프라인](docs/architecture/통합_파이프라인.md)
- [P2 정규화 설계 검토](docs/P2/P2_정규화_설계검토.md)
- [P2 구글시트 API 사용 가이드](docs/P2/P2_구글시트_API_사용가이드.md)
- [P3 파생 지표 구현 결과](docs/P3/P3_파생지표_구현결과.md)
- [P4 전주 비교 구현 결과](docs/P4/P4_전주비교_구현결과.md)
- [작업 타임라인](docs/작업_타임라인.md)
