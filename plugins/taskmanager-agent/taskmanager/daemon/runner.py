"""Main daemon loop — orchestrates polling, session spawning, and state management."""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from taskmanager import config
from taskmanager.daemon import logging_config
from taskmanager.daemon import poller
from taskmanager.daemon import selector
from taskmanager.daemon import session
from taskmanager.daemon import state

log = logging.getLogger("tm-daemon.runner")


class DaemonRunner:
    """Orchestrates the daemon lifecycle."""

    def __init__(
        self,
        poll_interval: float = poller.INTERVAL_ACTIVE,
        timeout: int = session.DEFAULT_TIMEOUT,
        log_channels: dict[str, bool] | None = None,
    ) -> None:
        self._timeout = timeout
        self._log_channels = log_channels or {
            "enable_daemon_log": True,
            "enable_session_log": True,
            "enable_session_output": True,
        }
        self._poller = poller.AdaptivePoller(initial_interval=poll_interval)
        self._state = state.DaemonState()
        self._draining = False
        self._force_stop = False
        self._active_proc: subprocess.Popen | None = None

    def run(self) -> None:
        """Start the daemon main loop."""
        logging_config.setup_logging(**self._log_channels)

        self._state = state.DaemonState.load()
        self._check_pid_lock()

        self._state.pid = os.getpid()
        self._state.started_at = _now_iso()
        self._state.save()

        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        log.info("Daemon started (pid=%d)", os.getpid())

        try:
            self._main_loop()
        finally:
            self._state.pid = None
            self._state.clear_active_session()
            self._state.save()
            log.info("Daemon stopped")

    def _main_loop(self) -> None:
        while not self._draining and not self._force_stop:
            self._state.poll_count += 1
            self._state.last_poll = _now_iso()

            quarantined_ids = {q.issue_id for q in self._state.quarantine}
            selected = selector.select_next_issue(quarantined_ids)

            if selected:
                log.info(
                    "Selected: %s — %s (status=%s)",
                    selected.identifier,
                    selected.title,
                    selected.status,
                )
                self._state.last_work_found = _now_iso()
                self._poller.work_found()
                self._process_issue(selected)
                # Skip sleep — immediately re-poll for pending work
                self._state.current_interval_seconds = self._poller.current_interval
                self._state.save()
                continue

            log.debug("No work found (tier %d)", self._poller.tier_index)
            self._poller.no_work_found()

            self._state.current_interval_seconds = self._poller.current_interval
            self._state.save()

            if self._draining or self._force_stop:
                break

            interval = self._poller.current_interval
            log.debug("Sleeping %.0fs before next poll", interval)
            # Sleep in small increments so we can respond to signals
            end_time = time.monotonic() + interval
            while time.monotonic() < end_time:
                if self._draining or self._force_stop:
                    break
                time.sleep(min(1.0, end_time - time.monotonic()))

    def _process_issue(self, selected: selector.SelectedIssue) -> None:
        """Spawn a Claude session and handle the result."""
        cfg = config.load_config()
        projects_by_id = {p["id"]: p for p in cfg.get("projects", [])}
        project = projects_by_id.get(selected.project_id, {})

        working_dir = self._resolve_working_dir(selected, project)
        if not working_dir:
            log.error("Cannot determine working directory for %s", selected.identifier)
            self._quarantine_issue(selected, "Cannot determine working directory")
            return

        # Record pre-session state
        pre_status = selected.status

        # Set up session log
        log_file = None
        if self._log_channels.get("enable_session_log") or self._log_channels.get(
            "enable_session_output"
        ):
            log_file = logging_config.session_log_path(selected.identifier)

        self._state.set_active_session(selected.issue_id, os.getpid())
        self._state.save()

        result = session.run_session(
            issue_identifier=selected.identifier,
            working_dir=working_dir,
            log_file=log_file,
            timeout=self._timeout,
        )

        self._state.clear_active_session()

        if result.timed_out:
            self._quarantine_issue(
                selected, f"Session timed out after {self._timeout}s"
            )
            self._state.add_to_history(
                selected.issue_id, "timeout", result.duration_seconds
            )
            return

        # Check post-session state
        post_issue = selector._run_dict_script("tm_get_issue.py", selected.identifier)
        post_status = ""
        if post_issue:
            post_status = post_issue.get("status", {}).get("name", "")

        if post_status == pre_status:
            log.warning(
                "Issue %s state unchanged after session (still %s)",
                selected.identifier,
                pre_status,
            )
            self._quarantine_issue(
                selected, f"State unchanged after session (remained {pre_status})"
            )
            self._state.add_to_history(
                selected.issue_id, "unchanged", result.duration_seconds
            )
        else:
            log.info(
                "Issue %s transitioned: %s → %s",
                selected.identifier,
                pre_status,
                post_status,
            )
            self._state.add_to_history(
                selected.issue_id, "completed", result.duration_seconds
            )

    def _resolve_working_dir(
        self, selected: selector.SelectedIssue, project: dict
    ) -> Path | None:
        """Determine the working directory for a session."""
        local_path = project.get("local_path")
        repo = project.get("repo")

        if local_path:
            path = Path(local_path)
            if path.exists():
                return path

            # Auto-clone if repo URL is available
            if repo:
                log.info("Cloning %s to %s", repo, path)
                try:
                    subprocess.run(
                        ["git", "clone", repo, str(path)],
                        check=True,
                        capture_output=True,
                        text=True,
                        timeout=300,
                    )
                    return path
                except (
                    subprocess.CalledProcessError,
                    subprocess.TimeoutExpired,
                ) as exc:
                    log.error("Clone failed for %s: %s", repo, exc)
                    return None

            return None

        # Non-code project — create session directory
        session_dir = (
            Path.home()
            / "Projects"
            / "sessions"
            / selected.project_name.lower().replace(" ", "-")
        )
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir

    def _quarantine_issue(self, selected: selector.SelectedIssue, reason: str) -> None:
        """Add issue to quarantine and create error sub-issue in Linear."""
        log.warning("Quarantining %s: %s", selected.identifier, reason)
        self._state.add_to_quarantine(selected.issue_id, reason)

        # Create error sub-issue
        cfg = config.load_config()
        team_id = cfg.get("team", {}).get("id", "")
        operator_id = cfg.get("operator", {}).get("id", "")

        if team_id:
            scripts_dir = selector._find_scripts_dir()
            python = selector._find_venv_python()

            # Create error sub-issue
            try:
                subprocess.run(
                    [
                        python,
                        str(scripts_dir / "tm_save_issue.py"),
                        "--title",
                        f"[Daemon Error] {selected.identifier}: {reason}",
                        "--team",
                        team_id,
                        "--parent-id",
                        selected.issue_id,
                        "--state",
                        "Todo",
                        "--label",
                        "Review",
                        *(["--assignee", operator_id] if operator_id else []),
                        "--description",
                        f"The daemon encountered an error processing {selected.identifier}.\n\nReason: {reason}\n\nThis issue has been quarantined. To retry, remove it from the quarantine list in ~/.claude/taskmanager/daemon-state.yaml.",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                log.error(
                    "Failed to create error sub-issue for %s", selected.identifier
                )

            # Mark parent as blocked
            try:
                subprocess.run(
                    [
                        python,
                        str(scripts_dir / "tm_save_issue.py"),
                        "--id",
                        selected.identifier,
                        "--state",
                        "Blocked",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                log.error("Failed to block %s", selected.identifier)

    def _check_pid_lock(self) -> None:
        """Refuse to start if another daemon instance is running."""
        if self._state.pid is None:
            return

        try:
            os.kill(self._state.pid, 0)
            # Process exists
            log.error(
                "Another daemon is already running (pid=%d). Exiting.", self._state.pid
            )
            sys.exit(1)
        except ProcessLookupError:
            # Process is dead — stale PID
            log.info("Clearing stale PID %d from previous run", self._state.pid)
            self._state.pid = None
        except PermissionError:
            # Process exists but we can't signal it
            log.error(
                "Another daemon may be running (pid=%d, permission denied). Exiting.",
                self._state.pid,
            )
            sys.exit(1)

    def _handle_signal(self, signum: int, _frame: object) -> None:
        """Two-stage shutdown: first drain, second force-kill."""
        if self._draining:
            log.info("Second signal received — force stopping")
            self._force_stop = True
        else:
            log.info(
                "Signal %d received — draining (finish current session, then exit)",
                signum,
            )
            self._draining = True


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
