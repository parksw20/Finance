"""DART OpenAPI (opendart.fss.or.kr) 연동.

- corpCode.xml 로 기업명 -> corp_code 매핑 (캐시: data/corp_codes.json)
- fnlttSinglAcntAll 로 손익/재무상태/현금흐름 주요 계정 수집
  * 판관비 세부 항목(인건비/광고비 등)은 주석 데이터라 이 API로는 제공되지 않음 → 엑셀 입력값 유지
- 상장사(사업보고서 제출 법인)만 조회 가능. 비상장사는 건너뜀.
"""
import io
import json
import re
import zipfile
import xml.etree.ElementTree as ET

import logging
import time

import requests

from . import categories as C

log = logging.getLogger("finance.dart")
_session = requests.Session()


def _get(url, params, timeout=20, retries=2):
    """DART GET (타임아웃 20초, 일시 오류 시 재시도). 마지막 실패는 예외로 전파."""
    last = None
    for attempt in range(retries + 1):
        try:
            r = _session.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            return r
        except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as e:  # noqa: PERF203
            last = e
            if isinstance(e, requests.HTTPError) and e.response is not None and e.response.status_code < 500:
                raise
            log.warning("DART 요청 실패(%d/%d) %s: %s", attempt + 1, retries + 1, params.get("corp_code", ""), e)
            time.sleep(1.5 * (attempt + 1))
    raise last
from .config import DART_API_KEY, DATA_DIR

BASE = "https://opendart.fss.or.kr/api"
CORP_CACHE = DATA_DIR / "corp_codes.json"

# DART 표준 계정명 -> 계정분류 (account_map 테이블보다 우선순위 낮음)
STANDARD_MAP = {
    "매출액": C.REVENUE, "수익(매출액)": C.REVENUE, "영업수익": C.REVENUE, "매출": C.REVENUE,
    "매출원가": C.COGS,
    "매출총이익": C.GROSS, "매출총이익(손실)": C.GROSS,
    "판매비와관리비": C.SGA, "판매비와 관리비": C.SGA, "영업비용": C.SGA,
    "영업이익": C.OP, "영업이익(손실)": C.OP, "영업손실": C.OP,
    "당기순이익": C.NET, "당기순이익(손실)": C.NET, "당기순손실": C.NET,
    "자산총계": C.ASSETS, "부채총계": C.LIAB, "자본총계": C.EQUITY,
    "이익잉여금": C.RETAINED, "이익잉여금(결손금)": C.RETAINED,
    "재고자산": C.INVENTORY,
    "사용권자산": C.ROU,
    "리스부채": C.LEASE, "유동리스부채": C.LEASE, "비유동리스부채": C.LEASE,
    "영업활동현금흐름": C.CF_OP, "투자활동현금흐름": C.CF_INV, "재무활동현금흐름": C.CF_FIN,
    "현금및현금성자산의순증가(감소)": C.CF_NET, "현금및현금성자산의증가(감소)": C.CF_NET,
}

# 순운전자본 구성 계정 (재무상태표 유동 항목 중 매핑)
# DART 로 덮어쓰는 계정분류 (총계 성격). 판관비 세부(①~⑨)는 DART 에 없으므로 제외
REPLACE_CATEGORIES = set(C.IS_ITEMS + C.CF_ITEMS + [C.ASSETS, C.LIAB, C.EQUITY, C.RETAINED, C.INVENTORY, C.ROU, C.LEASE])
NWC_CATEGORIES = {C.NWC_PLUS, C.NWC_MINUS}

NWC_PLUS_NAMES = {"현금및현금성자산", "단기금융상품", "단기금융자산", "매출채권", "매출채권및기타채권", "기타유동금융자산", "단기대여금", "기타수취채권"}
NWC_MINUS_NAMES = {"매입채무", "매입채무및기타채무", "단기차입금", "유동성장기부채", "유동성장기차입금", "미지급금", "기타유동금융부채", "단기금융부채", "계약부채"}


def _key():
    if not DART_API_KEY:
        raise RuntimeError("DART_API_KEY 가 설정되지 않았습니다 (.env 참고)")
    return DART_API_KEY


def _norm(name):
    return re.sub(r"\s+", "", str(name or ""))


def load_corp_codes(force=False):
    """{corp_name: {"corp_code":..., "stock_code":...}}"""
    if CORP_CACHE.exists() and not force:
        return json.loads(CORP_CACHE.read_text(encoding="utf-8"))
    log.info("DART 기업코드 목록 다운로드…")
    r = _get(f"{BASE}/corpCode.xml", {"crtfc_key": _key()}, timeout=120, retries=1)
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    xml = zf.read(zf.namelist()[0])
    root = ET.fromstring(xml)
    out = {}
    for el in root.iter("list"):
        name = _norm(el.findtext("corp_name"))
        stock = (el.findtext("stock_code") or "").strip()
        rec = {"corp_code": el.findtext("corp_code"), "stock_code": stock}
        # 동명 회사가 있으면 상장사를 우선
        if name not in out or (stock and not out[name]["stock_code"]):
            out[name] = rec
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CORP_CACHE.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


def resolve_corp(name, codes):
    n = _norm(name)
    cands = [n, n.replace("(주)", ""), "주식회사" + n, n + "주식회사"]
    m = re.match(r"^(.*?)\(.*\)$", n)  # 'TP(태평양물산)' -> 'TP', '태평양물산'
    if m:
        cands.append(m.group(1))
        cands.append(re.search(r"\((.*)\)", n).group(1))
    for c in cands:
        if c in codes:
            return codes[c]
    return None


# 보고서 코드: 11011 사업보고서(연간), 11013 1분기, 11012 반기, 11014 3분기
REPORT_CODES = {"FY": "11011", "Q1": "11013", "Q2": "11012", "Q3": "11014"}


def fetch_company_info(corp_code):
    """기업개황: 결산월(acc_mt), 종목코드 등. 실패 시 None."""
    r = _get(f"{BASE}/company.json", {"crtfc_key": _key(), "corp_code": corp_code})
    js = r.json()
    if js.get("status") != "000":
        return None
    acc = str(js.get("acc_mt") or "").strip()
    return {"fiscal_month": int(acc) if acc.isdigit() else None, "stock_code": (js.get("stock_code") or "").strip(), "corp_name": js.get("corp_name")}


def fetch_statements(corp_code, year, reprt_code="11011", prefer=None):
    """사업연도·보고서 코드의 전체 재무제표. 연결(CFS) 우선, 없으면 별도(OFS).
    prefer 에 'CFS'/'OFS' 를 주면 그것만 조회 (연간에서 확인된 구분을 분기에 재사용해 호출 수 절감)."""
    for fs_div in ((prefer,) if prefer else ("CFS", "OFS")):
        r = _get(
            f"{BASE}/fnlttSinglAcntAll.json",
            {"crtfc_key": _key(), "corp_code": corp_code, "bsns_year": year, "reprt_code": reprt_code, "fs_div": fs_div},
        )
        js = r.json()
        if js.get("status") == "000" and js.get("list"):
            return fs_div, js["list"]
        if js.get("status") not in ("000", "013"):  # 013 = 조회된 데이터 없음
            raise RuntimeError(f"DART 오류 {js.get('status')}: {js.get('message')}")
    return None, []


def _amt(v):
    if v in (None, "", "-"):
        return None
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return None


def to_facts(rows, year, account_map, period="FY"):
    """DART 응답 -> {(category, item, year, period): amount}.

    분기 보고서(period Q1~Q3):
      - 손익(IS/CIS): thstrm_amount = 당기 3개월, frmtrm_amount = 전기 동기 3개월 → 해당 분기값으로 저장
      - 재무상태(BS): thstrm_amount = 분기말 잔액 저장. frmtrm_amount 는 전기말(연간)이라 저장하지 않음
      - 현금흐름(CF): 분기 보고서는 누적값만 있어 저장하지 않음 (연간만)
    """
    facts = {}
    quarterly = period != "FY"
    for row in rows:
        nm = _norm(row.get("account_nm"))
        sj = row.get("sj_div")  # BS / IS / CIS / CF / SCE
        cat = account_map.get(row.get("account_nm", "").strip()) or account_map.get(nm) or STANDARD_MAP.get(nm)
        if cat is None and sj == "BS":
            if nm in NWC_PLUS_NAMES:
                cat = C.NWC_PLUS
            elif nm in NWC_MINUS_NAMES:
                cat = C.NWC_MINUS
        if cat is None or cat not in REPLACE_CATEGORIES | NWC_CATEGORIES:
            continue
        if sj == "CIS" and cat in (C.REVENUE, C.COGS, C.GROSS, C.SGA, C.OP, C.NET) and any(k[0] == cat for k in facts):
            continue  # 손익계산서(IS)가 있으면 포괄손익(CIS) 중복 무시
        if quarterly and sj == "CF":
            continue
        cur, prev = _amt(row.get("thstrm_amount")), _amt(row.get("frmtrm_amount"))
        if quarterly and sj == "BS":
            prev = None
        for y, a in ((year, cur), (year - 1, prev)):
            if a is None:
                continue
            key = (cat, nm, y, period)
            if key in facts:
                continue
            facts[key] = a
    return facts
