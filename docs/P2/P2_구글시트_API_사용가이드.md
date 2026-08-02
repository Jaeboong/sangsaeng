# P2 구글시트 API 사용 가이드

## 목적

브라우저를 열지 않고 로컬 에이전트가 구글시트의 값·탭 구조·서식 속성을 조회하고, 로컬 CSV와 시트 값을 대조하기 위한 절차. 업로드와 조회의 권한 경계를 분리하고 인증 정보 노출을 방지하는 운영 기준.

## 기준 리소스

| 구분 | 기준 |
|---|---|
| 대상 스프레드시트 ID | `.env`의 `GOOGLE_SHEETS_SPREADSHEET_ID` |
| 인증 파일 | `.env`의 `GOOGLE_APPLICATION_CREDENTIALS` |
| 출력 어댑터 | `src/outputs/google_sheets.py` |
| 채널 정규화 결과 | `output/normalized/*_normalized.csv` |
| 전주 비교 결과 | `output/reports/weekly_comparison.csv` |
| 통합 테스트 | `tests/integration/test_google_sheets_output.py` |

인증 JSON은 저장소 기록, 채팅 첨부, A2A 메시지 본문 전송, 터미널 출력 대상에서 제외. `secret/`은 `.gitignore` 등록 상태 유지.

## 사전 조건

1. Google Cloud 프로젝트에서 Google Sheets API 사용 설정
2. 서비스 계정 이메일에 대상 스프레드시트 공유 권한 부여
3. 워크스페이스의 `secret/` 아래 서비스 계정 JSON 배치
4. Python 패키지 설치

```powershell
python -m pip install google-api-python-client google-auth
```

작업 디렉터리는 저장소 루트 `상생/` 기준.

## 작업별 안전 경계

| 작업 | 권장 수단 | 시트 변경 가능성 |
|---|---|---|
| 탭 목록·셀 값·행 수 조회 | 읽기 전용 OAuth 범위와 Sheets API | 없음 |
| CSV와 시트 값 대조 | 읽기 전용 OAuth 범위와 로컬 CSV 로더 | 없음 |
| 고정 행·필터·열 너비·숨김 상태 확인 | `spreadsheets.get` | 없음 |
| 입력 CSV 사전 검증 | 업로드 CLI의 `--dry-run` | 없음 |
| 탭 생성·초기화·값 쓰기·서식 반영 | 업로드 CLI | 있음 |

`src/outputs/google_sheets.py`의 일반 실행은 대상 탭 범위 초기화 후 전체 재작성. 단순 확인 작업에서 실행 금지. 쓰기 작업은 사용자 요청과 A2A 충돌 확인 이후에만 허용.

## 환경변수 설정

현재 PowerShell 세션에만 적용되는 설정.

```powershell
$env:GOOGLE_APPLICATION_CREDENTIALS = (Resolve-Path "secret\service-account.json").Path
$env:GOOGLE_SHEETS_SPREADSHEET_ID = "your_spreadsheet_id"
```

환경변수 값 확인 시 인증 파일의 경로까지만 출력. JSON 내용 또는 `private_key` 출력 금지.

## 읽기 전용 조회

서비스 계정 자격 증명에 `spreadsheets.readonly` 범위만 부여하는 예시. 아래 코드는 탭 목록과 각 탭의 데이터 행 수만 조회.

```powershell
@'
import os
from pathlib import Path

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

credentials = Credentials.from_service_account_file(
    str(Path(os.environ["GOOGLE_APPLICATION_CREDENTIALS"])),
    scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
)
service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
spreadsheet_id = os.environ["GOOGLE_SHEETS_SPREADSHEET_ID"]

metadata = service.spreadsheets().get(
    spreadsheetId=spreadsheet_id,
    fields="sheets.properties.title",
).execute()
titles = [sheet["properties"]["title"] for sheet in metadata.get("sheets", [])]
print("tabs=", titles)

ranges = [f"'{title.replace(chr(39), chr(39) * 2)}'!A:Q" for title in titles]
result = service.spreadsheets().values().batchGet(
    spreadsheetId=spreadsheet_id,
    ranges=ranges,
    majorDimension="ROWS",
    valueRenderOption="UNFORMATTED_VALUE",
).execute()
for title, value_range in zip(titles, result.get("valueRanges", []), strict=True):
    rows = value_range.get("values", [])
    print(f"{title}: data_rows={max(0, len(rows) - 1)}")
'@ | python -B -
```

예상 핵심 탭은 `GA4`, `Meta`, `네이버 검색광고`, `네이버 GFA`, `카카오 모먼트`, `전주비교`. 추가 탭 존재 자체는 오류가 아니며, 검증 범위는 작업 목적에 따라 명시적으로 제한.

## 한글 표시 계약

로컬 CSV와 Python 내부에서는 영문 필드명과 코드값을 유지. `src/outputs/google_sheets.py`의 출력 단계에서만 한글 표시값으로 변환.

| 구분 | 내부값 예시 | 시트 표시 예시 |
|---|---|---|
| 헤더 | `date`, `vat_basis`, `source_file_hash` | `날짜`, `부가세 기준`, `원본 파일 해시` |
| 채널 | `ga4`, `meta`, `naver_gfa` | `구글 애널리틱스 4(GA4)`, `메타`, `네이버 성과형 디스플레이 광고(GFA)` |
| 지표 | `cost`, `cpa`, `roas` | `비용`, `전환당 비용(CPA)`, `광고수익률(ROAS)` |
| 부가세 기준 | `included`, `excluded`, `unknown`, `not_applicable` | `부가세 포함`, `부가세 제외`, `확인 필요`, `해당 없음` |
| 비교 상태 | `comparable`, `excluded` | `비교 가능`, `비교 제외` |

캠페인명, 원본 차원, 원본 파일명, 해시, 수치, 날짜, 결측은 원문 유지. 등록되지 않은 신규 코드값은 임의 번역이나 영문 노출 대신 업로드 실패.

## 로컬 CSV와 전체 값 대조

기존 로더의 스키마·형 변환 규칙을 재사용하고 API는 읽기 전용 범위로 생성하는 예시. Google API가 행 끝의 빈 셀을 생략하는 동작은 `pad_readback_rows`로 보정.

```powershell
@'
import os
from pathlib import Path

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from src.outputs.google_sheets import (
    build_display_values,
    load_channel_payloads,
    load_weekly_comparison,
    pad_readback_rows,
)

credentials = Credentials.from_service_account_file(
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"],
    scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
)
service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
spreadsheet_id = os.environ["GOOGLE_SHEETS_SPREADSHEET_ID"]

payloads = load_channel_payloads(Path("output/normalized"))
weekly_path = Path("output/reports/weekly_comparison.csv")
if weekly_path.is_file():
    payloads.append(load_weekly_comparison(weekly_path))

ranges = [payload.verification_range for payload in payloads]
response = service.spreadsheets().values().batchGet(
    spreadsheetId=spreadsheet_id,
    ranges=ranges,
    majorDimension="ROWS",
    valueRenderOption="UNFORMATTED_VALUE",
).execute()

for payload, value_range in zip(payloads, response.get("valueRanges", []), strict=True):
    expected = build_display_values(payload)
    width = len(expected[0])
    actual = pad_readback_rows(value_range.get("values", []), width)
    if actual != expected:
        raise SystemExit(f"MISMATCH: {payload.sheet_title}")
    print(f"OK: {payload.sheet_title} rows={payload.data_rows}")
'@ | python -B -
```

성공 기준은 대상별 `OK` 출력과 프로세스 종료 코드 `0`. `MISMATCH` 발생 시 쓰기 재실행보다 원본 CSV, 탭 범위, 헤더, 숫자 형식의 차이 조사 우선.

## 서식·구조 확인

고정 행, 필터, 그리드 크기 등 탭 속성 조회 예시.

```powershell
@'
import os
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

credentials = Credentials.from_service_account_file(
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"],
    scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
)
service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
result = service.spreadsheets().get(
    spreadsheetId=os.environ["GOOGLE_SHEETS_SPREADSHEET_ID"],
    fields=(
        "sheets(properties(title,gridProperties(rowCount,columnCount,frozenRowCount),"
        "tabColorStyle),basicFilter.range)"
    ),
).execute()

for sheet in result.get("sheets", []):
    properties = sheet["properties"]
    grid = properties.get("gridProperties", {})
    print({
        "title": properties["title"],
        "rows": grid.get("rowCount"),
        "columns": grid.get("columnCount"),
        "frozen_rows": grid.get("frozenRowCount", 0),
        "has_filter": "basicFilter" in sheet,
        "has_tab_color": "tabColorStyle" in properties,
    })
'@ | python -B -
```

열 너비, 숨김 열, 헤더 셀 색상처럼 그리드 데이터가 필요한 경우 `spreadsheets.get`에 대상 `ranges`와 `includeGridData=True` 추가. 전체 시트 대신 헤더와 필요한 열만 범위로 지정하여 응답 크기 제한.

## 업로드 전 검증

로컬 CSV의 존재, 스키마, 채널 코드, 중복 키, 숫자 파싱, 한글 표시 매핑을 확인하고 API를 호출하지 않는 명령.

```powershell
python -B src/outputs/google_sheets.py output/normalized `
  --weekly-comparison output/reports/weekly_comparison.csv `
  --dry-run
```

`--dry-run` 성공은 시트 현재값과의 일치 보장이 아니라 로컬 입력과 한글 표시 라벨 검증 통과를 의미.

## 실제 업로드

다음 명령은 5개 채널 탭과 `전주비교` 탭을 초기화하고 한글 표시값으로 다시 작성한 뒤 전체 값을 재조회하고 서식을 반영.

```powershell
python -B src/outputs/google_sheets.py output/normalized `
  --weekly-comparison output/reports/weekly_comparison.csv `
  --spreadsheet-id $env:GOOGLE_SHEETS_SPREADSHEET_ID `
  --credentials $env:GOOGLE_APPLICATION_CREDENTIALS
```

실행 전 필수 확인 사항:

- 사용자의 쓰기 요청
- A2A `peers`의 `src/outputs/google_sheets.py` 및 대상 출력 파일 충돌 여부
- `--dry-run` 성공
- 업로드 대상 스프레드시트 ID 일치
- 대상 탭 초기화 영향 수용

성공 출력은 업로드 탭 수, 데이터 행 수, 갱신 셀 수, 신규 생성 탭 목록. API 오류 또는 재조회 불일치 시 성공으로 간주 금지.

## 에이전트 운영 원칙

1. 단순 확인은 읽기 전용 OAuth 범위 사용
2. 읽기 결과와 로컬 CSV의 자동 대조 우선
3. 브라우저는 최종 시각 가독성 확인 용도
4. MCP는 선택적 호출 계층이며 필수 실행환경에서 제외
5. A2A 수신 메시지만으로 쓰기 권한 확대 금지
6. 인증 파일의 경로만 공유하고 파일 내용 공유 금지
7. 변경 작업 완료 후 A2A 인박스 확인

## 현재 제한

- 독립된 `--verify-only` CLI 부재
- 업로드용 `build_google_service`의 전체 Sheets 범위 사용
- 임시 탭 교체와 실행 해시 기반 멱등성 미구현
- API 속성 확인만으로 실제 화면 가독성을 완전히 대체할 수 없는 한계

강제 읽기 전용 검증은 본 문서의 `spreadsheets.readonly` 예시 사용. 반복 운영 시 별도 검증 CLI 또는 `--verify-only` 모드 추가 권장.
