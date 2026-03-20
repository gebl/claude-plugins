"""Tests for session spawner with streaming output."""

import io
import subprocess
from unittest.mock import MagicMock, patch

from taskmanager.daemon.session import _stream_pipe, run_session


class TestStreamPipe:
    def test_streams_to_console_and_log(self):
        pipe = io.StringIO("line 1\nline 2\nline 3\n")
        log_file = io.StringIO()
        console = io.StringIO()
        collected: list[str] = []

        _stream_pipe(pipe, log_file, console, collected)

        assert collected == ["line 1\n", "line 2\n", "line 3\n"]
        assert log_file.getvalue() == "line 1\nline 2\nline 3\n"
        assert console.getvalue() == "line 1\nline 2\nline 3\n"

    def test_streams_to_console_only_when_no_log(self):
        pipe = io.StringIO("output\n")
        console = io.StringIO()
        collected: list[str] = []

        _stream_pipe(pipe, None, console, collected)

        assert collected == ["output\n"]
        assert console.getvalue() == "output\n"

    def test_handles_empty_pipe(self):
        pipe = io.StringIO("")
        console = io.StringIO()
        collected: list[str] = []

        _stream_pipe(pipe, None, console, collected)

        assert collected == []
        assert console.getvalue() == ""


class TestRunSession:
    def test_captures_output_from_popen(self, tmp_path):
        mock_proc = MagicMock()
        mock_proc.stdout = io.StringIO("hello world\n")
        mock_proc.stderr = io.StringIO("")
        mock_proc.wait.return_value = None
        mock_proc.returncode = 0

        with patch("subprocess.Popen", return_value=mock_proc):
            result = run_session(
                issue_identifier="LAN-99",
                working_dir=tmp_path,
                log_file=None,
                timeout=10,
            )

        assert result.exit_code == 0
        assert result.timed_out is False
        assert "hello world" in result.stdout

    def test_writes_to_log_file(self, tmp_path):
        log_file = tmp_path / "session.log"

        mock_proc = MagicMock()
        mock_proc.stdout = io.StringIO("logged output\n")
        mock_proc.stderr = io.StringIO("")
        mock_proc.wait.return_value = None
        mock_proc.returncode = 0

        with patch("subprocess.Popen", return_value=mock_proc):
            result = run_session(
                issue_identifier="LAN-99",
                working_dir=tmp_path,
                log_file=log_file,
                timeout=10,
            )

        assert result.exit_code == 0
        assert log_file.exists()
        assert "logged output" in log_file.read_text()

    def test_handles_timeout(self, tmp_path):
        mock_proc = MagicMock()
        mock_proc.stdout = io.StringIO("")
        mock_proc.stderr = io.StringIO("")
        # First wait() raises timeout, second wait() (after kill) returns normally
        mock_proc.wait.side_effect = [
            subprocess.TimeoutExpired(cmd="claude", timeout=1),
            None,
        ]
        mock_proc.returncode = -9

        with patch("subprocess.Popen", return_value=mock_proc):
            result = run_session(
                issue_identifier="LAN-99",
                working_dir=tmp_path,
                log_file=None,
                timeout=1,
            )

        assert result.timed_out is True
        mock_proc.kill.assert_called_once()
