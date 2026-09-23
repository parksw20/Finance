import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SEED_DIR = DATA_DIR / "seed"
INBOX_DIR = DATA_DIR / "inbox"
STATIC_DIR = ROOT / "static"


def _load_dotenv():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()

DB_PATH = Path(os.environ.get("FINANCE_DB", str(DATA_DIR / "finance.db")))
if not DB_PATH.is_absolute():
    DB_PATH = ROOT / DB_PATH
KEYRING_SERVICE = os.environ.get("FINANCE_KEYRING_SERVICE", "finance-dashboard")


def _from_keyring(name):
    """OS 키체인(Windows 자격 증명 관리자 / macOS Keychain / Secret Service)에서 조회. keyring 미설치 시 None."""
    try:
        import keyring  # noqa: WPS433

        return (keyring.get_password(KEYRING_SERVICE, name) or "").strip() or None
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException:  # noqa: BLE001 - 미설치, 백엔드 없음, 네이티브 모듈 오류(PanicException) 등은 모두 미설정으로 취급
        return None


# 우선순위: 환경변수 > .env > OS 키체인
DART_API_KEY = os.environ.get("DART_API_KEY", "").strip() or _from_keyring("DART_API_KEY") or ""
REFRESH_SCHEDULE = os.environ.get("REFRESH_SCHEDULE", "0 6 * * *").strip()
REFRESH_ON_START = os.environ.get("REFRESH_ON_START", "false").lower() in ("1", "true", "yes")
# DART 분기보고서(1분기·반기·3분기)도 수집할지. false 면 연간만
DART_QUARTERLY = os.environ.get("DART_QUARTERLY", "true").lower() in ("1", "true", "yes")
# 자동 갱신 후 docs/ 스냅샷을 내보내고 git push 할지 (GitHub Pages 자동 갱신)
PUBLISH_AFTER_REFRESH = os.environ.get("PUBLISH_AFTER_REFRESH", "false").lower() in ("1", "true", "yes")
