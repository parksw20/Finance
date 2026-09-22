"""기업/업종 지표 계산 (엑셀 '스크리너'/'업종'/'기업분석' 시트의 수식을 그대로 옮김).

금액 단위: 억원 (원 / 1e8)
"""
from collections import defaultdict

from . import categories as C

EOK = 1e8

RATIO_KEYS = ["cogs_ratio", "sga_ratio", "opm", "net_margin"]


def _div(a, b):
    if a is None or b in (None, 0):
        return None
    return a / b


def _growth(cur, prev):
    if cur is None or prev in (None, 0):
        return None
    return cur / prev - 1


def load_amounts(conn, company_ids=None):
    """{company_id: {year: {category: amount(억원)}}}"""
    sql = "SELECT company_id, category, fiscal_year, SUM(amount) AS amt FROM facts"
    params = ()
    if company_ids:
        sql += " WHERE company_id IN (%s)" % ",".join("?" * len(company_ids))
        params = tuple(company_ids)
    sql += " GROUP BY company_id, category, fiscal_year"
    out = defaultdict(lambda: defaultdict(dict))
    for r in conn.execute(sql, params):
        out[r["company_id"]][r["fiscal_year"]][r["category"]] = r["amt"] / EOK
    return out


def load_sga_detail(conn, company_id):
    """{year: {category: [(item, amount)]}} 판관비 세부 항목"""
    out = defaultdict(lambda: defaultdict(list))
    for r in conn.execute(
        "SELECT category, item, fiscal_year, amount FROM facts WHERE company_id=? ORDER BY category, amount DESC",
        (company_id,),
    ):
        out[r["fiscal_year"]][r["category"]].append((r["item"], r["amount"] / EOK))
    return out


def fill_derived(y):
    """매출총이익/판관비/영업이익 누락 시 보완."""
    rev, cogs = y.get(C.REVENUE), y.get(C.COGS)
    if C.GROSS not in y and rev is not None and cogs is not None:
        y[C.GROSS] = rev - cogs
    if C.SGA not in y:
        items = [y.get(k) for k in C.SGA_ITEMS if y.get(k) is not None]
        if items:
            y[C.SGA] = sum(items)
    if C.OP not in y and y.get(C.GROSS) is not None and y.get(C.SGA) is not None:
        y[C.OP] = y[C.GROSS] - y[C.SGA]
    return y


def compute_ratios(cur, prev):
    """당해/전년 계정 dict -> 지표 dict."""
    cur = fill_derived(dict(cur))
    prev = fill_derived(dict(prev)) if prev else {}
    rev, prev_rev = cur.get(C.REVENUE), prev.get(C.REVENUE)
    inv_cur, inv_prev = cur.get(C.INVENTORY), prev.get(C.INVENTORY)
    avg_inv = None
    if inv_cur is not None and inv_prev is not None and (inv_cur + inv_prev) > 0:
        avg_inv = (inv_cur + inv_prev) / 2
    elif inv_cur:
        avg_inv = inv_cur
    turnover = _div(cur.get(C.COGS), avg_inv)
    net_cash = None
    if cur.get(C.NWC_PLUS) is not None or cur.get(C.NWC_MINUS) is not None:
        net_cash = (cur.get(C.NWC_PLUS) or 0) - (cur.get(C.NWC_MINUS) or 0)
    net_cash_prev = None
    if prev.get(C.NWC_PLUS) is not None or prev.get(C.NWC_MINUS) is not None:
        net_cash_prev = (prev.get(C.NWC_PLUS) or 0) - (prev.get(C.NWC_MINUS) or 0)
    debt_ratio = _div((cur.get(C.LIAB) or 0) - (cur.get(C.LEASE) or 0), cur.get(C.EQUITY)) if cur.get(C.LIAB) is not None else None
    debt_ratio_prev = _div((prev.get(C.LIAB) or 0) - (prev.get(C.LEASE) or 0), prev.get(C.EQUITY)) if prev.get(C.LIAB) is not None else None

    m = {
        "revenue": rev,
        "revenue_prev": prev_rev,
        "revenue_growth": _growth(rev, prev_rev),
        "cogs": cur.get(C.COGS),
        "cogs_prev": prev.get(C.COGS),
        "gross": cur.get(C.GROSS),
        "gross_prev": prev.get(C.GROSS),
        "sga": cur.get(C.SGA),
        "sga_prev": prev.get(C.SGA),
        "op": cur.get(C.OP),
        "op_prev": prev.get(C.OP),
        "op_change": (cur.get(C.OP) - prev.get(C.OP)) if cur.get(C.OP) is not None and prev.get(C.OP) is not None else None,
        "net": cur.get(C.NET),
        "net_prev": prev.get(C.NET),
        "cogs_ratio": _div(cur.get(C.COGS), rev),
        "cogs_ratio_prev": _div(prev.get(C.COGS), prev_rev),
        "sga_ratio": _div(cur.get(C.SGA), rev),
        "sga_ratio_prev": _div(prev.get(C.SGA), prev_rev),
        "opm": _div(cur.get(C.OP), rev),
        "opm_prev": _div(prev.get(C.OP), prev_rev),
        "net_margin": _div(cur.get(C.NET), rev),
        "assets": cur.get(C.ASSETS),
        "assets_prev": prev.get(C.ASSETS),
        "liabilities": cur.get(C.LIAB),
        "liabilities_prev": prev.get(C.LIAB),
        "equity": cur.get(C.EQUITY),
        "equity_prev": prev.get(C.EQUITY),
        "inventory": inv_cur,
        "inventory_prev": inv_prev,
        "inventory_turnover": turnover,
        "inventory_days": _div(365, turnover),
        "net_cash": net_cash,
        "net_cash_prev": net_cash_prev,
        "debt_ratio": debt_ratio,
        "debt_ratio_prev": debt_ratio_prev,
        "nwc_plus": cur.get(C.NWC_PLUS),
        "nwc_minus": cur.get(C.NWC_MINUS),
        "rou_asset": cur.get(C.ROU),
        "rou_asset_prev": prev.get(C.ROU),
        "lease_liab": cur.get(C.LEASE),
        "lease_liab_prev": prev.get(C.LEASE),
        "cf_op": cur.get(C.CF_OP),
        "cf_inv": cur.get(C.CF_INV),
        "cf_fin": cur.get(C.CF_FIN),
        "cf_net": cur.get(C.CF_NET),
        "sga_items": {},
    }
    for k in C.SGA_ITEMS:
        m["sga_items"][k] = {
            "cur": cur.get(k),
            "prev": prev.get(k),
            "ratio": _div(cur.get(k), rev),
            "ratio_prev": _div(prev.get(k), prev_rev),
        }
    m.update(ratings(m))
    return m


def ratings(m):
    """엑셀 '간략 평가' 규칙.
    성장성: 매출성장률 >20% Good, <0 Bad, 그 외 N
    수익성: 영업이익률 >15% Good, <5% Bad, 그 외 N
    안정성: 부채비율 <100% Good, >200% Bad, 그 외 N
    """
    g = m.get("revenue_growth")
    p = m.get("opm")
    d = m.get("debt_ratio")
    growth = "-" if g is None else ("Good" if g > 0.20 else "Bad" if g < 0 else "N")
    profit = "-" if p is None or (m.get("op") is None) else ("Good" if p > 0.15 else "Bad" if p < 0.05 else "N")
    eq = m.get("equity")
    if eq is not None and eq <= 0 and m.get("liabilities") is not None:
        stab = "Bad"  # 자본잠식
    elif d is None or eq in (None, 0):
        stab = "-"
    else:
        stab = "Good" if 0 <= d < 1.0 else "Bad" if d > 2.0 else "N"
    return {"rating_growth": growth, "rating_profit": profit, "rating_stability": stab}


def company_metrics(conn, year, company_ids=None):
    """기업별 지표 목록."""
    amounts = load_amounts(conn, company_ids)
    rows = []
    q = "SELECT * FROM companies ORDER BY name"
    for c in conn.execute(q):
        if company_ids and c["id"] not in company_ids:
            continue
        yrs = amounts.get(c["id"], {})
        cur = yrs.get(year, {})
        if not cur:
            continue
        m = compute_ratios(cur, yrs.get(year - 1, {}))
        m.update(
            id=c["id"],
            name=c["name"],
            sector=c["sector"],
            category=c["category"],
            description=c["description"],
            include_in_sector=bool(c["include_in_sector"]),
        )
        m["size_band"] = size_band(m["revenue"])
        rows.append(m)
    return rows


def size_band(rev_eok):
    if rev_eok is None:
        return None
    r = rev_eok
    if r < 10:
        return "①0~10억"
    if r < 100:
        return "②10~100억"
    if r < 500:
        return "③100~500억"
    if r < 1000:
        return "④500~1000억"
    if r < 5000:
        return "⑤1000~5000억"
    if r < 10000:
        return "⑥5000억~1조"
    return "⑦1조 이상"


def aggregate(rows_cur, label):
    """기업 지표 행들을 합산해 하나의 집계 행(업종/전체)으로."""
    cur = defaultdict(float)
    prev = defaultdict(float)
    seen_cur = set()
    seen_prev = set()
    for r in rows_cur:
        for k, v in r["_cur_raw"].items():
            cur[k] += v
            seen_cur.add(k)
        for k, v in r["_prev_raw"].items():
            prev[k] += v
            seen_prev.add(k)
    m = compute_ratios({k: cur[k] for k in seen_cur}, {k: prev[k] for k in seen_prev})
    m["name"] = label
    m["company_count"] = len(rows_cur)
    return m


def sector_metrics(conn, year):
    """업종별 집계 지표 + 전체 평균."""
    amounts = load_amounts(conn)
    by_sector = defaultdict(list)
    all_rows = []
    for c in conn.execute("SELECT * FROM companies WHERE include_in_sector=1"):
        yrs = amounts.get(c["id"], {})
        cur = yrs.get(year, {})
        if not cur or cur.get(C.REVENUE) in (None, 0):
            continue
        row = {"_cur_raw": fill_derived(dict(cur)), "_prev_raw": fill_derived(dict(yrs.get(year - 1, {})))}
        by_sector[c["sector"] or "미분류"].append(row)
        all_rows.append(row)
    sectors = []
    for name, rows in by_sector.items():
        m = aggregate(rows, name)
        m["sector"] = name
        sectors.append(m)
    sectors.sort(key=lambda s: -(s["revenue"] or 0))
    total = aggregate(all_rows, "∑ 전체 합계") if all_rows else None
    return sectors, total


def available_years(conn):
    rows = conn.execute(
        "SELECT fiscal_year, COUNT(DISTINCT company_id) AS n FROM facts WHERE category=? GROUP BY fiscal_year ORDER BY fiscal_year",
        (C.REVENUE,),
    ).fetchall()
    return [{"year": r["fiscal_year"], "companies": r["n"]} for r in rows]


def default_year(conn):
    yrs = [y for y in available_years(conn) if y["companies"] >= 5]
    if not yrs:
        yrs = available_years(conn)
    return yrs[-1]["year"] if yrs else None
