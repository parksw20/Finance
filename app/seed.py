"""data/seed/*.csv -> DB (최초 실행 시 자동)."""
import csv

from .config import SEED_DIR
from .importer import write_to_db


def load_seed():
    comp_f, map_f, fact_f = SEED_DIR / "companies.csv", SEED_DIR / "account_map.csv", SEED_DIR / "facts.csv"
    if not (comp_f.exists() and fact_f.exists()):
        return None
    companies, account_map, facts = {}, {}, {}
    with open(comp_f, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            companies[r["name"]] = {
                "name": r["name"],
                "sector": r["sector"] or None,
                "category": r["category"] or None,
                "description": r["description"] or None,
                "include_in_sector": int(r["include_in_sector"] or 1),
                "listed": int(r["listed"]) if r.get("listed") not in (None, "") else None,
            }
    if map_f.exists():
        with open(map_f, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                account_map[r["source_name"]] = r["category"]
    with open(fact_f, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r["company"] not in companies:
                companies[r["company"]] = {"name": r["company"], "sector": None, "category": None, "description": None, "include_in_sector": 1}
            facts[(r["company"], r["category"], r["item"], int(r["fiscal_year"]), r.get("period") or "FY")] = float(r["amount"])
    n = write_to_db(companies, account_map, facts, source="seed")
    return {"companies": len(companies), "account_map": len(account_map), "facts": n}


def backfill_listed():
    """이미 적재된 DB 에서 listed 가 비어 있는 기업을 seed CSV 값으로 채움 (구버전 DB 마이그레이션용)."""
    comp_f = SEED_DIR / "companies.csv"
    if not comp_f.exists():
        return 0
    from .db import get_conn

    with open(comp_f, encoding="utf-8", newline="") as f:
        seed = {r["name"]: r.get("listed") for r in csv.DictReader(f) if r.get("listed") not in (None, "")}
    n = 0
    with get_conn() as conn:
        for row in conn.execute("SELECT id, name FROM companies WHERE listed IS NULL").fetchall():
            if row["name"] in seed:
                conn.execute("UPDATE companies SET listed=? WHERE id=?", (int(seed[row["name"]]), row["id"]))
                n += 1
    return n
