"""SQLite 연결 및 스키마."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    sector TEXT,
    category TEXT,
    description TEXT,
    include_in_sector INTEGER NOT NULL DEFAULT 1,
    corp_code TEXT,
    stock_code TEXT,
    listed INTEGER,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS account_map (
    source_name TEXT PRIMARY KEY,
    category TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    item TEXT NOT NULL DEFAULT '',
    fiscal_year INTEGER NOT NULL,
    period TEXT NOT NULL DEFAULT 'FY',
    amount REAL NOT NULL,
    source TEXT NOT NULL DEFAULT 'excel',
    updated_at TEXT,
    UNIQUE(company_id, category, item, fiscal_year, period)
);
CREATE INDEX IF NOT EXISTS idx_facts_company_year ON facts(company_id, fiscal_year);
CREATE INDEX IF NOT EXISTS idx_facts_category ON facts(category);
CREATE TABLE IF NOT EXISTS refresh_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    rows_written INTEGER DEFAULT 0,
    message TEXT
);
CREATE TABLE IF NOT EXISTS import_files (
    path TEXT PRIMARY KEY,
    mtime REAL NOT NULL,
    size INTEGER NOT NULL,
    imported_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def now() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


MIGRATIONS = [
    ("companies", "listed", "ALTER TABLE companies ADD COLUMN listed INTEGER"),
]

# facts 에 period 컬럼 추가 (유니크 키가 바뀌므로 테이블 재생성)
FACTS_PERIOD_MIGRATION = """
CREATE TABLE facts_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    item TEXT NOT NULL DEFAULT '',
    fiscal_year INTEGER NOT NULL,
    period TEXT NOT NULL DEFAULT 'FY',
    amount REAL NOT NULL,
    source TEXT NOT NULL DEFAULT 'excel',
    updated_at TEXT,
    UNIQUE(company_id, category, item, fiscal_year, period)
);
INSERT INTO facts_new(id, company_id, category, item, fiscal_year, period, amount, source, updated_at)
  SELECT id, company_id, category, item, fiscal_year, 'FY', amount, source, updated_at FROM facts;
DROP TABLE facts;
ALTER TABLE facts_new RENAME TO facts;
CREATE INDEX IF NOT EXISTS idx_facts_company_year ON facts(company_id, fiscal_year);
CREATE INDEX IF NOT EXISTS idx_facts_category ON facts(category);
"""


def init_db():
    with connect() as conn:
        conn.executescript(SCHEMA)
        for table, col, ddl in MIGRATIONS:
            cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
            if col not in cols:
                conn.execute(ddl)
        fcols = {r[1] for r in conn.execute("PRAGMA table_info(facts)")}
        if "period" not in fcols:
            conn.executescript(FACTS_PERIOD_MIGRATION)


@contextmanager
def get_conn():
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def get_setting(conn, key, default=None):
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn, key, value):
    conn.execute(
        "INSERT INTO settings(key, value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )
