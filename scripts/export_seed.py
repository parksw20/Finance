"""참고 워크북 -> data/seed/*.csv (저장소에 포함되는 초기 데이터)."""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.importer import parse_workbook  # noqa: E402
from app.config import SEED_DIR  # noqa: E402


def main(path):
    companies, account_map, facts = parse_workbook(path)
    SEED_DIR.mkdir(parents=True, exist_ok=True)
    with open(SEED_DIR / "companies.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["name", "sector", "category", "description", "include_in_sector"])
        for c in companies.values():
            w.writerow([c["name"], c["sector"] or "", c["category"] or "", c["description"] or "", c["include_in_sector"]])
    with open(SEED_DIR / "account_map.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["source_name", "category"])
        for k, v in sorted(account_map.items()):
            w.writerow([k, v])
    with open(SEED_DIR / "facts.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["company", "category", "item", "fiscal_year", "amount"])
        for (name, cat, item, year), amt in sorted(facts.items()):
            w.writerow([name, cat, item, year, int(amt) if float(amt).is_integer() else amt])
    print(f"companies={len(companies)} account_map={len(account_map)} facts={len(facts)} -> {SEED_DIR}")


if __name__ == "__main__":
    main(sys.argv[1])
