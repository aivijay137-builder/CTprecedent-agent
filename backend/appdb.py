"""App state in SQLite (app.db): runs, packages, and a log of every decision. Separate from the data DBs."""
import json
import os
import sqlite3
from contextlib import closing
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
DB = (Path(os.environ["DATA_DIR"]) if os.environ.get("DATA_DIR") else Path(__file__).resolve().parent.parent) / "app.db"  # Railway: the /data volume


def _c():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def init():
    with closing(_c()) as c, c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS runs(run_id TEXT PRIMARY KEY, parent_run_id TEXT, created_at TEXT, result TEXT);
        CREATE TABLE IF NOT EXISTS packages(package_id TEXT PRIMARY KEY, run_id TEXT, created_at TEXT, snapshot TEXT);
        CREATE TABLE IF NOT EXISTS llm_cache(key TEXT PRIMARY KEY, task TEXT, prompt_version TEXT, model TEXT, response TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS llm_log(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, task TEXT, model TEXT, prompt_version TEXT,
            prompt_tokens INTEGER, completion_tokens INTEGER, cost_usd REAL, seconds REAL, status TEXT, error TEXT);
        CREATE TABLE IF NOT EXISTS cutoff_cache(nct_id TEXT, key TEXT, prompt_version TEXT, status TEXT, value TEXT, unit TEXT, source TEXT,
            model TEXT, created_at TEXT, PRIMARY KEY (nct_id, key, prompt_version));
        CREATE TABLE IF NOT EXISTS usage(day TEXT, visitor TEXT, n INTEGER, PRIMARY KEY (day, visitor));
        CREATE TABLE IF NOT EXISTS decisions(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, role TEXT, kind TEXT,
            run_id TEXT, package_id TEXT, flag_id TEXT, action TEXT, reason TEXT);
        """)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def save_run(result: dict, parent: str | None = None):
    with closing(_c()) as c, c:
        c.execute("INSERT OR REPLACE INTO runs VALUES(?,?,?,?)",
                  (result["run_id"], parent, now(), json.dumps(result)))


def load_run(run_id: str) -> dict | None:
    with closing(_c()) as c, c:
        r = c.execute("SELECT result FROM runs WHERE run_id=?", (run_id,)).fetchone()
    return json.loads(r["result"]) if r else None


def save_package(snap: dict):
    with closing(_c()) as c, c:
        c.execute("INSERT OR REPLACE INTO packages VALUES(?,?,?,?)",
                  (snap["package_id"], snap["run_id"], snap["created_at"], json.dumps(snap)))


def load_package(pid: str) -> dict | None:
    with closing(_c()) as c, c:
        r = c.execute("SELECT snapshot FROM packages WHERE package_id=?", (pid,)).fetchone()
    return json.loads(r["snapshot"]) if r else None


def log(role: str, kind: str, action: str, run_id=None, package_id=None, flag_id=None, reason=None):
    with closing(_c()) as c, c:
        c.execute("INSERT INTO decisions(ts,role,kind,run_id,package_id,flag_id,action,reason) VALUES(?,?,?,?,?,?,?,?)",
                  (now(), role, kind, run_id, package_id, flag_id, action, reason))


def use_check(visitor: str, limit: int) -> bool:
    """Count one precedent check for this visitor today (UTC). False = over the daily limit. limit <= 0 means no limit."""
    if limit <= 0:
        return True
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with closing(_c()) as c, c:
        n = (c.execute("SELECT n FROM usage WHERE day=? AND visitor=?", (day, visitor)).fetchone() or [0])[0]
        if n >= limit:
            return False
        c.execute("INSERT OR REPLACE INTO usage VALUES (?,?,?)", (day, visitor, n + 1))
    return True
