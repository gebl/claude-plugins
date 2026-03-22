"""Main daemon loop — orchestrates polling, session spawning, and state management."""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from taskmanager import config
from taskmanager.daemon import database
from taskmanager.daemon import logging_config
from taskmanager.daemon import poller
from taskmanager.daemon import selector
from taskmanager.daemon import session
from taskmanager.daemon import state
from taskmanager.daemon import validator

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

        database.init_db()

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
            quarantine_note = (
                f" ({len(quarantined_ids)} quarantined)" if quarantined_ids else ""
            )
            log.info(
                "Poll #%d — scanning for work%s",
                self._state.poll_count,
                quarantine_note,
            )
            selected = selector.select_next_issue(
                quarantined_ids, seen_comments=self._state.seen_comments
            )

            if selected:
                log.info(
                    "Selected: %s — %s (priority=%s, status=%s)",
                    selected.identifier,
                    selected.title,
                    selected.priority or "none",
                    selected.status,
                )
                self._state.last_work_found = _now_iso()
                self._poller.work_found()
                self._process_issue(selected)
                # Skip sleep — immediately re-poll for pending work
                self._state.current_interval_seconds = self._poller.current_interval
                self._state.save()
                continue

            self._poller.no_work_found()

            self._state.current_interval_seconds = self._poller.current_interval
            self._state.save()

            if self._draining or self._force_stop:
                break

            interval = self._poller.current_interval
            log.info(
                "No work found — sleeping %.0fs (tier %d)",
                interval,
                self._poller.tier_index,
            )
            # Sleep in small increments so we can respond to signals
            end_time = time.monotonic() + interval
            while time.monotonic() < end_time:
                if self._draining or self._force_stop:
                    break
                time.sleep(min(1.0, end_time - time.monotonic()))

    def _is_conversation_issue(
        self, selected: selector.SelectedIssue, active_project_ids: set[str]
    ) -> bool:
        """Check if an issue is a conversation-mode issue (no active project)."""
        return not selected.project_id or selected.project_id not in active_project_ids

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

        session_started_at = _now_iso()
        self._state.set_active_session(selected.issue_id, os.getpid())
        self._state.save()

        def _on_proc(proc: subprocess.Popen) -> None:
            self._active_proc = proc

        # Determine the command based on issue type
        active_project_ids = set(projects_by_id.keys())
        session_command = None
        if self._is_conversation_issue(selected, active_project_ids):
            session_command = f"/tm-converse {selected.identifier}"

        result = session.run_session(
            issue_identifier=selected.identifier,
            working_dir=working_dir,
            log_file=log_file,
            timeout=self._timeout,
            issue_id=selected.issue_id,
            proc_callback=_on_proc,
            command=session_command,
        )

        self._active_proc = None
        self._state.clear_active_session()
        self._state.mark_comments_seen(selected.issue_id, _now_iso())

        if result.timed_out:
            self._quarantine_issue(
                selected, f"Session timed out after {self._timeout}s"
            )
            self._state.add_to_history(
                selected.issue_id,
                "timeout",
                result.duration_seconds,
                total_cost_usd=result.total_cost_usd,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                num_turns=result.num_turns,
            )
            self._record_session_to_db(selected, result, "timeout", session_started_at)
            self._post_session_summary(selected, result, "timeout")
            return

        # Check post-session state
        post_issue = selector._run_dict_script("tm_get_issue.py", selected.identifier)
        post_status = ""
        if post_issue:
            post_status = post_issue.get("status", {}).get("name", "")

        is_conversation = self._is_conversation_issue(selected, active_project_ids)

        if (
            post_status == pre_status
            and pre_status != "In Review"
            and not is_conversation
        ):
            log.warning(
                "Issue %s state unchanged after session (still %s)",
                selected.identifier,
                pre_status,
            )
            self._quarantine_issue(
                selected, f"State unchanged after session (remained {pre_status})"
            )
            self._state.add_to_history(
                selected.issue_id,
                "unchanged",
                result.duration_seconds,
                total_cost_usd=result.total_cost_usd,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                num_turns=result.num_turns,
            )
            self._record_session_to_db(selected, result, "unchanged", session_started_at)
            self._post_session_summary(selected, result, "unchanged")
        elif not _is_valid_transition(pre_status, post_status):
            log.warning(
                "Issue %s made invalid transition: %s → %s",
                selected.identifier,
                pre_status,
                post_status,
            )
            self._quarantine_issue(
                selected,
                f"Invalid workflow transition: {pre_status} → {post_status}",
            )
            self._state.add_to_history(
                selected.issue_id,
                "invalid_transition",
                result.duration_seconds,
                total_cost_usd=result.total_cost_usd,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                num_turns=result.num_turns,
            )
            self._record_session_to_db(selected, result, "invalid_transition", session_started_at)
            self._post_session_summary(selected, result, "invalid_transition")
        else:
            # Valid transition — now check artifact requirements
            comments = selector._run_list_script(
                "tm_list_comments.py", selected.issue_id
            )
            sub_issues = selector._run_list_script(
                "tm_list_issues.py", "--parent", selected.issue_id
            )
            artifact_ok, artifact_reason = validator.validate_artifacts(
                pre_status,
                post_status,
                post_issue or {},
                comments or [],
                sub_issues or [],
            )
            if not artifact_ok:
                log.warning(
                    "Issue %s missing artifacts: %s",
                    selected.identifier,
                    artifact_reason,
                )
                self._quarantine_issue(selected, artifact_reason)
                self._state.add_to_history(
                    selected.issue_id,
                    "missing_artifacts",
                    result.duration_seconds,
                    total_cost_usd=result.total_cost_usd,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    num_turns=result.num_turns,
                )
                self._record_session_to_db(selected, result, "missing_artifacts", session_started_at)
                self._post_session_summary(selected, result, "missing_artifacts")
            else:
                log.info(
                    "Issue %s transitioned: %s → %s",
                    selected.identifier,
                    pre_status,
                    post_status,
                )
                self._state.add_to_history(
                    selected.issue_id,
                    "completed",
                    result.duration_seconds,
                    total_cost_usd=result.total_cost_usd,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    num_turns=result.num_turns,
                )
                db_row_id = self._record_session_to_db(
                    selected, result, "completed", session_started_at
                )
                self._post_session_summary(selected, result, "completed")

                # Record PR if the session transitioned to In Review
                if post_status == "In Review" and selected.branch_name:
                    self._capture_pr(selected, project, db_row_id)

    def _capture_pr(
        self,
        selected: selector.SelectedIssue,
        project: dict,
        db_session_id: int | None,
    ) -> None:
        """Check for a PR on the branch and record it to the database."""
        repo_url = project.get("repo", "")
        if not repo_url or not selected.branch_name:
            return

        scripts_dir = selector._find_scripts_dir()
        python = selector._find_venv_python()

        try:
            proc = subprocess.run(
                [
                    python,
                    str(scripts_dir / "check_pr_status.py"),
                    "--repo-url",
                    repo_url,
                    "--branch",
                    selected.branch_name,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if proc.returncode != 0:
                return

            pr_data = json.loads(proc.stdout)
            pr_url = pr_data.get("pr_url", "")
            if pr_url and pr_data.get("state") != "not_found":
                database.record_pr(
                    issue_id=selected.issue_id,
                    pr_url=pr_url,
                    branch_name=selected.branch_name,
                    session_id=db_session_id,
                )
        except Exception:
            log.exception("Failed to capture PR for %s", selected.identifier)

    def _record_session_to_db(
        self,
        selected: selector.SelectedIssue,
        result: session.SessionResult,
        outcome: str,
        started_at: str,
    ) -> int | None:
        """Persist session metrics to the SQLite database."""
        try:
            return database.record_session(
                issue_id=selected.issue_id,
                issue_identifier=selected.identifier,
                project_id=selected.project_id,
                project_name=selected.project_name,
                session_id=result.session_id,
                branch_name=selected.branch_name,
                outcome=outcome,
                exit_code=result.exit_code,
                timed_out=result.timed_out,
                duration_seconds=result.duration_seconds,
                duration_api_ms=result.duration_api_ms,
                total_cost_usd=result.total_cost_usd,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cache_read_input_tokens=result.cache_read_input_tokens,
                cache_creation_input_tokens=result.cache_creation_input_tokens,
                num_turns=result.num_turns,
                started_at=started_at,
            )
        except Exception:
            log.exception("Failed to record session to database for %s", selected.identifier)
            return None

    def _post_session_summary(
        self,
        selected: selector.SelectedIssue,
        result: session.SessionResult,
        outcome: str,
    ) -> None:
        """Post a session metrics comment to the Linear issue."""
        parts = [f"**[Session Complete]** Outcome: {outcome}"]

        duration_mins = result.duration_seconds / 60
        parts.append(f"Duration: {duration_mins:.1f}m (wall clock)")

        if result.duration_api_ms is not None:
            api_mins = result.duration_api_ms / 1000 / 60
            parts.append(f"API time: {api_mins:.1f}m")

        if result.total_cost_usd is not None:
            parts.append(f"Cost: ${result.total_cost_usd:.4f}")

        if result.input_tokens is not None or result.output_tokens is not None:
            token_parts = []
            if result.input_tokens is not None:
                token_parts.append(f"{result.input_tokens} in")
            if result.output_tokens is not None:
                token_parts.append(f"{result.output_tokens} out")
            token_str = f"Tokens: {' / '.join(token_parts)}"
            cache_parts = []
            if result.cache_read_input_tokens is not None:
                cache_parts.append(f"{result.cache_read_input_tokens} read")
            if result.cache_creation_input_tokens is not None:
                cache_parts.append(f"{result.cache_creation_input_tokens} created")
            if cache_parts:
                token_str += f" (cache: {', '.join(cache_parts)})"
            parts.append(token_str)

        if result.num_turns is not None:
            parts.append(f"Turns: {result.num_turns}")

        body = " | ".join(parts)

        scripts_dir = selector._find_scripts_dir()
        python = selector._find_venv_python()

        try:
            subprocess.run(
                [
                    python,
                    str(scripts_dir / "tm_save_comment.py"),
                    "--issue-id",
                    selected.issue_id,
                    "--body",
                    body,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            log.error("Failed to post session summary for %s", selected.identifier)

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

        # Non-code project or conversation issue — create session directory
        dir_name = selected.project_name or selected.identifier
        session_dir = (
            Path.home() / "Projects" / "sessions" / dir_name.lower().replace(" ", "-")
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
        human_id = cfg.get("issue_defaults", {}).get("assignee_id", "")

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
                        *(["--assignee", human_id] if human_id else []),
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
            if self._active_proc:
                log.info(
                    "Killing active session process (pid=%d)", self._active_proc.pid
                )
                self._active_proc.kill()
        else:
            log.info(
                "Signal %d received — draining (finish current session, then exit)",
                signum,
            )
            self._draining = True


_VALID_TRANSITIONS: dict[str, set[str]] = {
    "Todo": {"In Progress", "In Review", "Blocked"},
    "In Progress": {"In Review", "Blocked"},
    "In Review": {"In Review", "Done", "Blocked", "In Progress"},
    "Blocked": {"In Progress", "Todo", "In Review"},
}


def _is_valid_transition(pre: str, post: str) -> bool:
    """Check whether a status transition follows the expected workflow."""
    valid = _VALID_TRANSITIONS.get(pre)
    if valid is None:
        return True  # Unknown pre-status — don't block
    return post in valid


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
