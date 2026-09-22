"""FastAPI 앱: API + 정적 대시보드."""
import logging
import shutil
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from . import categories as C
from . import scheduler
from .config import DART_API_KEY, INBOX_DIR, REFRESH_ON_START, REFRESH_SCHEDULE, STATIC_DIR
from .db import get_conn, init_db, connect
from .metrics import available_years, company_metrics, default_year, fill_derived, load_amounts, load_sga_detail, sector_metrics, compute_ratios
from .refresh import refresh_state, run_refresh, refresh_inbox
from .seed import load_seed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("finance")


def bootstrap():
    init_db()
    with get_conn() as conn:
        n = conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
    if n == 0:
        res = load_seed()
        log.info("seed 데이터 적재: %s", res)
    refresh_inbox()


@asynccontextmanager
async def lifespan(app: FastAPI):
    bootstrap()
    scheduler.start()
    if REFRESH_ON_START:
        threading.Thread(target=run_refresh, daemon=True).start()
    yield
    scheduler.stop()


app = FastAPI(title="Finance Dashboard", lifespan=lifespan)


def _year(conn, year):
    y = year or default_year(conn)
    if y is None:
        raise HTTPException(404, "데이터가 없습니다")
    return y


def _strip(m):
    return {k: v for k, v in m.items() if not k.startswith("_")}


@app.get("/api/meta")
def meta():
    conn = connect()
    try:
        years = available_years(conn)
        last = conn.execute("SELECT * FROM refresh_log ORDER BY id DESC LIMIT 1").fetchone()
        sectors = [r[0] for r in conn.execute("SELECT DISTINCT sector FROM companies WHERE sector IS NOT NULL ORDER BY sector")]
        n_comp = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
        return {
            "years": years,
            "default_year": default_year(conn),
            "sectors": sectors,
            "company_count": n_comp,
            "sga_items": C.SGA_ITEMS,
            "last_refresh": dict(last) if last else None,
            "schedule": REFRESH_SCHEDULE,
            "next_run": scheduler.next_run(),
            "dart_enabled": bool(DART_API_KEY),
            "refresh_running": refresh_state()["running"],
        }
    finally:
        conn.close()


@app.get("/api/sectors")
def sectors(year: int | None = None):
    conn = connect()
    try:
        y = _year(conn, year)
        secs, total = sector_metrics(conn, y)
        comps = [r for r in company_metrics(conn, y) if r["include_in_sector"]]
        rankings = {}

        def top(key, n=10, reverse=True, pred=lambda r: True, min_rev=100):
            rows = [r for r in comps if r.get(key) is not None and (r["revenue"] or 0) >= min_rev and pred(r)]
            rows.sort(key=lambda r: r[key], reverse=reverse)
            return [{"id": r["id"], "name": r["name"], "sector": r["sector"], "value": r[key], "revenue": r["revenue"]} for r in rows[:n]]

        rankings["growth"] = top("revenue_growth")
        rankings["decline"] = top("revenue_growth", reverse=False, pred=lambda r: r["revenue_growth"] < 0)
        rankings["opm"] = top("opm")
        rankings["cogs_ratio"] = top("cogs_ratio", reverse=False, pred=lambda r: r["cogs_ratio"] > 0)
        rankings["ad_ratio"] = sorted(
            [
                {"id": r["id"], "name": r["name"], "sector": r["sector"], "value": r["sga_items"]["④ 광고선전비"]["ratio"], "revenue": r["revenue"]}
                for r in comps
                if r["sga_items"]["④ 광고선전비"]["ratio"] and (r["revenue"] or 0) >= 100
            ],
            key=lambda x: -x["value"],
        )[:10]
        rankings["sector_growth"] = sorted(
            [{"name": s["sector"], "value": s["revenue_growth"]} for s in secs if s["revenue_growth"] is not None], key=lambda x: -x["value"]
        )
        rankings["sector_opm"] = sorted([{"name": s["sector"], "value": s["opm"]} for s in secs if s["opm"] is not None], key=lambda x: -x["value"])
        return {"year": y, "sectors": [_strip(s) for s in secs], "total": _strip(total) if total else None, "rankings": rankings}
    finally:
        conn.close()


@app.get("/api/screener")
def screener(year: int | None = None):
    conn = connect()
    try:
        y = _year(conn, year)
        rows = company_metrics(conn, y)
        rows.sort(key=lambda r: -(r["revenue"] or 0))
        return {"year": y, "companies": [_strip(r) for r in rows]}
    finally:
        conn.close()


@app.get("/api/companies")
def companies():
    conn = connect()
    try:
        return [dict(r) for r in conn.execute("SELECT id, name, sector, category, description, include_in_sector, corp_code, stock_code FROM companies ORDER BY sector, name")]
    finally:
        conn.close()


@app.get("/api/company/{cid}")
def company(cid: int, year: int | None = None, peers: str = Query("", description="비교 기업 id, 콤마 구분")):
    conn = connect()
    try:
        y = _year(conn, year)
        row = conn.execute("SELECT * FROM companies WHERE id=?", (cid,)).fetchone()
        if not row:
            raise HTTPException(404, "기업 없음")
        amounts = load_amounts(conn, [cid]).get(cid, {})
        years_avail = sorted(amounts.keys())
        cur, prev = amounts.get(y, {}), amounts.get(y - 1, {})
        m = compute_ratios(cur, prev)
        m.update(id=row["id"], name=row["name"], sector=row["sector"], category=row["category"], description=row["description"])
        # 손익 표 (계정, 전년, 당해, 성장률, 전년비율, 당해비율, GAP)
        cur_f, prev_f = fill_derived(dict(cur)), fill_derived(dict(prev))
        rev, prev_rev = cur_f.get(C.REVENUE), prev_f.get(C.REVENUE)
        statement = []
        for cat in C.STATEMENT_ORDER:
            a, b = prev_f.get(cat), cur_f.get(cat)
            if a is None and b is None:
                continue
            ra = a / prev_rev if a is not None and prev_rev else None
            rb = b / rev if b is not None and rev else None
            statement.append(
                {
                    "category": cat,
                    "is_sub": cat in C.SGA_ITEMS,
                    "prev": a,
                    "cur": b,
                    "growth": (b / a - 1) if a not in (None, 0) and b is not None else None,
                    "ratio_prev": ra,
                    "ratio_cur": rb,
                    "gap": (rb - ra) if ra is not None and rb is not None else None,
                }
            )
        balance = []
        for cat, label in ((C.ASSETS, "자산총계"), (C.LIAB, "부채총계"), (C.EQUITY, "자본총계"), (C.LEASE, "리스부채"), (C.INVENTORY, "재고자산"), (C.ROU, "사용권자산"), (C.CF_OP, "영업활동현금흐름")):
            a, b = prev_f.get(cat), cur_f.get(cat)
            if a is None and b is None:
                continue
            balance.append({"category": label, "prev": a, "cur": b, "growth": (b / a - 1) if a not in (None, 0) and b is not None else None})
        balance.append({"category": "부채비율", "prev": m["debt_ratio_prev"], "cur": m["debt_ratio"], "growth": (m["debt_ratio"] / m["debt_ratio_prev"] - 1) if m["debt_ratio_prev"] and m["debt_ratio"] is not None else None, "is_ratio": True})
        # 판관비 세부
        detail = load_sga_detail(conn, cid)
        sga_detail = {}
        for cat in C.SGA_ITEMS:
            items = {}
            for it, amt in detail.get(y, {}).get(cat, []):
                items.setdefault(it, {})["cur"] = amt
            for it, amt in detail.get(y - 1, {}).get(cat, []):
                items.setdefault(it, {})["prev"] = amt
            if items:
                sga_detail[cat] = [{"item": k, **v} for k, v in sorted(items.items(), key=lambda kv: -(kv[1].get("cur") or 0))]
        # 연도별 추이
        trend = []
        for yy in years_avail:
            f = fill_derived(dict(amounts[yy]))
            trend.append({"year": yy, "revenue": f.get(C.REVENUE), "op": f.get(C.OP), "net": f.get(C.NET), "opm": (f[C.OP] / f[C.REVENUE]) if f.get(C.REVENUE) and f.get(C.OP) is not None else None})
        # 업종 평균 & 비교 기업
        secs, total = sector_metrics(conn, y)
        sector_avg = next((_strip(s) for s in secs if s["sector"] == row["sector"]), None)
        peer_ids = [int(p) for p in peers.split(",") if p.strip().isdigit() and int(p) != cid][:4]
        peer_rows = [_strip(r) for r in company_metrics(conn, y, [cid] + peer_ids)] if peer_ids else []
        peer_rows = [r for r in peer_rows if r["id"] != cid]
        return {"year": y, "years": years_avail, "company": _strip(m), "statement": statement, "balance": balance, "sga_detail": sga_detail, "trend": trend, "sector_avg": sector_avg, "total_avg": _strip(total) if total else None, "peers": peer_rows}
    finally:
        conn.close()


@app.put("/api/company/{cid}")
def update_company(cid: int, body: dict):
    allowed = {k: body[k] for k in ("sector", "category", "description", "include_in_sector", "corp_code") if k in body}
    if not allowed:
        raise HTTPException(400, "수정할 필드 없음")
    if "include_in_sector" in allowed:
        allowed["include_in_sector"] = 1 if allowed["include_in_sector"] else 0
    sets = ", ".join(f"{k}=?" for k in allowed)
    with get_conn() as conn:
        conn.execute(f"UPDATE companies SET {sets} WHERE id=?", (*allowed.values(), cid))
    return {"ok": True}


@app.post("/api/refresh")
def refresh(source: str = Query("all", pattern="^(all|inbox|dart)$"), year: int | None = None):
    if refresh_state()["running"]:
        return {"status": "busy"}
    sources = ("inbox", "dart") if source == "all" else (source,)
    threading.Thread(target=run_refresh, args=(sources, year), daemon=True).start()
    return {"status": "started", "sources": sources}


@app.get("/api/refresh/status")
def refresh_status(limit: int = 20):
    conn = connect()
    try:
        logs = [dict(r) for r in conn.execute("SELECT * FROM refresh_log ORDER BY id DESC LIMIT ?", (limit,))]
        files = [dict(r) for r in conn.execute("SELECT * FROM import_files ORDER BY imported_at DESC")]
        return {**refresh_state(), "schedule": REFRESH_SCHEDULE, "next_run": scheduler.next_run(), "dart_enabled": bool(DART_API_KEY), "logs": logs, "files": files}
    finally:
        conn.close()


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    if not file.filename or Path(file.filename).suffix.lower() not in (".xlsm", ".xlsx"):
        raise HTTPException(400, "xlsm/xlsx 파일만 업로드 가능")
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    dest = INBOX_DIR / Path(file.filename).name
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    res = refresh_inbox()
    return {"saved": dest.name, "result": res}


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


@app.get("/")
def index():
    return FileResponse(str(STATIC_DIR / "index.html"))
