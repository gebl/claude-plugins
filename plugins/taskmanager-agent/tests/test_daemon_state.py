"""Tests for daemon state persistence."""

from taskmanager.daemon.state import DaemonState, HISTORY_CAP


class TestDaemonState:
    def test_fresh_state_defaults(self):
        s = DaemonState()
        assert s.pid is None
        assert s.poll_count == 0
        assert s.quarantine == []
        assert s.history == []
        assert s.active_session is None

    def test_save_and_load(self, tmp_path, monkeypatch):
        state_file = tmp_path / "daemon-state.yaml"
        monkeypatch.setattr("taskmanager.daemon.state.STATE_FILE", state_file)
        monkeypatch.setattr("taskmanager.daemon.state.STATE_DIR", tmp_path)

        s = DaemonState(pid=12345, poll_count=10)
        s.add_to_quarantine("issue-1", "timed out")
        s.add_to_history("issue-2", "completed", 120.5)
        s.save()

        loaded = DaemonState.load()
        assert loaded.pid == 12345
        assert loaded.poll_count == 10
        assert len(loaded.quarantine) == 1
        assert loaded.quarantine[0].issue_id == "issue-1"
        assert loaded.quarantine[0].reason == "timed out"
        assert len(loaded.history) == 1
        assert loaded.history[0].issue_id == "issue-2"
        assert loaded.history[0].outcome == "completed"
        assert loaded.history[0].duration_seconds == 120.5

    def test_load_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "taskmanager.daemon.state.STATE_FILE", tmp_path / "missing.yaml"
        )
        s = DaemonState.load()
        assert s.pid is None
        assert s.poll_count == 0

    def test_quarantine_operations(self):
        s = DaemonState()
        assert not s.is_quarantined("issue-1")

        s.add_to_quarantine("issue-1", "failed")
        assert s.is_quarantined("issue-1")
        assert not s.is_quarantined("issue-2")

        # Duplicate add is a no-op
        s.add_to_quarantine("issue-1", "failed again")
        assert len(s.quarantine) == 1

    def test_history_cap(self):
        s = DaemonState()
        for i in range(20):
            s.add_to_history(f"issue-{i}", "completed", 60.0)

        assert len(s.history) == HISTORY_CAP
        # Most recent entries are kept
        assert s.history[0].issue_id == f"issue-{20 - HISTORY_CAP}"
        assert s.history[-1].issue_id == "issue-19"

    def test_active_session(self):
        s = DaemonState()
        assert s.active_session is None

        s.set_active_session("issue-1", 99999)
        assert s.active_session is not None
        assert s.active_session.issue_id == "issue-1"
        assert s.active_session.pid == 99999

        s.clear_active_session()
        assert s.active_session is None
