"""데이터 갱신 오케스트레이션.

소스
 1. data/inbox/ 에 놓인 엑셀 파일(참고 워크북과 동일 양식) — 새 파일/변경된 파일만 임포트
 2. DART OpenAPI — DART_API_KEY 가 있으면 상장사 재무제표를 최신 사업연도 기준으로 갱신

수동 실행:  python -m app.refresh [--dart] [--inbox] [--year 2025]
"""
import argparse
import logging
import threading
import traceback
from pathlib import Path

from . import categories as C
from . import dart
from .config import DART_API_KEY, DART_QUARTERLY, INBOX_DIR, PUBLISH_AFTER_REFRESH
from .db import get_conn, now, init_db
from .importer import import_file, write_to_db
from .metrics import default_year

log = logging.getLogger("finance.refresh")
_lock = threading.Lock()
_state = {"running": False, "last": None, "cancel": False, "started_at": None}


def request_cancel():
    """진행 중인 갱신에 중단 요청 (현재 기업 처리 후 종료)."""
    if _state["running"]:
        _state["cancel"] = True
        return True
    return False


def _log_start(conn, source):
    cur = conn.execute("INSERT INTO refresh_log(source, started_at, status) VALUES(?,?,?)", (source, now(), "running"))
    return cur.lastrowid


def _log_progress(conn, log_id, message):
    conn.execute("UPDATE refresh_log SET message=? WHERE id=?", (message, log_id))


def _log_end(conn, log_id, status, rows=0, message=None):
    conn.execute(
        "UPDATE refresh_log SET finished_at=?, status=?, rows_written=?, message=? WHERE id=?",
        (now(), status, rows, message, log_id),
    )


def refresh_inbox(manual=False):
    """inbox 의 새/변경 엑셀 파일 임포트. manual=True 면 변경 없음도 이력에 남김."""
    results = []
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in INBOX_DIR.iterdir() if p.suffix.lower() in (".xlsm", ".xlsx") and not p.name.startswith("~$"))
    for p in files:
        if _state["cancel"]:
            break
        st = p.stat()
        with get_conn() as conn:
            prev = conn.execute("SELECT mtime, size FROM import_files WHERE path=?", (str(p),)).fetchone()
            if prev and abs(prev["mtime"] - st.st_mtime) < 1e-6 and prev["size"] == st.st_size:
                continue
            log_id = _log_start(conn, f"excel:{p.name}")
        try:
            res = import_file(p)
            with get_conn() as conn:
                conn.execute(
                    "INSERT INTO import_files(path, mtime, size, imported_at) VALUES(?,?,?,?) ON CONFLICT(path) DO UPDATE SET mtime=excluded.mtime, size=excluded.size, imported_at=excluded.imported_at",
                    (str(p), st.st_mtime, st.st_size, now()),
                )
                _log_end(conn, log_id, "ok", res["facts"], f"기업 {res['companies']}개, 매핑 {res['account_map']}개")
            results.append({"file": p.name, **res})
        except Exception as e:  # noqa: BLE001
            with get_conn() as conn:
                _log_end(conn, log_id, "error", 0, f"{e}\n{traceback.format_exc()[-800:]}")
            results.append({"file": p.name, "error": str(e)})
    if manual and not results:
        with get_conn() as conn:
            log_id = _log_start(conn, "excel:inbox")
            _log_end(conn, log_id, "ok", 0, "새로운/변경된 엑셀 파일 없음")
    return results


def refresh_dart(year=None, company_ids=None):
    """DART 에서 상장사 재무제표 갱신."""
    if not DART_API_KEY:
        with get_conn() as conn:
            log_id = _log_start(conn, "dart")
            _log_end(conn, log_id, "skipped", 0, "DART_API_KEY 미설정 → 건너뜀 (.env 또는 키체인에 키를 넣고 서버를 재시작하세요)")
        return {"skipped": "DART_API_KEY 미설정"}
    with get_conn() as conn:
        log_id = _log_start(conn, "dart")
        year = year or default_year(conn)
        if year is None:
            _log_end(conn, log_id, "skipped", 0, "데이터가 없어 기준 연도를 정할 수 없음 (seed 또는 엑셀을 먼저 적재하세요)")
            return {"skipped": "기준 연도 없음"}
        account_map = {r["source_name"]: r["category"] for r in conn.execute("SELECT * FROM account_map")}
        q = "SELECT id, name, corp_code, fiscal_month FROM companies"
        if company_ids:
            q += " WHERE id IN (%s)" % ",".join(str(int(i)) for i in company_ids)
        companies = [dict(r) for r in conn.execute(q)]
    updated, skipped, errors = [], [], []
    total = 0
    try:
        codes = dart.load_corp_codes()
        for idx, c in enumerate(companies, 1):
            if _state["cancel"]:
                skipped.append({"name": c["name"], "reason": "사용자 중단"})
                break
            if idx == 1 or idx % 5 == 0:
                msg = f"{idx}/{len(companies)} 처리 중 · {c['name']} (갱신 {len(updated)}, 건너뜀 {len(skipped)}, 오류 {len(errors)})"
                log.info(msg)
                with get_conn() as conn:
                    _log_progress(conn, log_id, msg)
            rec = None
            if c["corp_code"]:
                rec = {"corp_code": c["corp_code"], "stock_code": ""}
            else:
                rec = dart.resolve_corp(c["name"], codes)
                if rec:
                    with get_conn() as conn:
                        conn.execute(
                            "UPDATE companies SET corp_code=?, stock_code=?, listed=? WHERE id=?",
                            (rec["corp_code"], rec["stock_code"] or None, 1 if rec["stock_code"] else 0, c["id"]),
                        )
            if not rec:
                skipped.append({"name": c["name"], "reason": "DART 기업코드 없음"})
                continue
            try:
                if c.get("fiscal_month") is None:
                    info = dart.fetch_company_info(rec["corp_code"])
                    if info and info["fiscal_month"]:
                        with get_conn() as conn:
                            conn.execute("UPDATE companies SET fiscal_month=? WHERE id=?", (info["fiscal_month"], c["id"]))
                # 수집 대상: (연도, 기간) — 연간은 year, 분기는 year 와 다음 연도(진행 중인 해)
                # 연간 사업보고서를 먼저 조회. 없으면(비상장·미제출) 분기 조회 없이 건너뜀
                fs_used, rows = dart.fetch_statements(rec["corp_code"], year, dart.REPORT_CODES["FY"])
                if not rows:
                    skipped.append({"name": c["name"], "reason": f"{year}년 사업보고서 없음(비상장 또는 미제출)"})
                    continue
                all_facts = dict(dart.to_facts(rows, year, account_map, "FY"))
                if DART_QUARTERLY:
                    # 연간에서 확인된 연결/별도 구분을 그대로 써서 분기당 1회만 호출
                    for y in (year, year + 1):
                        for q in ("Q1", "Q2", "Q3"):
                            _fs, qrows = dart.fetch_statements(rec["corp_code"], y, dart.REPORT_CODES[q], prefer=fs_used)
                            if qrows:
                                all_facts.update(dart.to_facts(qrows, y, account_map, q))
                            elif y == year + 1:
                                break  # 진행 중인 해는 최신 분기까지만 존재 → 이후 분기는 조회 생략
                if not all_facts:
                    skipped.append({"name": c["name"], "reason": "매핑 가능한 계정 없음"})
                    continue
                # 순운전자본(+/-)은 DART 표준계정이 엑셀 원장보다 거칠므로, 연간은 기존 데이터가 있으면 유지
                with get_conn() as conn:
                    has_nwc = {r[0] for r in conn.execute(
                        "SELECT DISTINCT fiscal_year FROM facts WHERE company_id=? AND category IN (?,?) AND period='FY' AND source!='dart'",
                        (c["id"], C.NWC_PLUS, C.NWC_MINUS))}
                all_facts = {k: v for k, v in all_facts.items() if not (k[0] in dart.NWC_CATEGORIES and k[3] == "FY" and k[2] in has_nwc)}
                keyed = {(c["name"], cat, item, y, period): a for (cat, item, y, period), a in all_facts.items()}
                # 해당 (기업, 계정분류, 연도, 기간)의 기존 항목을 DART 값으로 대체
                with get_conn() as conn:
                    for (cat, _item, y, period) in all_facts:
                        conn.execute("DELETE FROM facts WHERE company_id=? AND category=? AND fiscal_year=? AND period=?", (c["id"], cat, y, period))
                n = write_to_db({}, {}, keyed, source="dart", replace_company_facts=False)
                total += n
                nq = len({(k[2], k[3]) for k in all_facts if k[3] != "FY"})
                updated.append({"name": c["name"], "fs": fs_used, "facts": n, "quarters": nq})
            except Exception as e:  # noqa: BLE001
                log.warning("%s: %s", c["name"], e)
                errors.append({"name": c["name"], "error": str(e)})
        status = "ok" if not errors else ("partial" if updated else "error")
        nq = sum(u.get("quarters", 0) for u in updated)
        msg = f"갱신 {len(updated)}개, 건너뜀 {len(skipped)}개, 오류 {len(errors)}개 (연간 {year}년, 분기 데이터 {nq}건)"
        if _state["cancel"]:
            status, msg = "cancelled", "사용자 중단 · " + msg
    except Exception as e:  # noqa: BLE001
        status, msg = "error", f"{e}"
    with get_conn() as conn:
        _log_end(conn, log_id, status, total, msg)
    return {"year": year, "updated": updated, "skipped": skipped, "errors": errors, "status": status}


def close_stale_runs():
    """서버 재시작 등으로 끝나지 못한 'running' 이력을 interrupted 로 정리."""
    with get_conn() as conn:
        n = conn.execute(
            "UPDATE refresh_log SET status='interrupted', finished_at=?, message=COALESCE(message,'') || ' → 서버 재시작으로 중단됨' WHERE status='running'",
            (now(),),
        ).rowcount
    return n


def run_refresh(sources=("inbox", "dart"), year=None):
    """모든 소스 갱신. 동시 실행 방지."""
    if not _lock.acquire(blocking=False):
        return {"status": "busy", "message": "이미 갱신이 진행 중입니다"}
    _state["running"] = True
    _state["cancel"] = False
    _state["started_at"] = now()
    try:
        result = {"started_at": now()}
        if "inbox" in sources:
            result["inbox"] = refresh_inbox(manual=True)
        if "dart" in sources:
            result["dart"] = refresh_dart(year)
        if PUBLISH_AFTER_REFRESH:
            try:
                from .publish import publish

                result["publish"] = publish()
            except Exception as e:  # noqa: BLE001
                result["publish"] = {"error": str(e)}
        result["finished_at"] = now()
        _state["last"] = result
        return result
    finally:
        _state["running"] = False
        _lock.release()


def refresh_state():
    return dict(_state)


def main():
    ap = argparse.ArgumentParser(description="재무 데이터 갱신")
    ap.add_argument("--dart", action="store_true", help="DART 만")
    ap.add_argument("--inbox", action="store_true", help="inbox 엑셀만")
    ap.add_argument("--year", type=int, default=None, help="DART 조회 사업연도")
    ap.add_argument("--file", help="특정 엑셀 파일을 즉시 임포트")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", force=True)
    init_db()
    # DB 가 비어 있으면(CI 등 최초 실행) seed 를 먼저 적재해야 갱신 대상 기업이 생김
    with get_conn() as conn:
        empty = conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0] == 0
    if empty:
        from .seed import load_seed

        print("seed 적재:", load_seed())
    if a.file:
        print(import_file(a.file))
        return
    sources = []
    if a.dart:
        sources.append("dart")
    if a.inbox:
        sources.append("inbox")
    if not sources:
        sources = ["inbox", "dart"]
    import json

    print(json.dumps(run_refresh(sources, a.year), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
