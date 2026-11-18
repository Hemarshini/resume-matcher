"""Tiny SQLite persistence: one row per analysis session (JSON payload)."""
import json
import sqlite3
import time
import uuid
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "data.db"


def _conn():
    c = sqlite3.connect(DB)
    c.execute("CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, created REAL, payload TEXT)")
    return c


def save(payload: dict) -> str:
    sid = uuid.uuid4().hex[:12]
    with _conn() as c:
        c.execute("INSERT INTO sessions VALUES (?,?,?)", (sid, time.time(), json.dumps(payload)))
    return sid


def load(sid: str) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT payload FROM sessions WHERE id=?", (sid,)).fetchone()
    return json.loads(row[0]) if row else None
