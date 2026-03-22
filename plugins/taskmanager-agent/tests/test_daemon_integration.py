"""Integration tests for the daemon runner."""

import os
import signal
from unittest.mock import MagicMock, patch

import pytest

from taskmanager.daemon.runner import DaemonRunner
from taskmanager.daemon.session import SessionResult
from taskmanager.daemon.state import DaemonState


class TestPidLocking:
    def test_refuses_if_pid_alive(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "taskmanager.daemon.state.STATE_FILE", tmp_path / "state.yaml"
        )
        monkeypatch.setattr("taskmanager.daemon.state.STATE_DIR", tmp_path)

        # Write state with current process PID (guaranteed alive)
        s = DaemonState(pid=os.getpid())
        s.save()

        runner = DaemonRunner()
        with pytest.raises(SystemExit):
            runner.run()

    def test_clears_stale_pid(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "taskmanager.daemon.state.STATE_FILE", tmp_path / "state.yaml"
        )
        monkeypatch.setattr("taskmanager.daemon.state.STATE_DIR", tmp_path)

        # Write state with a PID that doesn't exist
        s = DaemonState(pid=99999999)
        s.save()

        runner = DaemonRunner()
        runner._state = DaemonState.load()
        runner._check_pid_lock()
        # Should not raise — stale PID cleared
        assert runner._state.pid is None


class TestSignalHandling:
    def test_first_signal_sets_draining(self):
        runner = DaemonRunner()
        assert not runner._draining
        assert not runner._force_stop

        runner._handle_signal(signal.SIGINT, None)
        assert runner._draining
        assert not runner._force_stop

    def test_second_signal_sets_force_stop(self):
        runner = DaemonRunner()
        runner._handle_signal(signal.SIGINT, None)
        runner._handle_signal(signal.SIGINT, None)
        assert runner._draining
        assert runner._force_stop


class TestWorkingDirResolution:
    def test_existing_local_path(self, tmp_path):
        runner = DaemonRunner()
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()

        from taskmanager.daemon.selector import SelectedIssue

        selected = SelectedIssue(
            issue_id="id",
            identifier="LAN-1",
            title="Test",
            status="Todo",
            priority=3,
            project_id="p1",
            project_name="My Project",
        )
        project = {"local_path": str(project_dir), "repo": "git@example.com:repo.git"}

        result = runner._resolve_working_dir(selected, project)
        assert result == project_dir

    def test_non_code_project_creates_session_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        # Patch Path.home() to return tmp_path
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        runner = DaemonRunner()
        from taskmanager.daemon.selector import SelectedIssue

        selected = SelectedIssue(
            issue_id="id",
            identifier="LAN-1",
            title="Test",
            status="Todo",
            priority=3,
            project_id="p1",
            project_name="My Project",
        )
        project = {}  # No local_path, no repo

        result = runner._resolve_working_dir(selected, project)
        expected = tmp_path / "Projects" / "sessions" / "my-project"
        assert result == expected
        assert result.exists()

    def test_missing_local_path_no_repo(self):
        runner = DaemonRunner()
        from taskmanager.daemon.selector import SelectedIssue

        selected = SelectedIssue(
            issue_id="id",
            identifier="LAN-1",
            title="Test",
            status="Todo",
            priority=3,
            project_id="p1",
            project_name="My Project",
        )
        project = {"local_path": "/nonexistent/path/that/doesnt/exist"}

        result = runner._resolve_working_dir(selected, project)
        assert result is None


class TestQuarantine:
    def test_quarantine_creates_sub_issue(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "taskmanager.daemon.state.STATE_FILE", tmp_path / "state.yaml"
        )
        monkeypatch.setattr("taskmanager.daemon.state.STATE_DIR", tmp_path)

        runner = DaemonRunner()
        runner._state = DaemonState()

        from taskmanager.daemon.selector import SelectedIssue

        selected = SelectedIssue(
            issue_id="id-123",
            identifier="LAN-99",
            title="Test Issue",
            status="In Progress",
            priority=3,
            project_id="p1",
            project_name="My Project",
        )

        mock_config = {
            "team": {"id": "team-1"},
            "operator": {"id": "op-1"},
        }

        with (
            patch(
                "taskmanager.daemon.runner.config.load_config", return_value=mock_config
            ),
            patch(
                "taskmanager.daemon.runner.selector._find_scripts_dir",
                return_value=tmp_path,
            ),
            patch(
                "taskmanager.daemon.runner.selector._find_venv_python",
                return_value="python",
            ),
            patch("subprocess.run"),
        ):
            runner._quarantine_issue(selected, "timed out")

        assert runner._state.is_quarantined("id-123")

    def test_quarantine_assigns_to_human(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "taskmanager.daemon.state.STATE_FILE", tmp_path / "state.yaml"
        )
        monkeypatch.setattr("taskmanager.daemon.state.STATE_DIR", tmp_path)

        runner = DaemonRunner()
        runner._state = DaemonState()

        from taskmanager.daemon.selector import SelectedIssue

        selected = SelectedIssue(
            issue_id="id-123",
            identifier="LAN-99",
            title="Test Issue",
            status="In Progress",
            priority=3,
            project_id="p1",
            project_name="My Project",
        )

        mock_config = {
            "team": {"id": "team-1"},
            "operator": {"id": "op-1"},
            "issue_defaults": {"assignee_id": "human-1"},
        }

        calls = []

        def capture_run(*args, **kwargs):
            calls.append(args[0] if args else kwargs.get("args", []))
            return MagicMock(returncode=0)

        with (
            patch(
                "taskmanager.daemon.runner.config.load_config", return_value=mock_config
            ),
            patch(
                "taskmanager.daemon.runner.selector._find_scripts_dir",
                return_value=tmp_path,
            ),
            patch(
                "taskmanager.daemon.runner.selector._find_venv_python",
                return_value="python",
            ),
            patch("subprocess.run", side_effect=capture_run),
        ):
            runner._quarantine_issue(selected, "timed out")

        # The first subprocess.run call creates the error sub-issue
        create_call = calls[0]
        assignee_idx = create_call.index("--assignee") + 1
        assert create_call[assignee_idx] == "human-1"


class TestForceStop:
    def test_second_signal_kills_active_proc(self):
        runner = DaemonRunner()
        mock_proc = MagicMock()
        runner._active_proc = mock_proc

        runner._handle_signal(signal.SIGINT, None)  # first — drain
        runner._handle_signal(signal.SIGINT, None)  # second — force stop

        mock_proc.kill.assert_called_once()




class TestConversationIssueDetection:
    """Tests for conversation issue routing in the runner."""

    def _make_runner(self):
        return DaemonRunner()

    def _make_selected(self, project_id=None, project_name=None):
        from taskmanager.daemon.selector import SelectedIssue

        return SelectedIssue(
            issue_id="id-conv",
            identifier="LAN-50",
            title="Conversation Test",
            status="In Progress",
            priority=3,
            project_id=project_id or "",
            project_name=project_name or "",
        )

    def test_projectless_issue_is_conversation(self):
        runner = self._make_runner()
        selected = self._make_selected(project_id="", project_name="")
        assert runner._is_conversation_issue(selected, {"p1"}) is True

    def test_active_project_issue_is_not_conversation(self):
        runner = self._make_runner()
        selected = self._make_selected(project_id="p1", project_name="Project")
        assert runner._is_conversation_issue(selected, {"p1"}) is False

    def test_inactive_project_issue_is_conversation(self):
        runner = self._make_runner()
        selected = self._make_selected(project_id="p2", project_name="Other")
        assert runner._is_conversation_issue(selected, {"p1"}) is True

    def test_working_dir_uses_identifier_for_projectless(self, tmp_path, monkeypatch):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        runner = self._make_runner()
        selected = self._make_selected(project_id="", project_name="")
        project = {}

        result = runner._resolve_working_dir(selected, project)
        expected = tmp_path / "Projects" / "sessions" / "lan-50"
        assert result == expected
        assert result.exists()


class TestSessionSummary:
    def _make_selected(self):
        from taskmanager.daemon.selector import SelectedIssue

        return SelectedIssue(
            issue_id="id-123",
            identifier="LAN-99",
            title="Test",
            status="In Progress",
            priority=3,
            project_id="p1",
            project_name="My Project",
        )

    def test_summary_includes_token_counts(self, tmp_path):
        runner = DaemonRunner()
        selected = self._make_selected()
        result = SessionResult(
            exit_code=0,
            timed_out=False,
            duration_seconds=120.0,
            stdout="",
            stderr="",
            total_cost_usd=0.1234,
            duration_api_ms=5000,
            input_tokens=1000,
            output_tokens=500,
            cache_read_input_tokens=800,
            cache_creation_input_tokens=200,
            num_turns=3,
            session_id="sess-abc",
        )

        with (
            patch(
                "taskmanager.daemon.runner.selector._find_scripts_dir",
                return_value=tmp_path,
            ),
            patch(
                "taskmanager.daemon.runner.selector._find_venv_python",
                return_value="python",
            ),
            patch("subprocess.run") as mock_run,
        ):
            runner._post_session_summary(selected, result, "completed")

        body = mock_run.call_args[0][0][mock_run.call_args[0][0].index("--body") + 1]
        assert "Tokens: 1000 in / 500 out" in body
        assert "cache: 800 read, 200 created" in body
        assert "Turns: 3" in body
        assert "Cost: $0.1234" in body

    def test_summary_without_tokens(self, tmp_path):
        runner = DaemonRunner()
        selected = self._make_selected()
        result = SessionResult(
            exit_code=0,
            timed_out=False,
            duration_seconds=60.0,
            stdout="",
            stderr="",
            total_cost_usd=0.05,
        )

        with (
            patch(
                "taskmanager.daemon.runner.selector._find_scripts_dir",
                return_value=tmp_path,
            ),
            patch(
                "taskmanager.daemon.runner.selector._find_venv_python",
                return_value="python",
            ),
            patch("subprocess.run") as mock_run,
        ):
            runner._post_session_summary(selected, result, "completed")

        body = mock_run.call_args[0][0][mock_run.call_args[0][0].index("--body") + 1]
        assert "Tokens:" not in body
        assert "Turns:" not in body
        assert "Cost: $0.0500" in body
