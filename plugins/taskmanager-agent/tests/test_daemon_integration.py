"""Integration tests for the daemon runner."""

import os
import signal
from unittest.mock import patch

import pytest

from taskmanager.daemon.runner import DaemonRunner
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
