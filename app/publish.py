"""정적 스냅샷을 docs/ 에 내보내고 git 커밋·푸시 (GitHub Pages: 브랜치의 /docs 폴더 배포).

    python -m app.publish            # docs/ 갱신 → 변경 있으면 commit + push
    python -m app.publish --no-push  # 커밋만

서버의 자동 갱신 후에도 실행하려면 .env 에 PUBLISH_AFTER_REFRESH=true
"""
import argparse
import logging
import subprocess
from datetime import datetime
from pathlib import Path

from .config import ROOT
from .export_static import export

log = logging.getLogger("finance.publish")
DOCS = ROOT / "docs"


def _git(*args, check=True):
    return subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True, text=True, check=check)


def publish(push=True):
    export(DOCS)
    _git("add", "-A", "docs")
    if not _git("status", "--porcelain", "docs").stdout.strip():
        log.info("docs/ 변경 없음 → 커밋 생략")
        return {"changed": False}
    msg = f"스냅샷 갱신 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    _git("commit", "-m", msg)
    if push:
        branch = _git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        r = _git("push", "-u", "origin", branch, check=False)
        if r.returncode != 0:
            log.error("push 실패: %s", r.stderr.strip())
            return {"changed": True, "pushed": False, "error": r.stderr.strip()}
        log.info("push 완료 (%s)", branch)
        return {"changed": True, "pushed": True, "branch": branch}
    return {"changed": True, "pushed": False}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-push", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", force=True)
    print(publish(push=not a.no_push))
