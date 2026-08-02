# 프로젝트 파일 구조

## 기준 구조

```text
상생/
├─ AGENTS.md
├─ README.md
├─ .gitignore
├─ .env.example
├─ Sangsaeng_Report_Automation.exe
├─ docs/
│  ├─ 설계.md
│  ├─ 설계메모.md
│  ├─ 작업_타임라인.md
│  ├─ architecture/
│  │  └─ FILE_TREE.md
│  ├─ P1/
│  ├─ P2/
│  ├─ P3/
│  ├─ P4/
│  └─ P5/
├─ src/
│  ├─ pipeline.py
│  ├─ ingestion/
│  ├─ normalization/
│  ├─ validation/
│  ├─ metrics/
│  ├─ comparison/
│  ├─ reporting/
│  └─ outputs/
├─ config/
├─ scripts/
│  ├─ executable_launcher.py
│  ├─ build_executable.bat
│  └─ run_pipeline.bat
├─ tests/
│  ├─ normalization/
│  ├─ metrics/
│  ├─ comparison/
│  ├─ reporting/
│  └─ integration/
├─ data/
│  └─ input/
└─ output/
   ├─ normalized/
   ├─ reports/
   └─ logs/
```

## 파이프라인

```text
data/input의 채널 CSV
        ↓
src/ingestion
파일 탐색·CSV 판독·채널 판별
        ↓
src/normalization
공통 스키마 변환·원본 추적 정보 보존
        ↓
src/validation
스키마·값·결측·중복·합계 검증
        ↓
src/metrics
CPA·ROAS·전환율 계산
        ↓
src/comparison
전주 대비 증감 계산
        ↓
src/reporting
주간 요약 데이터 생성
        ↓
src/outputs
로컬 파일 저장·구글시트 업로드
        ↓
output/normalized · output/reports · output/logs
```

## 책임 구분

| 문제 | 구현 위치 | 문서 위치 | 테스트 위치 |
|---|---|---|---|
| P1 채널별 수집 | MVP 구현 제외 | `docs/P1/` | - |
| P2 정규화·구글시트 반영 | `src/ingestion/`, `src/normalization/`, `src/validation/`, `src/outputs/` | `docs/P2/` | `tests/normalization/`, `tests/integration/` |
| P3 파생 지표 | `src/metrics/` | `docs/P3/` | `tests/metrics/` |
| P4 전주 대비 비교 | `src/comparison/` | `docs/P4/` | `tests/comparison/` |
| P5 주간 요약 | `src/reporting/` | `docs/P5/` | `tests/reporting/` |

`src/pipeline.py`와 공통 설정은 문제별 결과를 연결하는 통합 계층. 헤드 에이전트 관리 대상.

## 파일 생성 규칙

- 루트에 문제별 코드·문서·실행 결과 생성 금지
- 실행 결과의 루트 및 `src/` 저장 금지
- 원본 CSV의 코드 디렉터리 복사 금지
- 인증 정보의 저장소 기록 금지
- 문제별 에이전트는 할당된 구현·문서·테스트 경로만 수정
- 공통 스키마와 파이프라인 변경은 헤드 에이전트 검토 후 반영
- 기존 루트 파일 이동은 파일을 작업 중인 세션과 충돌 확인 후 진행
