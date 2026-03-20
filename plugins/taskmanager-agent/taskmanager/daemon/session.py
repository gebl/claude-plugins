"""Claude Code session spawner for the daemon."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("tm-daemon.session")

DEFAULT_TIMEOUT = 1800  # 30 minutes

GIT_DAEMON_EMAIL = "claude-daemon@local"
GIT_DAEMON_NAME = "Claude Daemon"


@dataclass
class SessionResult:
    exit_code: int
    timed_out: bool
    duration_seconds: float
    stdout: str
    stderr: str


def _stream_pipe(
    pipe: object,
    log_file: object | None,
    console: object,
    collected: list[str],
) -> None:
    """Read lines from a pipe, writing to both log file and console."""
    for line in pipe:  # type: ignore[attr-defined]
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
) -> SessionResult:
    """Spawn a Claude Code session for a single issue.

    Changes to working_dir, sets git identity env vars, and runs
    claude -p with the /tm-assign skill. Streams output to both
    the terminal and log file in real time.
    """
    original_dir = os.getcwd()

    env = os.environ.copy()
    env["GIT_AUTHOR_EMAIL"] = GIT_DAEMON_EMAIL
    env["GIT_COMMITTER_EMAIL"] = GIT_DAEMON_EMAIL
    env["GIT_AUTHOR_NAME"] = GIT_DAEMON_NAME
    env["GIT_COMMITTER_NAME"] = GIT_DAEMON_NAME

    prompt = f"/tm-assign {issue_identifier}"
    cmd = [
        "claude",
        "-p",
        prompt,
        "--dangerously-skip-permissions",
    ]

    log.info(
        "Spawning session for %s in %s (timeout=%ds)",
        issue_identifier,
        working_dir,
        timeout,
    )

    start = time.monotonic()
    timed_out = False
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    exit_code = 1

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

        # Stream stdout and stderr in separate threads
        stdout_thread = threading.Thread(
            target=_stream_pipe,
            args=(proc.stdout, stdout_log, sys.stdout, stdout_lines),
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
    )
