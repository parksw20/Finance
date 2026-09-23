"""정적 사이트 내보내기 (GitHub Pages 등 서버 없는 호스팅용).

    python -m app.export_static [출력폴더]   (기본: site/)

출력:
  index.html            정적 모드 플래그가 포함된 페이지 (경로는 상대경로)
  static/               app.js / style.css / vendor
  data/meta.json        /api/meta 결과 + 생성 시각
  data/sectors_{Y}_{P}.json, data/screener_{Y}_{P}.json
  data/company_{ID}_{Y}_{P}.json   (비교 기업은 화면에서 스크리너 데이터로 계산)
  data/refresh_status.json
"""
import json
import shutil
import sys
from pathlib import Path

from . import categories as C
from .config import ROOT, STATIC_DIR
from .db import connect, init_db, now
from .main import company, meta, refresh_status, screener, sectors
from .metrics import available_periods
from .seed import load_seed


def _dump(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def export(out_dir: Path):
    init_db()
    conn = connect()
    if conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0] == 0:
        load_seed()
    out_dir.mkdir(parents=True, exist_ok=True)
    data = out_dir / "data"
    if data.exists():
        shutil.rmtree(data)
    # 정적 파일
    if (out_dir / "static").exists():
        shutil.rmtree(out_dir / "static")
    shutil.copytree(STATIC_DIR, out_dir / "static")
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    html = html.replace('href="/static/', 'href="./static/').replace('src="/static/', 'src="./static/')
    html = html.replace("<script src=\"./static/app.js\"></script>", f"<script>window.STATIC_MODE = true; window.STATIC_GENERATED_AT = {json.dumps(now())};</script>\n<script src=\"./static/app.js\"></script>")
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")

    m = meta()
    m["static_generated_at"] = now()
    _dump(data / "meta.json", m)
    _dump(data / "refresh_status.json", refresh_status(limit=50))

    periods = [p for p in available_periods(conn) if p["companies"] >= 1]
    n_company = 0
    for p in periods:
        y, per = p["year"], p["period"]
        _dump(data / f"sectors_{y}_{per}.json", sectors(y, per))
        sc = screener(y, per)
        _dump(data / f"screener_{y}_{per}.json", sc)
        for row in sc["companies"]:
            d = company(row["id"], y, per, "")
            d["peers"] = []  # 정적 모드에서는 화면이 스크리너 데이터로 비교 기업을 채움
            _dump(data / f"company_{row['id']}_{y}_{per}.json", d)
            n_company += 1
    conn.close()
    print(f"exported → {out_dir}  (기간 {len(periods)}개, 기업 파일 {n_company}개)")


if __name__ == "__main__":
    export(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "site")
