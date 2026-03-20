"""Configurable logging setup for the daemon."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path.home() / ".claude" / "taskmanager"
DAEMON_LOG = LOG_DIR / "daemon.log"
SESSION_LOG_DIR = LOG_DIR / "logs"

MAX_DAEMON_LOG_BYTES = 5 * 1024 * 1024  # 5 MB
DAEMON_LOG_BACKUP_COUNT = 3


def setup_logging(
    enable_daemon_log: bool = True,
    enable_session_log: bool = True,
    enable_session_output: bool = True,
) -> dict[str, bool]:
    """Configure daemon logging channels.

    Returns a dict of channel states for reference.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    if enable_session_log or enable_session_output:
        SESSION_LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger("tm-daemon")
    root.setLevel(logging.DEBUG)

    # Console handler — always on
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    )
    root.addHandler(console)

    # Daemon file handler
    if enable_daemon_log:
        file_handler = RotatingFileHandler(
            DAEMON_LOG,
            maxBytes=MAX_DAEMON_LOG_BYTES,
            backupCount=DAEMON_LOG_BACKUP_COUNT,
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
        )
        root.addHandler(file_handler)

    return {
        "daemon_log": enable_daemon_log,
        "session_log": enable_session_log,
        "session_output": enable_session_output,
    }


def session_log_path(issue_identifier: str) -> Path:
    """Generate a per-session log file path."""
    from datetime import datetime, timezone

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return SESSION_LOG_DIR / f"{issue_identifier}_{timestamp}.log"
