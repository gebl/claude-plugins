"""Tests for SQLite session metrics database."""

import sqlite3

import pytest

from taskmanager.daemon import database


@pytest.fixture
def db_path(tmp_path):
    """Provide a temporary database path and initialize schema."""
    path = tmp_path / "test_sessions.db"
    database.init_db(db_path=path)
    return path


class TestInitDb:
    def test_creates_tables(self, db_path):
        conn = sqlite3.connect(str(db_path))
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.close()
        assert "sessions" in tables
        assert "pull_requests" in tables

    def test_idempotent(self, db_path):
        # Calling init_db again should not raise
        database.init_db(db_path=db_path)


class TestRecordSession:
    def test_insert_minimal(self, db_path):
        row_id = database.record_session(
            issue_id="issue-1",
            issue_identifier="LAN-1",
            outcome="completed",
            db_path=db_path,
        )
        assert row_id is not None
        assert row_id > 0

    def test_insert_full(self, db_path):
        row_id = database.record_session(
            issue_id="issue-2",
            issue_identifier="LAN-2",
            project_id="proj-1",
            project_name="My Project",
            session_id="sess-abc",
            branch_name="gabe/lan-2-feature",
            outcome="completed",
            exit_code=0,
            timed_out=False,
            duration_seconds=120.5,
            duration_api_ms=95000.0,
            total_cost_usd=1.2345,
            input_tokens=5000,
            output_tokens=3000,
            cache_read_input_tokens=2000,
            cache_creation_input_tokens=1000,
            num_turns=15,
            started_at="2026-03-22T01:00:00Z",
            finished_at="2026-03-22T01:02:00Z",
            db_path=db_path,
        )
        assert row_id is not None

        sessions = database.query_sessions(issue_id="issue-2", db_path=db_path)
        assert len(sessions) == 1
        s = sessions[0]
        assert s["issue_identifier"] == "LAN-2"
        assert s["project_name"] == "My Project"
        assert s["total_cost_usd"] == pytest.approx(1.2345)
        assert s["num_turns"] == 15
        assert s["timed_out"] == 0

    def test_multiple_sessions(self, db_path):
        for i in range(5):
            database.record_session(
                issue_id=f"issue-{i}",
                issue_identifier=f"LAN-{i}",
                outcome="completed",
                db_path=db_path,
            )
        all_sessions = database.query_sessions(db_path=db_path)
        assert len(all_sessions) == 5


class TestRecordPr:
    def test_insert_pr(self, db_path):
        session_id = database.record_session(
            issue_id="issue-1",
            issue_identifier="LAN-1",
            outcome="completed",
            db_path=db_path,
        )
        pr_id = database.record_pr(
            issue_id="issue-1",
            pr_url="https://example.com/pr/1",
            branch_name="gabe/lan-1-feature",
            session_id=session_id,
            db_path=db_path,
        )
        assert pr_id is not None

        prs = database.query_pull_requests(issue_id="issue-1", db_path=db_path)
        assert len(prs) == 1
        assert prs[0]["pr_url"] == "https://example.com/pr/1"
        assert prs[0]["session_id"] == session_id

    def test_pr_without_session(self, db_path):
        pr_id = database.record_pr(
            issue_id="issue-1",
            pr_url="https://example.com/pr/2",
            db_path=db_path,
        )
        assert pr_id is not None

        prs = database.query_pull_requests(db_path=db_path)
        assert len(prs) == 1


class TestQuerySessions:
    def _seed(self, db_path):
        database.record_session(
            issue_id="issue-1",
            issue_identifier="LAN-1",
            project_id="proj-a",
            project_name="Alpha",
            outcome="completed",
            finished_at="2026-03-20T10:00:00Z",
            db_path=db_path,
        )
        database.record_session(
            issue_id="issue-2",
            issue_identifier="LAN-2",
            project_id="proj-b",
            project_name="Beta",
            outcome="timeout",
            finished_at="2026-03-21T10:00:00Z",
            db_path=db_path,
        )
        database.record_session(
            issue_id="issue-3",
            issue_identifier="LAN-3",
            project_id="proj-a",
            project_name="Alpha",
            outcome="completed",
            finished_at="2026-03-22T10:00:00Z",
            db_path=db_path,
        )

    def test_filter_by_project_name(self, db_path):
        self._seed(db_path)
        results = database.query_sessions(project_name="Alpha", db_path=db_path)
        assert len(results) == 2
        assert all(r["project_name"] == "Alpha" for r in results)

    def test_filter_by_issue_identifier(self, db_path):
        self._seed(db_path)
        results = database.query_sessions(issue_identifier="LAN-2", db_path=db_path)
        assert len(results) == 1
        assert results[0]["outcome"] == "timeout"

    def test_filter_by_since(self, db_path):
        self._seed(db_path)
        results = database.query_sessions(since="2026-03-21T00:00:00Z", db_path=db_path)
        assert len(results) == 2

    def test_filter_combined(self, db_path):
        self._seed(db_path)
        results = database.query_sessions(
            project_name="Alpha",
            since="2026-03-21T00:00:00Z",
            db_path=db_path,
        )
        assert len(results) == 1
        assert results[0]["issue_identifier"] == "LAN-3"

    def test_no_filters(self, db_path):
        self._seed(db_path)
        results = database.query_sessions(db_path=db_path)
        assert len(results) == 3

    def test_invalid_filter_combo(self, db_path):
        # Unsupported combination should raise
        with pytest.raises(ValueError, match="Unsupported filter combination"):
            database.query_sessions(
                project_id="p",
                project_name="n",
                issue_id="i",
                issue_identifier="ident",
                since="2026-01-01",
                db_path=db_path,
            )


class TestSummaryStats:
    def test_summary(self, db_path):
        database.record_session(
            issue_id="issue-1",
            issue_identifier="LAN-1",
            project_name="Alpha",
            outcome="completed",
            total_cost_usd=0.50,
            input_tokens=1000,
            output_tokens=500,
            duration_seconds=60.0,
            num_turns=5,
            db_path=db_path,
        )
        database.record_session(
            issue_id="issue-2",
            issue_identifier="LAN-2",
            project_name="Alpha",
            outcome="completed",
            total_cost_usd=1.00,
            input_tokens=2000,
            output_tokens=1000,
            duration_seconds=120.0,
            num_turns=10,
            db_path=db_path,
        )

        stats = database.get_summary_stats(project_name="Alpha", db_path=db_path)
        assert stats["total_sessions"] == 2
        assert stats["total_cost"] == pytest.approx(1.50)
        assert stats["total_input_tokens"] == 3000
        assert stats["total_output_tokens"] == 1500
        assert stats["avg_duration"] == pytest.approx(90.0)
        assert stats["total_turns"] == 15
        assert stats["unique_issues"] == 2

    def test_empty_summary(self, db_path):
        stats = database.get_summary_stats(db_path=db_path)
        assert stats["total_sessions"] == 0
        assert stats["total_cost"] == 0

    def test_summary_with_since(self, db_path):
        database.record_session(
            issue_id="issue-1",
            issue_identifier="LAN-1",
            outcome="completed",
            total_cost_usd=0.50,
            finished_at="2026-03-20T10:00:00Z",
            db_path=db_path,
        )
        database.record_session(
            issue_id="issue-2",
            issue_identifier="LAN-2",
            outcome="completed",
            total_cost_usd=1.00,
            finished_at="2026-03-22T10:00:00Z",
            db_path=db_path,
        )

        stats = database.get_summary_stats(since="2026-03-21T00:00:00Z", db_path=db_path)
        assert stats["total_sessions"] == 1
        assert stats["total_cost"] == pytest.approx(1.00)
