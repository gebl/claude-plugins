"""SQLite persistence for session metrics and PR tracking."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("tm-daemon.database")

DB_DIR = Path.home() / ".claude" / "taskmanager"
DB_PATH = DB_DIR / "sessions.db"

_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id        TEXT NOT NULL,
    issue_identifier TEXT NOT NULL,
    project_id      TEXT,
    project_name    TEXT,
    session_id      TEXT,
    branch_name     TEXT,
    outcome         TEXT NOT NULL,
    exit_code       INTEGER,
    timed_out       INTEGER NOT NULL DEFAULT 0,
    duration_seconds REAL,
    duration_api_ms  REAL,
    total_cost_usd   REAL,
    input_tokens     INTEGER,
    output_tokens    INTEGER,
    cache_read_input_tokens    INTEGER,
    cache_creation_input_tokens INTEGER,
    num_turns        INTEGER,
    started_at       TEXT,
    finished_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pull_requests (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER REFERENCES sessions(id),
    issue_id    TEXT NOT NULL,
    pr_url      TEXT NOT NULL,
    branch_name TEXT,
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_issue_id ON sessions(issue_id);
CREATE INDEX IF NOT EXISTS idx_sessions_project_id ON sessions(project_id);
CREATE INDEX IF NOT EXISTS idx_sessions_finished_at ON sessions(finished_at);
CREATE INDEX IF NOT EXISTS idx_pull_requests_issue_id ON pull_requests(issue_id);
"""


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    """Open a connection with row_factory set to sqlite3.Row."""
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: Path | None = None) -> None:
    """Create tables if they don't exist."""
    conn = _connect(db_path)
    try:
        conn.executescript(_SCHEMA_SQL)
        log.info("Database initialized at %s", db_path or DB_PATH)
    finally:
        conn.close()


def record_session(
    *,
    issue_id: str,
    issue_identifier: str,
    project_id: str | None = None,
    project_name: str | None = None,
    session_id: str | None = None,
    branch_name: str | None = None,
    outcome: str,
    exit_code: int | None = None,
    timed_out: bool = False,
    duration_seconds: float | None = None,
    duration_api_ms: float | None = None,
    total_cost_usd: float | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cache_read_input_tokens: int | None = None,
    cache_creation_input_tokens: int | None = None,
    num_turns: int | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
    db_path: Path | None = None,
) -> int:
    """Insert a session record. Returns the row ID."""
    if finished_at is None:
        finished_at = datetime.now(timezone.utc).isoformat()

    conn = _connect(db_path)
    try:
        cur = conn.execute(
            """\
            INSERT INTO sessions (
                issue_id, issue_identifier, project_id, project_name,
                session_id, branch_name, outcome, exit_code, timed_out,
                duration_seconds, duration_api_ms, total_cost_usd,
                input_tokens, output_tokens,
                cache_read_input_tokens, cache_creation_input_tokens,
                num_turns, started_at, finished_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                issue_id,
                issue_identifier,
                project_id,
                project_name,
                session_id,
                branch_name,
                outcome,
                exit_code,
                int(timed_out),
                duration_seconds,
                duration_api_ms,
                total_cost_usd,
                input_tokens,
                output_tokens,
                cache_read_input_tokens,
                cache_creation_input_tokens,
                num_turns,
                started_at,
                finished_at,
            ),
        )
        conn.commit()
        row_id = cur.lastrowid
        log.debug("Recorded session %d for %s (%s)", row_id, issue_identifier, outcome)
        return row_id  # type: ignore[return-value]
    finally:
        conn.close()


def record_pr(
    *,
    issue_id: str,
    pr_url: str,
    branch_name: str | None = None,
    session_id: int | None = None,
    created_at: str | None = None,
    db_path: Path | None = None,
) -> int:
    """Insert a pull request record. Returns the row ID."""
    if created_at is None:
        created_at = datetime.now(timezone.utc).isoformat()

    conn = _connect(db_path)
    try:
        cur = conn.execute(
            """\
            INSERT INTO pull_requests (session_id, issue_id, pr_url, branch_name, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, issue_id, pr_url, branch_name, created_at),
        )
        conn.commit()
        row_id = cur.lastrowid
        log.debug("Recorded PR %s for %s", pr_url, issue_id)
        return row_id  # type: ignore[return-value]
    finally:
        conn.close()


def query_sessions(
    *,
    project_id: str | None = None,
    project_name: str | None = None,
    issue_id: str | None = None,
    issue_identifier: str | None = None,
    since: str | None = None,
    db_path: Path | None = None,
) -> list[dict]:
    """Query sessions with optional filters. Returns list of dicts."""
    conn = _connect(db_path)
    try:
        sql, params = _build_session_query(
            project_id=project_id,
            project_name=project_name,
            issue_id=issue_id,
            issue_identifier=issue_identifier,
            since=since,
        )
        rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def query_pull_requests(
    *,
    issue_id: str | None = None,
    db_path: Path | None = None,
) -> list[dict]:
    """Query pull requests with optional filters."""
    conn = _connect(db_path)
    try:
        if issue_id:
            rows = conn.execute(
                "SELECT * FROM pull_requests WHERE issue_id = ? ORDER BY created_at DESC",
                (issue_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM pull_requests ORDER BY created_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_summary_stats(
    *,
    project_name: str | None = None,
    since: str | None = None,
    db_path: Path | None = None,
) -> dict:
    """Get aggregate statistics for reporting."""
    conn = _connect(db_path)
    try:
        if project_name and since:
            row = conn.execute(
                _SUMMARY_BY_PROJECT_AND_SINCE,
                (project_name, since),
            ).fetchone()
        elif project_name:
            row = conn.execute(
                _SUMMARY_BY_PROJECT,
                (project_name,),
            ).fetchone()
        elif since:
            row = conn.execute(
                _SUMMARY_BY_SINCE,
                (since,),
            ).fetchone()
        else:
            row = conn.execute(_SUMMARY_ALL).fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


_SUMMARY_COLUMNS = """\
    COUNT(*) as total_sessions,
    COALESCE(SUM(total_cost_usd), 0) as total_cost,
    COALESCE(SUM(input_tokens), 0) as total_input_tokens,
    COALESCE(SUM(output_tokens), 0) as total_output_tokens,
    COALESCE(AVG(duration_seconds), 0) as avg_duration,
    COALESCE(SUM(num_turns), 0) as total_turns,
    COUNT(DISTINCT issue_id) as unique_issues"""

# nosemgrep: python.lang.security.audit.formatted-sql-query
_SUMMARY_ALL = "SELECT" + _SUMMARY_COLUMNS + " FROM sessions"
_SUMMARY_BY_PROJECT = "SELECT" + _SUMMARY_COLUMNS + " FROM sessions WHERE project_name = ?"
_SUMMARY_BY_SINCE = "SELECT" + _SUMMARY_COLUMNS + " FROM sessions WHERE finished_at >= ?"
_SUMMARY_BY_PROJECT_AND_SINCE = (
    "SELECT" + _SUMMARY_COLUMNS + " FROM sessions WHERE project_name = ? AND finished_at >= ?"
)


def _build_session_query(
    *,
    project_id: str | None = None,
    project_name: str | None = None,
    issue_id: str | None = None,
    issue_identifier: str | None = None,
    since: str | None = None,
) -> tuple[str, tuple[str, ...]]:
    """Select the right static SQL query based on which filters are active.

    All SQL is pre-defined — no dynamic string building from user input.
    """
    # Encode the active filter combination as a frozenset of keys
    active: set[str] = set()
    params: list[str] = []
    if project_id:
        active.add("project_id")
        params.append(project_id)
    if project_name:
        active.add("project_name")
        params.append(project_name)
    if issue_id:
        active.add("issue_id")
        params.append(issue_id)
    if issue_identifier:
        active.add("issue_identifier")
        params.append(issue_identifier)
    if since:
        active.add("since")
        params.append(since)

    key = frozenset(active)
    sql = _SESSION_QUERIES.get(key)
    if sql is None:
        raise ValueError(f"Unsupported filter combination: {sorted(active)}")
    return sql, tuple(params)


# Static query lookup — every supported filter combination has a pre-built query.
# Parameter order must match the order filters are added in _build_session_query.
_Q = "SELECT * FROM sessions"
_SESSION_QUERIES: dict[frozenset[str], str] = {
    frozenset(): _Q + " ORDER BY finished_at DESC",
    frozenset({"project_id"}): _Q + " WHERE project_id = ? ORDER BY finished_at DESC",
    frozenset({"project_name"}): _Q + " WHERE project_name = ? ORDER BY finished_at DESC",
    frozenset({"issue_id"}): _Q + " WHERE issue_id = ? ORDER BY finished_at DESC",
    frozenset({"issue_identifier"}): _Q + " WHERE issue_identifier = ? ORDER BY finished_at DESC",
    frozenset({"since"}): _Q + " WHERE finished_at >= ? ORDER BY finished_at DESC",
    frozenset({"project_id", "since"}): _Q + " WHERE project_id = ? AND finished_at >= ? ORDER BY finished_at DESC",
    frozenset({"project_name", "since"}): _Q + " WHERE project_name = ? AND finished_at >= ? ORDER BY finished_at DESC",
    frozenset({"issue_id", "since"}): _Q + " WHERE issue_id = ? AND finished_at >= ? ORDER BY finished_at DESC",
    frozenset({"issue_identifier", "since"}): _Q + " WHERE issue_identifier = ? AND finished_at >= ? ORDER BY finished_at DESC",
    frozenset({"project_id", "issue_id"}): _Q + " WHERE project_id = ? AND issue_id = ? ORDER BY finished_at DESC",
    frozenset({"project_name", "issue_identifier"}): _Q + " WHERE project_name = ? AND issue_identifier = ? ORDER BY finished_at DESC",
    frozenset({"project_id", "issue_id", "since"}): _Q + " WHERE project_id = ? AND issue_id = ? AND finished_at >= ? ORDER BY finished_at DESC",
    frozenset({"project_name", "issue_identifier", "since"}): _Q + " WHERE project_name = ? AND issue_identifier = ? AND finished_at >= ? ORDER BY finished_at DESC",
}
