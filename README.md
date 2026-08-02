# 상생 마케팅 리포트 자동화 MVP

채널별 CSV 5개를 지정 폴더에 넣고 실행파일을 더블클릭하면 데이터 정규화, 지표 계산, 전주 비교, Google Sheets 반영까지 한 번에 처리하는 Windows 프로그램.

## 사용 방법

프로젝트를 처음 받은 사용자를 기준으로 한 전체 실행 순서.

### 1. 프로젝트 폴더 준비

압축을 해제하거나 저장소를 내려받은 뒤 실행파일만 따로 이동하지 않고 전체 폴더 구조 유지.

GitHub에서 받은 폴더에 빈 디렉터리가 없다면 다음 폴더 생성.

- 프로젝트 루트의 `data` 폴더 아래 `input` 폴더
- 프로젝트 루트의 `secret` 폴더

```text
상생/
├─ Sangsaeng_Report_Automation.exe
├─ .env.example
├─ .env                      ← 2단계에서 생성
├─ data/
│  └─ input/                 ← 4단계에서 CSV 저장
├─ secret/
│  └─ service-account.json   ← 3단계에서 저장
└─ output/                   ← 첫 실행 시 자동 생성
```

### 2. `.env` 설정

1. Windows 파일 탐색기에서 `보기 → 표시 → 파일 확장명` 선택
2. `.env.example`을 복사
3. 복사본의 파일명을 `.env`로 변경
4. 파일명이 `.env.txt`가 아닌 `.env`인지 확인
5. 메모장으로 `.env` 열기

다음 항목을 실제 값으로 수정.

```dotenv
GOOGLE_SHEETS_SPREADSHEET_ID=https://docs.google.com/spreadsheets/d/your_spreadsheet_id/edit
GOOGLE_APPLICATION_CREDENTIALS=secret/service-account.json
UPLOAD_ENABLED=true
DRY_RUN=false
```

`GOOGLE_SHEETS_SPREADSHEET_ID`는 결과를 올릴 Google Sheets 문서의 고유 식별자. 시트 탭 이름이나 공유 이메일이 아닌 문서 주소에 포함된 값.

```text
Google Sheets 주소:
https://docs.google.com/spreadsheets/d/1AbCdeFGhijkLmNopQRstuVWxyz/edit

스프레드시트 ID:
1AbCdeFGhijkLmNopQRstuVWxyz
```

다음 두 입력 방식 모두 지원.

```dotenv
# ID만 입력
GOOGLE_SHEETS_SPREADSHEET_ID=1AbCdeFGhijkLmNopQRstuVWxyz

# 또는 Google Sheets 전체 주소 입력
GOOGLE_SHEETS_SPREADSHEET_ID=https://docs.google.com/spreadsheets/d/1AbCdeFGhijkLmNopQRstuVWxyz/edit
```

`GOOGLE_APPLICATION_CREDENTIALS`는 Google Sheets에 접근할 서비스 계정 JSON의 로컬 경로. 나머지 폴더 경로와 날짜 설정은 기본값 유지.

### 3. 서비스 계정과 Google Sheets 연결

이 단계는 최초 관리자 또는 개발자 1회 설정 권장.

1. Google Cloud에서 Google Sheets API 사용 설정
2. 서비스 계정 JSON 발급
3. JSON을 `secret/service-account.json`으로 저장
4. JSON의 `client_email` 값을 대상 Google Sheets의 편집자로 등록
5. `.env`의 시트 주소와 JSON 경로 재확인

서비스 계정 JSON 내용을 이메일, 채팅, GitHub에 첨부하지 않도록 주의.

### 4. 원본 CSV 저장

GA4, Meta, 네이버 검색광고, 네이버 GFA, 카카오 모먼트에서 같은 분석 기간의 CSV를 각각 다운로드.

새 CSV 5개를 `data/input`에 저장. 기존 CSV가 있다면 별도 폴더에 백업한 뒤 입력 폴더 밖으로 이동.

파일명 변경 불필요. CSV 헤더 기반 채널 자동 판별.

> [!WARNING]
> `DRY_RUN=false` 실행은 대상 Google Sheets의 `GA4`, `Meta`, `네이버 검색광고`, `네이버 GFA`, `카카오 모먼트`, `전주비교` 탭을 초기화한 뒤 전체 재작성. 운영 시트는 실행 전 사본 생성 권장.

### 5. 실행파일 더블클릭

[`Sangsaeng_Report_Automation.exe`](Sangsaeng_Report_Automation.exe)를 더블클릭. Python 설치와 터미널 명령 불필요.

- 성공: `처리가 완료되었습니다` 대화상자
- 실패: 실제 오류 원인과 최신 로그 위치가 포함된 대화상자

### 6. 결과 확인

- Google Sheets: 채널별 5개 탭과 `전주비교` 탭
- 로컬 결과: `output/normalized`, `output/reports`
- 실행 기록: `output/logs`

## 제출물

1. [설계 메모](설계메모.md)
2. [동작 결과물](Sangsaeng_Report_Automation.exe) · [Google Sheets 결과](https://docs.google.com/spreadsheets/d/1fInri5U_FMkxOEE0x4ChEBXyV6MkdY3dPLUgZAoNXMw/edit?usp=sharing)
3. [AI 활용 기록](AI_활용기록.md)

## 매주 반복 사용

최초 설정 이후의 반복 작업은 다음 4단계.

1. 이전 `data/input` CSV를 별도 폴더로 이동
2. 같은 분석 기간의 새 CSV 5개를 `data/input`에 저장
3. `Sangsaeng_Report_Automation.exe` 더블클릭
4. 완료 대화상자와 Google Sheets 결과 확인

실제 시트를 변경하지 않고 시험하려면 `.env`의 `DRY_RUN=true` 사용. 검증 후 실제 업로드는 `DRY_RUN=false`로 복원.

## 실행 전 확인

- 지원 채널 5종의 CSV가 각각 1개 이상 존재
- 같은 분석 기간의 CSV 사용
- `data/input`의 이전 실행 CSV 정리 완료
- `.env`와 서비스 계정 JSON 존재
- 서비스 계정 이메일에 대상 시트 편집 권한 부여
- 인터넷 연결 상태 확인
- 운영 시트 사용 시 사본 또는 백업 존재

같은 날짜·채널·캠페인 데이터가 둘 이상이면 자동 합산하지 않고 실행 중단.

## 결과 확인

### Google Sheets

| 탭 | 내용 |
|---|---|
| `GA4` | GA4 정규화 결과 |
| `Meta` | Meta 정규화 결과 |
| `네이버 검색광고` | 네이버 검색광고 정규화 결과 |
| `네이버 GFA` | 네이버 GFA 정규화 결과 |
| `카카오 모먼트` | 카카오 모먼트 정규화 결과 |
| `전주비교` | 채널·캠페인·지표별 전주 값, 금주 값, 증감, 증감률 |

첫 행 고정, 필터, 숫자 형식, 열 너비, 기술 메타데이터 숨김 적용. 업로드 직후 API 재조회와 로컬 입력값 대조.

### 로컬 파일

| 결과 | 경로 |
|---|---|
| 채널별 정규화 CSV | `output/normalized/` |
| CPA·ROAS·전환율 | `output/reports/derived_metrics.csv` |
| 전주 비교 | `output/reports/weekly_comparison.csv` |
| 실행 로그 | `output/logs/pipeline_*.log` |

## 오류 해결

### `CSV 파일 없음`

`data/input`에 CSV 저장 여부 확인. CSV가 다른 폴더에 있으면 입력 폴더로 이동 후 재실행.

### `지원 채널 누락` 또는 `채널 판별 실패`

지원 채널 5종의 CSV 존재 여부 확인. CSV를 Excel에서 다시 저장하면서 헤더가 변경되지 않았는지 확인.

### `서비스 계정 JSON 없음`

`.env`의 `GOOGLE_APPLICATION_CREDENTIALS` 경로와 `secret` 폴더의 JSON 파일명 확인.

### Google Sheets 권한 오류

서비스 계정 JSON의 `client_email`이 대상 시트의 편집자로 등록되어 있는지 확인.

### 기타 오류

1. `output/logs` 폴더 열기
2. 수정 시간이 가장 최근인 `pipeline_*.log` 열기
3. 마지막 `error=` 내용 확인
4. 원인 확인 전 실제 업로드 반복 실행 금지

다음 조건은 Google Sheets 쓰기 전 실행 중단 대상.

- 입력 CSV 부재 또는 지원 채널 누락
- 날짜·채널·캠페인 중복
- 공통 스키마 불일치
- 파생 지표 또는 주간 비교 계산 실패
- 시트 입력 데이터 검증 실패
- 실제 업로드 설정에서 시트 ID 또는 인증 파일 부재

## Windows 보안 경고

코드 서명 인증서가 없는 실행파일이므로 다른 PC에서 Windows SmartScreen 경고 표시 가능. 저장소 출처와 아래 SHA-256 확인 후 `추가 정보 → 실행` 선택.

```text
D6344F14DF5A483DD6DD96AD1D42CF4C46EF55065C824C72C35CD841E485EFA2
```

위 해시는 현재 저장소의 `Sangsaeng_Report_Automation.exe` 기준. 실행파일 재빌드 시 변경.

## 자동화 범위

- 지원 채널: GA4, Meta, 네이버 검색광고, 네이버 GFA, 카카오 모먼트
- 채널 자동 판별과 공통 스키마 정규화
- CPA·ROAS·전환율 계산
- 동일 채널·캠페인의 전주 대비 증감과 증감률 계산
- 채널별 Google Sheets 탭과 `전주비교` 탭 반영
- 채널 관리자 화면 수집 자동화 제외
- 주요 변화 선택과 성과 해석 문장 자동화 제외

처리 흐름:

```text
원본 CSV
→ 헤더 기반 채널 판별
→ 공통 스키마 정규화
→ CPA·ROAS·전환율 계산
→ 전주 비교
→ 전체 결과 검증
→ 로컬 CSV 저장
→ Google Sheets 반영과 재조회 검증
→ 실행 로그 저장
```

## 계산과 데이터 보존 기준

- `CPA = 비용 합계 ÷ 전환 합계`
- `ROAS = 매출 합계 ÷ 비용 합계`
- `전환율 = 전환 합계 ÷ 클릭 합계`
- 행별 비율 평균이 아닌 원천 지표 합계 후 비율 계산
- 원본에 없는 값은 `0`이 아닌 결측으로 유지
- 0 분모, 필수 값 결측, VAT 기준 혼합, 전환 정의 혼합 시 계산 제외와 사유 기록
- GA4 주요 이벤트와 광고 채널 구매 전환의 강제 통합 제외
- VAT 포함·제외 금액의 강제 환산 제외

## 고급 설정

| 설정 | 의미 |
|---|---|
| `UPLOAD_ENABLED=true` | Google Sheets 실제 반영 |
| `UPLOAD_ENABLED=false` | 로컬 결과만 생성 |
| `DRY_RUN=true` | 시트 입력 데이터 검증까지 진행, 원격 쓰기 제외 |
| `CURRENT_WEEK_START` | 금주로 사용할 월요일. 예: `2026-07-20` |
| `REFERENCE_DATE` | 해당 날짜를 기준으로 완전히 종료된 최신 주간 선택 |

`CURRENT_WEEK_START`와 `REFERENCE_DATE`는 둘 중 하나만 사용. 모두 비어 있으면 입력 데이터에서 확인되는 최신 완전 주간 선택.

<details>
<summary><strong>개발자용 실행·테스트·빌드</strong></summary>

### 소스 실행

```powershell
scripts\run_pipeline.bat --no-pause
```

### 원격 쓰기 없는 검증

```powershell
scripts\run_pipeline.bat --no-pause --dry-run
```

### 로컬 결과만 생성

```powershell
scripts\run_pipeline.bat --no-pause --no-upload
```

### 테스트

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m unittest discover -s tests/metrics -v
python -m unittest discover -s tests/comparison -v
python -m unittest discover -s tests/integration -v
```

### 실행파일 재빌드

```powershell
python -m pip install google-api-python-client google-auth pyinstaller
scripts\build_executable.bat
```

빌드 결과: 저장소 루트의 `Sangsaeng_Report_Automation.exe`.

</details>

<details>
<summary><strong>프로젝트 구조와 상세 문서</strong></summary>

```text
src/pipeline.py                         전체 실행 제어
src/normalization/normalize_csvs.py     채널 판별과 정규화
src/metrics/calculate_metrics.py        CPA·ROAS·전환율
src/comparison/weekly_comparison.py     전주 비교
src/outputs/google_sheets.py            Google Sheets 출력
Sangsaeng_Report_Automation.exe         최종 사용자 실행파일
scripts/executable_launcher.py          실행파일 진입점
scripts/build_executable.bat            실행파일 빌드
scripts/run_pipeline.bat                개발자용 소스 실행 진입점
tests/                                  단위·통합 테스트
docs/                                   설계·구현·작업 기록
```

- [설계 메모](docs/설계.md)
- [통합 파이프라인](docs/architecture/통합_파이프라인.md)
- [P2 정규화 설계 검토](docs/P2/P2_정규화_설계검토.md)
- [P2 Google Sheets API 사용 가이드](docs/P2/P2_구글시트_API_사용가이드.md)
- [P3 파생 지표 구현 결과](docs/P3/P3_파생지표_구현결과.md)
- [P4 전주 비교 구현 결과](docs/P4/P4_전주비교_구현결과.md)
- [작업 타임라인](docs/작업_타임라인.md)

</details>
