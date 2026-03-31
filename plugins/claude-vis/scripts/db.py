"""SQLite database module for claude-vis session logging."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_DIR = Path.home() / ".config" / "claude-vis"
DB_PATH = DB_DIR / "sessions.db"

SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    model TEXT,
    cwd TEXT,
    git_repo TEXT,
    git_branch TEXT,
    permission_mode TEXT,
    session_source TEXT,
    started_at TEXT,
    ended_at TEXT,
    duration_ms INTEGER,
    total_input_tokens INTEGER DEFAULT 0,
    total_output_tokens INTEGER DEFAULT 0,
    cache_creation_tokens INTEGER DEFAULT 0,
    cache_read_tokens INTEGER DEFAULT 0,
    total_cost_usd REAL DEFAULT 0.0,
    lines_added INTEGER DEFAULT 0,
    lines_removed INTEGER DEFAULT 0,
    turn_count INTEGER DEFAULT 0,
    summary TEXT
);

CREATE TABLE IF NOT EXISTS tool_uses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(session_id),
    tool_name TEXT NOT NULL,
    tool_use_id TEXT,
    timestamp TEXT NOT NULL,
    success INTEGER,
    agent_id TEXT
);

CREATE TABLE IF NOT EXISTS commands_run (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(session_id),
    command TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    exit_code INTEGER,
    agent_id TEXT
);

CREATE TABLE IF NOT EXISTS urls_fetched (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(session_id),
    url TEXT NOT NULL,
    source TEXT NOT NULL,
    query TEXT,
    timestamp TEXT NOT NULL,
    agent_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_cwd ON sessions(cwd);
CREATE INDEX IF NOT EXISTS idx_sessions_started ON sessions(started_at);
CREATE INDEX IF NOT EXISTS idx_tool_uses_session ON tool_uses(session_id);
CREATE INDEX IF NOT EXISTS idx_commands_session ON commands_run(session_id);
CREATE INDEX IF NOT EXISTS idx_urls_session ON urls_fetched(session_id);
"""


def get_db() -> sqlite3.Connection:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.executescript(SCHEMA_SQL)
    return conn


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Write operations ────────────────────────────────────────────────────────


def upsert_session(
    *,
    session_id: str,
    model: str | None = None,
    cwd: str | None = None,
    git_repo: str | None = None,
    git_branch: str | None = None,
    permission_mode: str | None = None,
    session_source: str | None = None,
    started_at: str | None = None,
) -> None:
    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO sessions (session_id, model, cwd, git_repo, git_branch,
                   permission_mode, session_source, started_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(session_id) DO UPDATE SET
                   model = COALESCE(excluded.model, sessions.model),
                   cwd = COALESCE(excluded.cwd, sessions.cwd),
                   git_repo = COALESCE(excluded.git_repo, sessions.git_repo),
                   git_branch = COALESCE(excluded.git_branch, sessions.git_branch),
                   permission_mode = COALESCE(excluded.permission_mode, sessions.permission_mode),
                   session_source = COALESCE(excluded.session_source, sessions.session_source),
                   started_at = COALESCE(excluded.started_at, sessions.started_at)
            """,
            (session_id, model, cwd, git_repo, git_branch,
             permission_mode, session_source, started_at),
        )
        conn.commit()
    finally:
        conn.close()


def update_session_end(
    *,
    session_id: str,
    ended_at: str,
    duration_ms: int | None = None,
    summary: str | None = None,
    total_input_tokens: int = 0,
    total_output_tokens: int = 0,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
    total_cost_usd: float = 0.0,
    lines_added: int = 0,
    lines_removed: int = 0,
) -> None:
    conn = get_db()
    try:
        conn.execute(
            """UPDATE sessions SET
                   ended_at = ?,
                   duration_ms = ?,
                   summary = ?,
                   total_input_tokens = ?,
                   total_output_tokens = ?,
                   cache_creation_tokens = ?,
                   cache_read_tokens = ?,
                   total_cost_usd = ?,
                   lines_added = ?,
                   lines_removed = ?
               WHERE session_id = ?
            """,
            (ended_at, duration_ms, summary,
             total_input_tokens, total_output_tokens,
             cache_creation_tokens, cache_read_tokens,
             total_cost_usd, lines_added, lines_removed,
             session_id),
        )
        conn.commit()
    finally:
        conn.close()


def insert_tool_use(
    *,
    session_id: str,
    tool_name: str,
    tool_use_id: str | None = None,
    timestamp: str | None = None,
    success: int = 1,
    agent_id: str | None = None,
) -> None:
    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO tool_uses (session_id, tool_name, tool_use_id, timestamp, success, agent_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (session_id, tool_name, tool_use_id, timestamp or now_iso(), success, agent_id),
        )
        conn.commit()
    finally:
        conn.close()


def insert_command(
    *,
    session_id: str,
    command: str,
    timestamp: str | None = None,
    exit_code: int | None = None,
    agent_id: str | None = None,
) -> None:
    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO commands_run (session_id, command, timestamp, exit_code, agent_id)
               VALUES (?, ?, ?, ?, ?)""",
            (session_id, command, timestamp or now_iso(), exit_code, agent_id),
        )
        conn.commit()
    finally:
        conn.close()


def insert_url(
    *,
    session_id: str,
    url: str,
    source: str,
    query: str | None = None,
    timestamp: str | None = None,
    agent_id: str | None = None,
) -> None:
    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO urls_fetched (session_id, url, source, query, timestamp, agent_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (session_id, url, source, query, timestamp or now_iso(), agent_id),
        )
        conn.commit()
    finally:
        conn.close()


def increment_turn_count(session_id: str) -> None:
    conn = get_db()
    try:
        conn.execute(
            "UPDATE sessions SET turn_count = turn_count + 1 WHERE session_id = ?",
            (session_id,),
        )
        conn.commit()
    finally:
        conn.close()


# ── Read operations ─────────────────────────────────────────────────────────


def recent_sessions(n: int = 10) -> list[dict]:
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT session_id, model, cwd, git_repo, git_branch,
                      started_at, ended_at, duration_ms,
                      total_input_tokens, total_output_tokens,
                      total_cost_usd, turn_count, summary
               FROM sessions
               ORDER BY started_at DESC
               LIMIT ?""",
            (n,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def cost_by_project() -> list[dict]:
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT COALESCE(git_repo, cwd) AS project,
                      COUNT(*) AS session_count,
                      SUM(total_cost_usd) AS total_cost,
                      SUM(total_input_tokens) AS total_input,
                      SUM(total_output_tokens) AS total_output,
                      SUM(duration_ms) AS total_duration_ms
               FROM sessions
               GROUP BY project
               ORDER BY total_cost DESC""",
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def totals() -> dict:
    conn = get_db()
    try:
        row = conn.execute(
            """SELECT COUNT(*) AS session_count,
                      SUM(total_cost_usd) AS total_cost,
                      SUM(total_input_tokens) AS total_input,
                      SUM(total_output_tokens) AS total_output,
                      SUM(duration_ms) AS total_duration_ms,
                      SUM(turn_count) AS total_turns,
                      SUM(lines_added) AS total_lines_added,
                      SUM(lines_removed) AS total_lines_removed
               FROM sessions""",
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


def session_detail(session_id: str) -> dict | None:
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if not row:
            return None

        result = dict(row)

        tools = conn.execute(
            """SELECT tool_name, COUNT(*) AS count
               FROM tool_uses WHERE session_id = ?
               GROUP BY tool_name ORDER BY count DESC""",
            (session_id,),
        ).fetchall()
        result["tools"] = [dict(t) for t in tools]

        commands = conn.execute(
            "SELECT command, timestamp, exit_code FROM commands_run WHERE session_id = ? ORDER BY timestamp",
            (session_id,),
        ).fetchall()
        result["commands"] = [dict(c) for c in commands]

        urls = conn.execute(
            "SELECT url, source, query, timestamp FROM urls_fetched WHERE session_id = ? ORDER BY timestamp",
            (session_id,),
        ).fetchall()
        result["urls"] = [dict(u) for u in urls]

        return result
    finally:
        conn.close()


def top_tools(n: int = 20) -> list[dict]:
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT tool_name, COUNT(*) AS count
               FROM tool_uses
               GROUP BY tool_name
               ORDER BY count DESC
               LIMIT ?""",
            (n,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def recent_commands(n: int = 20) -> list[dict]:
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT c.command, c.timestamp, c.exit_code, c.session_id,
                      s.cwd, s.git_repo
               FROM commands_run c
               JOIN sessions s ON c.session_id = s.session_id
               ORDER BY c.timestamp DESC
               LIMIT ?""",
            (n,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def recent_urls(n: int = 20) -> list[dict]:
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT u.url, u.source, u.query, u.timestamp, u.session_id,
                      s.cwd, s.git_repo
               FROM urls_fetched u
               JOIN sessions s ON u.session_id = s.session_id
               ORDER BY u.timestamp DESC
               LIMIT ?""",
            (n,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_session_started_at(session_id: str) -> str | None:
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT started_at FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return row["started_at"] if row else None
    finally:
        conn.close()
