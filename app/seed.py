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
            facts[(r["company"], r["category"], r["item"], int(r["fiscal_year"]))] = float(r["amount"])
    n = write_to_db(companies, account_map, facts, source="seed")
    return {"companies": len(companies), "account_map": len(account_map), "facts": n}
