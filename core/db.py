"""SQLite persistence (swap for Postgres/Azure SQL in production - same table design).
Generic tables: records, items (kind = section key from usecase.yaml), chunks, llm_calls, llm_cache, feedback, audit.
Each use case gets its own DB file (data/<usecase>.db) so switching USECASE never mixes data."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from core.config import get_settings
from core.schemas import Insights

SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    record_date TEXT,
    category TEXT,
    source_name TEXT,
    content TEXT NOT NULL,
    insights_json TEXT NOT NULL,
    pii_masked INTEGER DEFAULT 0,
    guardrail_flags TEXT DEFAULT '[]',
    approved INTEGER DEFAULT 0,
    created_by TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id INTEGER NOT NULL REFERENCES records(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    text TEXT NOT NULL,
    owner TEXT,
    deadline TEXT,
    status TEXT DEFAULT 'open',
    evidence TEXT,
    confidence REAL,
    grounded INTEGER DEFAULT 1,
    attributes TEXT DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id INTEGER NOT NULL REFERENCES records(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    text TEXT NOT NULL,
    embedding TEXT
);
CREATE TABLE IF NOT EXISTS llm_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT, task TEXT, provider TEXT, model TEXT,
    prompt_tokens INTEGER, completion_tokens INTEGER,
    latency_ms INTEGER, cached INTEGER, cost_usd REAL, status TEXT, error TEXT
);
CREATE TABLE IF NOT EXISTS llm_cache (
    key TEXT PRIMARY KEY, response TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT, username TEXT, record_id INTEGER, target TEXT, rating INTEGER, comment TEXT
);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT, username TEXT, action TEXT, detail TEXT
);
CREATE INDEX IF NOT EXISTS ix_items_record ON items(record_id);
CREATE INDEX IF NOT EXISTS ix_chunks_record ON chunks(record_id);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def conn():
    path = get_settings().db_path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(path, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_db() -> None:
    with conn() as c:
        c.executescript(SCHEMA)


# ---------------- records ----------------
def _category(ins: Insights) -> str:
    return next(iter(ins.fields.values()), "") if ins.fields else ""


def save_record(title: str, record_date: str, source_name: str, content: str,
                ins: Insights, pii_masked: bool, flags: list[str], user: str) -> int:
    with conn() as c:
        cur = c.execute(
            "INSERT INTO records(title, record_date, category, source_name, content, insights_json,"
            " pii_masked, guardrail_flags, created_by, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (title, record_date, _category(ins), source_name, content, ins.model_dump_json(),
             int(pii_masked), json.dumps(flags), user, now()))
        rid = cur.lastrowid
        _write_items(c, rid, ins)
    audit(user, "record.create", f"id={rid} title={title}")
    return rid


def _write_items(c, rid: int, ins: Insights) -> None:
    c.execute("DELETE FROM items WHERE record_id=?", (rid,))
    for kind, it in ins.all_items():
        c.execute(
            "INSERT INTO items(record_id, kind, text, owner, deadline, status, evidence, confidence, grounded, attributes)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (rid, kind, it.text, it.owner, it.deadline, it.status, it.evidence, it.confidence, int(it.grounded),
             json.dumps(it.attributes)))


def update_insights(rid: int, ins: Insights, approved: bool, user: str) -> None:
    with conn() as c:
        c.execute("UPDATE records SET insights_json=?, approved=?, category=?, title=? WHERE id=?",
                  (ins.model_dump_json(), int(approved), _category(ins), ins.title, rid))
        _write_items(c, rid, ins)
    audit(user, "record.review", f"id={rid} approved={approved}")


def list_records(search: str = "") -> list[dict]:
    q = "SELECT id, title, record_date, category, approved, created_at, insights_json FROM records"
    args: tuple = ()
    if search:
        q += (" WHERE title LIKE ? OR insights_json LIKE ? OR id IN "
              "(SELECT record_id FROM items WHERE text LIKE ? OR owner LIKE ?)")
        s = f"%{search}%"
        args = (s, s, s, s)
    q += " ORDER BY COALESCE(NULLIF(record_date, ''), created_at) DESC, id DESC"
    with conn() as c:
        return [dict(r) for r in c.execute(q, args).fetchall()]


def get_record(rid: int) -> dict | None:
    with conn() as c:
        r = c.execute("SELECT * FROM records WHERE id=?", (rid,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["insights"] = Insights.model_validate_json(d["insights_json"])
    d["guardrail_flags"] = json.loads(d.get("guardrail_flags") or "[]")
    return d


def delete_record(rid: int, user: str) -> None:
    with conn() as c:
        c.execute("DELETE FROM records WHERE id=?", (rid,))
    audit(user, "record.delete", f"id={rid}")


def all_items(kind: str | None = None) -> list[dict]:
    q = ("SELECT i.*, r.title AS record_title, r.record_date FROM items i "
         "JOIN records r ON r.id = i.record_id")
    args: tuple = ()
    if kind:
        q += " WHERE i.kind=?"
        args = (kind,)
    with conn() as c:
        rows = [dict(r) for r in c.execute(q, args).fetchall()]
    for r in rows:
        r["attributes"] = json.loads(r.get("attributes") or "{}")
    return rows


# ---------------- chunks (RAG) ----------------
def save_chunks(rid: int, chunks: list[str], embeddings: list[list[float]] | None) -> None:
    with conn() as c:
        c.execute("DELETE FROM chunks WHERE record_id=?", (rid,))
        for i, t in enumerate(chunks):
            emb = json.dumps(embeddings[i]) if embeddings else None
            c.execute("INSERT INTO chunks(record_id, idx, text, embedding) VALUES (?,?,?,?)", (rid, i, t, emb))


def load_chunks(record_ids: list[int] | None = None) -> list[dict]:
    q = "SELECT c.record_id, c.idx, c.text, c.embedding, r.title FROM chunks c JOIN records r ON r.id=c.record_id"
    args: tuple = ()
    if record_ids:
        q += f" WHERE c.record_id IN ({','.join('?' * len(record_ids))})"
        args = tuple(record_ids)
    with conn() as c:
        rows = [dict(r) for r in c.execute(q, args).fetchall()]
    for r in rows:
        r["embedding"] = json.loads(r["embedding"]) if r["embedding"] else None
    return rows


# ---------------- observability / cache / feedback / audit ----------------
def log_llm_call(**kw) -> None:
    with conn() as c:
        c.execute(
            "INSERT INTO llm_calls(ts, task, provider, model, prompt_tokens, completion_tokens, latency_ms,"
            " cached, cost_usd, status, error) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (now(), kw.get("task"), kw.get("provider"), kw.get("model"), kw.get("prompt_tokens", 0),
             kw.get("completion_tokens", 0), kw.get("latency_ms", 0), int(kw.get("cached", False)),
             kw.get("cost_usd", 0.0), kw.get("status", "ok"), kw.get("error")))


def tokens_used_today() -> int:
    today = now()[:10]
    with conn() as c:
        r = c.execute("SELECT COALESCE(SUM(prompt_tokens + completion_tokens), 0) FROM llm_calls "
                      "WHERE substr(ts,1,10)=? AND cached=0", (today,)).fetchone()
    return int(r[0])


def llm_calls(limit: int = 500) -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM llm_calls ORDER BY id DESC LIMIT ?", (limit,))]


def cache_get(key: str) -> str | None:
    with conn() as c:
        r = c.execute("SELECT response FROM llm_cache WHERE key=?", (key,)).fetchone()
    return r[0] if r else None


def cache_put(key: str, response: str) -> None:
    with conn() as c:
        c.execute("INSERT OR REPLACE INTO llm_cache(key, response, created_at) VALUES (?,?,?)", (key, response, now()))


def add_feedback(user: str, record_id: int | None, target: str, rating: int, comment: str = "") -> None:
    with conn() as c:
        c.execute("INSERT INTO feedback(ts, username, record_id, target, rating, comment) VALUES (?,?,?,?,?,?)",
                  (now(), user, record_id, target, rating, comment))


def feedback_rows() -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM feedback ORDER BY id DESC")]


def audit(user: str, action: str, detail: str = "") -> None:
    with conn() as c:
        c.execute("INSERT INTO audit(ts, username, action, detail) VALUES (?,?,?,?)", (now(), user, action, detail))


def audit_rows(limit: int = 200) -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,))]
