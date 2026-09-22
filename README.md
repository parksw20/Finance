# 재무 대시보드 (업종 / 스크리너 / 기업분석)

참고 엑셀 워크북(업종·스크리너·기업분석·raw·정보입력 시트)을 웹 대시보드로 옮긴 프로젝트입니다.
데이터는 SQLite에 저장되며, 엑셀 파일 투입 또는 DART OpenAPI를 통해 주기적으로 갱신할 수 있습니다.

## 빠른 시작

```bash
pip install -r requirements.txt
cp .env.example .env            # 필요 시 DART_API_KEY, REFRESH_SCHEDULE 수정
uvicorn app.main:app --port 8000     # 또는 run.bat / ./run.sh [포트]
# http://localhost:8000
```

첫 실행 시 `data/seed/*.csv`(참고 워크북에서 추출한 122개 기업, 9,240건 계정 데이터)가 자동으로 `data/finance.db`에 적재됩니다.

## 화면 구성

| 탭 | 내용 (엑셀 시트 대응) |
|---|---|
| **업종** | 전체 KPI, 업종별 성장률·영업이익률·부채비율·판관비 구조 차트, 업종 요약표(간략 평가 포함), 기업 순위(성장률/역성장/영업이익률/매출원가율/광고비율) |
| **스크리너** | 기업별 손익·판관비·재무상태 지표 테이블. 업종/매출규모/성장·역성장/흑자·적자/간략평가 필터, 컬럼 정렬, 선택 기업 합계 행 |
| **기업분석** | 손익계산서(전년·당해·성장률·매출대비 비율·GAP), 재무상태·현금흐름, 판관비 구성 차트, 연도별 추이, 판관비 세부 원장, 비교 기업(최대 3) + 업종 평균 + 전체 합계 비교 |
| **데이터** | 갱신 상태·스케줄, 수동 갱신 버튼, 엑셀 업로드, 갱신 이력 |

금액 단위는 **억원**입니다. 간략 평가 규칙은 엑셀과 동일합니다.

- 성장성: 매출성장률 > 20% Good, < 0% Bad, 그 외 N
- 수익성: 영업이익률 > 15% Good, < 5% Bad, 그 외 N
- 안정성: 부채비율(리스부채 제외) < 100% Good, > 200% Bad, 그 외 N
  (엑셀 수식의 `0<x<100%` 연쇄 비교 버그로 엑셀에서는 Good이 표시되지 않던 부분을 의도대로 보정)

## 데이터 갱신

### 1. 엑셀 파일 (참고 워크북과 같은 양식)
- `data/inbox/`에 `.xlsm`/`.xlsx`를 넣거나 **데이터 탭에서 업로드**하면 `raw`·`정보입력` 시트를 읽어 DB에 반영합니다.
- 새 파일·변경된 파일만 임포트합니다(수정 시각/크기 기준).
- CLI: `python -m app.refresh --inbox` 또는 `python -m app.refresh --file 파일.xlsm`

### 2. DART OpenAPI (상장사)
- [OpenDART](https://opendart.fss.or.kr) 인증키를 다음 중 한 곳에 두면 (우선순위 순) 기업명으로 DART 기업코드를 자동 매핑합니다.
  1. 환경변수 `DART_API_KEY`
  2. `.env`의 `DART_API_KEY`
  3. OS 키체인: `keyring set finance-dashboard DART_API_KEY` 실행 후 키 입력 (Windows 자격 증명 관리자 / macOS 키체인 / Linux Secret Service). 서비스명은 `FINANCE_KEYRING_SERVICE`로 변경 가능
- 키가 설정되면 기업명으로 DART 기업코드를 자동 매핑하고 사업보고서(연결 우선)에서 손익·재무상태·현금흐름 총계를 가져옵니다.
- 판관비 세부 항목(인건비·광고선전비 등)은 주석 데이터라 API로 제공되지 않으므로 엑셀 입력값이 유지됩니다.
- 비상장사(쿠팡, 무신사 등)는 DART 재무제표 API 대상이 아니므로 건너뛰고 이력에 기록됩니다.
- CLI: `python -m app.refresh --dart --year 2025`

### 3. 자동 스케줄
- `.env`의 `REFRESH_SCHEDULE`(cron 5필드, 기본 `0 6 * * *` = 매일 06:00)에 따라 앱 프로세스 안의 APScheduler가 inbox → DART 순으로 갱신합니다. 서버(uvicorn)가 실행 중이어야 합니다.
- 시스템 cron을 쓰려면 `python -m app.refresh`를 등록해도 됩니다.

## 구조

```
app/
  main.py        FastAPI API + 정적 파일 서빙
  db.py          SQLite 스키마 (companies / account_map / facts / refresh_log / import_files)
  categories.py  계정분류 정의 (엑셀 '계정분류' 체계)
  importer.py    엑셀 → DB
  metrics.py     기업·업종 지표/간략평가 계산 (엑셀 수식 이식)
  dart.py        DART OpenAPI 클라이언트 + 계정 매핑
  refresh.py     갱신 오케스트레이션 (inbox + DART), CLI
  scheduler.py   APScheduler 주기 갱신
  seed.py        data/seed CSV 초기 적재
static/          index.html / app.js / style.css / vendor(Chart.js)
data/seed/       초기 데이터 CSV (companies, account_map, facts)
data/inbox/      갱신용 엑셀 투입 폴더
scripts/export_seed.py   워크북 → seed CSV 재생성
```

## API

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/api/meta` | 연도 목록, 업종, 최근 갱신, 스케줄 |
| GET | `/api/sectors?year=` | 업종별 집계 + 전체 합계 + 순위 |
| GET | `/api/screener?year=` | 기업별 지표 |
| GET | `/api/company/{id}?year=&peers=1,2` | 기업 상세 + 비교 |
| PUT | `/api/company/{id}` | 업종/설명/집계대상 수정 |
| POST | `/api/refresh?source=all` | 갱신 실행(백그라운드). `source`는 `all` / `inbox` / `dart` 중 하나, `year=` 로 DART 조회 연도 지정 가능 |
| GET | `/api/refresh/status` | 갱신 상태·이력 |
| POST | `/api/upload` | 엑셀 업로드 후 즉시 임포트 |
