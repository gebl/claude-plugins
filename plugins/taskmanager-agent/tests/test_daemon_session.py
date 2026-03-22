"""Tests for session spawner with streaming output."""

import io
import json
import subprocess
from unittest.mock import MagicMock, patch

from taskmanager.daemon.session import _stream_json_pipe, _stream_pipe, run_session


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

    def test_calls_proc_callback(self, tmp_path):
        mock_proc = MagicMock()
        mock_proc.stdout = io.StringIO("")
        mock_proc.stderr = io.StringIO("")
        mock_proc.wait.return_value = None
        mock_proc.returncode = 0

        captured = {}

        def on_proc(p):
            captured["proc"] = p

        with patch("subprocess.Popen", return_value=mock_proc):
            run_session(
                issue_identifier="LAN-99",
                working_dir=tmp_path,
                log_file=None,
                timeout=10,
                proc_callback=on_proc,
            )

        assert captured["proc"] is mock_proc


class TestStreamJsonPipe:
    def _make_result_event(self, **overrides):
        event = {
            "type": "result",
            "total_cost_usd": 0.1234,
            "duration_ms": 5000,
            "num_turns": 3,
            "session_id": "sess-abc123",
            "usage": {
                "input_tokens": 1000,
                "output_tokens": 500,
                "cache_read_input_tokens": 800,
                "cache_creation_input_tokens": 200,
            },
        }
        event.update(overrides)
        return json.dumps(event) + "\n"

    def test_captures_token_fields_from_result_event(self):
        line = self._make_result_event()
        pipe = io.StringIO(line)
        console = io.StringIO()
        collected: list[str] = []
        result_data: dict = {}

        _stream_json_pipe(pipe, None, console, collected, result_data=result_data)

        assert result_data["input_tokens"] == 1000
        assert result_data["output_tokens"] == 500
        assert result_data["cache_read_input_tokens"] == 800
        assert result_data["cache_creation_input_tokens"] == 200
        assert result_data["num_turns"] == 3
        assert result_data["session_id"] == "sess-abc123"
        assert result_data["total_cost_usd"] == 0.1234
        assert result_data["duration_api_ms"] == 5000

    def test_skips_missing_usage_fields(self):
        event = {"type": "result", "total_cost_usd": 0.05}
        pipe = io.StringIO(json.dumps(event) + "\n")
        console = io.StringIO()
        collected: list[str] = []
        result_data: dict = {}

        _stream_json_pipe(pipe, None, console, collected, result_data=result_data)

        assert result_data["total_cost_usd"] == 0.05
        assert "input_tokens" not in result_data
        assert "output_tokens" not in result_data
        assert "num_turns" not in result_data

    def test_result_data_none_skips_capture(self):
        line = self._make_result_event()
        pipe = io.StringIO(line)
        console = io.StringIO()
        collected: list[str] = []

        # Should not raise even with result_data=None
        _stream_json_pipe(pipe, None, console, collected, result_data=None)
