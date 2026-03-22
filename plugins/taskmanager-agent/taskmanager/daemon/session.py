"""Claude Code session spawner for the daemon."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("tm-daemon.session")

DEFAULT_TIMEOUT = 9000  # 2.5 hours

GIT_DAEMON_EMAIL = "claude-daemon@local"
GIT_DAEMON_NAME = "Claude Daemon"


@dataclass
class SessionResult:
    exit_code: int
    timed_out: bool
    duration_seconds: float
    stdout: str
    stderr: str
    total_cost_usd: float | None = None
    duration_api_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_input_tokens: int | None = None
    cache_creation_input_tokens: int | None = None
    num_turns: int | None = None
    session_id: str | None = None


def _format_stream_event(raw_line: str) -> str | None:
    """Parse a stream-json line and return a human-readable string, or None to skip."""
    try:
        event = json.loads(raw_line)
    except json.JSONDecodeError:
        return raw_line

    event_type = event.get("type", "")

    if event_type == "assistant":
        msg = event.get("message", {})
        parts = []
        for block in msg.get("content", []):
            if block.get("type") == "text" and block.get("text"):
                parts.append(block["text"])
        if parts:
            return "".join(parts)
        return None

    if event_type == "tool_use":
        tool = event.get("tool", {})
        name = tool.get("name", event.get("name", "unknown"))
        return f"[tool_use] {name}\n"

    if event_type == "tool_result":
        content = event.get("content", "")
        if isinstance(content, str) and content:
            preview = content[:200]
            if len(content) > 200:
                preview += "..."
            return f"[tool_result] {preview}\n"
        return "[tool_result]\n"

    if event_type == "result":
        cost = event.get("total_cost_usd")
        duration = event.get("duration_ms")
        parts = ["[session complete]"]
        if duration:
            parts.append(f" duration={duration / 1000:.1f}s")
        if cost:
            parts.append(f" cost=${cost:.4f}")
        parts.append("\n")
        return "".join(parts)

    # Skip system, rate_limit_event, etc.
    return None


def _stream_json_pipe(
    pipe: object,
    log_file: object | None,
    console: object,
    collected: list[str],
    tracker: object | None = None,
    result_data: dict | None = None,
) -> None:
    """Read stream-json lines, format them, and write to log/console."""
    from taskmanager.daemon.progress import ProgressTracker

    while True:
        line = pipe.readline()  # type: ignore[attr-defined]
        if not line:
            break
        collected.append(line)

        # Always write raw JSON to log file
        if log_file:
            log_file.write(line)  # type: ignore[union-attr]
            log_file.flush()  # type: ignore[union-attr]

        # Write formatted output to console
        formatted = _format_stream_event(line.rstrip("\n"))
        if formatted:
            console.write(formatted)  # type: ignore[union-attr]
            console.flush()  # type: ignore[union-attr]

        # Capture result event data for session metrics
        if result_data is not None:
            try:
                event = json.loads(line.rstrip("\n"))
                if event.get("type") == "result":
                    if event.get("total_cost_usd") is not None:
                        result_data["total_cost_usd"] = event["total_cost_usd"]
                    if event.get("duration_ms") is not None:
                        result_data["duration_api_ms"] = event["duration_ms"]
                    if event.get("num_turns") is not None:
                        result_data["num_turns"] = event["num_turns"]
                    if event.get("session_id") is not None:
                        result_data["session_id"] = event["session_id"]
                    usage = event.get("usage", {})
                    if usage.get("input_tokens") is not None:
                        result_data["input_tokens"] = usage["input_tokens"]
                    if usage.get("output_tokens") is not None:
                        result_data["output_tokens"] = usage["output_tokens"]
                    if usage.get("cache_read_input_tokens") is not None:
                        result_data["cache_read_input_tokens"] = usage[
                            "cache_read_input_tokens"
                        ]
                    if usage.get("cache_creation_input_tokens") is not None:
                        result_data["cache_creation_input_tokens"] = usage[
                            "cache_creation_input_tokens"
                        ]
            except json.JSONDecodeError:
                pass

        # Feed to progress tracker
        if isinstance(tracker, ProgressTracker):
            tracker.on_event(line.rstrip("\n"))


def _stream_pipe(
    pipe: object,
    log_file: object | None,
    console: object,
    collected: list[str],
) -> None:
    """Read lines from a pipe, writing to both log file and console."""
    while True:
        line = pipe.readline()  # type: ignore[attr-defined]
        if not line:
            break
        collected.append(line)
        if log_file:
            log_file.write(line)  # type: ignore[union-attr]
            log_file.flush()  # type: ignore[union-attr]
        console.write(line)  # type: ignore[union-attr]
        console.flush()  # type: ignore[union-attr]


def run_session(
    issue_identifier: str,
    working_dir: Path,
    log_file: Path | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    issue_id: str | None = None,
    proc_callback: Callable[[subprocess.Popen], None] | None = None,
    command: str | None = None,
) -> SessionResult:
    """Spawn a Claude Code session for a single issue.

    Changes to working_dir, sets git identity env vars, and runs
    claude -p with the given command (defaults to /tm-assign). Uses
    --output-format stream-json to stream parsed output to the terminal
    in real time.

    If issue_id is provided, posts periodic progress comments to the issue.
    """
    from taskmanager.daemon.progress import ProgressTracker

    original_dir = os.getcwd()

    env = os.environ.copy()
    env["GIT_AUTHOR_EMAIL"] = GIT_DAEMON_EMAIL
    env["GIT_COMMITTER_EMAIL"] = GIT_DAEMON_EMAIL
    env["GIT_AUTHOR_NAME"] = GIT_DAEMON_NAME
    env["GIT_COMMITTER_NAME"] = GIT_DAEMON_NAME

    prompt = command or f"/tm-assign {issue_identifier}"
    cmd = [
        "claude",
        "-p",
        prompt,
        "--dangerously-skip-permissions",
        "--output-format",
        "stream-json",
        "--verbose",
    ]

    log.info(
        "Spawning session for %s in %s (timeout=%ds)",
        issue_identifier,
        working_dir,
        timeout,
    )

    tracker = None
    if issue_id:
        tracker = ProgressTracker(issue_id, issue_identifier)

    start = time.monotonic()
    timed_out = False
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    exit_code = 1
    result_data: dict = {}

    stdout_log = None
    stderr_log = None

    try:
        os.chdir(working_dir)

        if log_file:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            stdout_log = open(log_file, "w")
            stderr_log = open(log_file.with_suffix(".stderr"), "w")

        proc = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if proc_callback:
            proc_callback(proc)

        # Stream stdout (stream-json) with formatting, stderr raw
        stdout_thread = threading.Thread(
            target=_stream_json_pipe,
            args=(
                proc.stdout,
                stdout_log,
                sys.stdout,
                stdout_lines,
                tracker,
                result_data,
            ),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=_stream_pipe,
            args=(proc.stderr, stderr_log, sys.stderr, stderr_lines),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()

        # Wait for process with timeout
        try:
            proc.wait(timeout=timeout)
            exit_code = proc.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            log.warning("Session timed out after %ds for %s", timeout, issue_identifier)
            proc.kill()
            proc.wait()

        # Wait for threads to finish reading remaining output
        stdout_thread.join(timeout=5)
        stderr_thread.join(timeout=5)

    finally:
        if stdout_log:
            stdout_log.close()
        if stderr_log:
            stderr_log.close()
        os.chdir(original_dir)

    duration = time.monotonic() - start

    log.info(
        "Session %s finished: exit=%d timed_out=%s duration=%.1fs",
        issue_identifier,
        exit_code,
        timed_out,
        duration,
    )

    return SessionResult(
        exit_code=exit_code,
        timed_out=timed_out,
        duration_seconds=duration,
        stdout="".join(stdout_lines),
        stderr="".join(stderr_lines),
        total_cost_usd=result_data.get("total_cost_usd"),
        duration_api_ms=result_data.get("duration_api_ms"),
        input_tokens=result_data.get("input_tokens"),
        output_tokens=result_data.get("output_tokens"),
        cache_read_input_tokens=result_data.get("cache_read_input_tokens"),
        cache_creation_input_tokens=result_data.get("cache_creation_input_tokens"),
        num_turns=result_data.get("num_turns"),
        session_id=result_data.get("session_id"),
    )
