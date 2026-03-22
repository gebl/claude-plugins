"""Daemon state persistence — quarantine, history, and session tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

STATE_DIR = Path.home() / ".claude" / "taskmanager"
STATE_FILE = STATE_DIR / "daemon-state.yaml"

HISTORY_CAP = 15


@dataclass
class ActiveSession:
    issue_id: str
    started_at: str
    pid: int


@dataclass
class QuarantineEntry:
    issue_id: str
    failed_at: str
    reason: str


@dataclass
class HistoryEntry:
    issue_id: str
    outcome: str
    duration_seconds: float
    finished_at: str
    total_cost_usd: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    num_turns: int | None = None


@dataclass
class DaemonState:
    pid: int | None = None
    started_at: str | None = None
    poll_count: int = 0
    last_poll: str | None = None
    last_work_found: str | None = None
    current_interval_seconds: float = 60.0
    active_session: ActiveSession | None = None
    quarantine: list[QuarantineEntry] = field(default_factory=list)
    history: list[HistoryEntry] = field(default_factory=list)
    seen_comments: dict[str, str] = field(default_factory=dict)

    @staticmethod
    def load() -> DaemonState:
        """Load state from disk, or return a fresh state if missing."""
        if not STATE_FILE.exists():
            return DaemonState()

        raw = yaml.safe_load(STATE_FILE.read_text()) or {}

        active = None
        if raw.get("active_session"):
            a = raw["active_session"]
            active = ActiveSession(
                issue_id=a["issue_id"],
                started_at=a["started_at"],
                pid=a["pid"],
            )

        quarantine = [
            QuarantineEntry(
                issue_id=q["issue_id"],
                failed_at=q["failed_at"],
                reason=q["reason"],
            )
            for q in raw.get("quarantine", [])
        ]

        history = [
            HistoryEntry(
                issue_id=h["issue_id"],
                outcome=h["outcome"],
                duration_seconds=h["duration_seconds"],
                finished_at=h["finished_at"],
                total_cost_usd=h.get("total_cost_usd"),
                input_tokens=h.get("input_tokens"),
                output_tokens=h.get("output_tokens"),
                num_turns=h.get("num_turns"),
            )
            for h in raw.get("history", [])
        ]

        return DaemonState(
            pid=raw.get("pid"),
            started_at=raw.get("started_at"),
            poll_count=raw.get("poll_count", 0),
            last_poll=raw.get("last_poll"),
            last_work_found=raw.get("last_work_found"),
            current_interval_seconds=raw.get("current_interval_seconds", 60.0),
            active_session=active,
            quarantine=quarantine,
            history=history,
            seen_comments=raw.get("seen_comments", {}),
        )

    def save(self) -> None:
        """Write state to disk."""
        STATE_DIR.mkdir(parents=True, exist_ok=True)

        active = None
        if self.active_session:
            active = {
                "issue_id": self.active_session.issue_id,
                "started_at": self.active_session.started_at,
                "pid": self.active_session.pid,
            }

        data = {
            "pid": self.pid,
            "started_at": self.started_at,
            "poll_count": self.poll_count,
            "last_poll": self.last_poll,
            "last_work_found": self.last_work_found,
            "current_interval_seconds": self.current_interval_seconds,
            "active_session": active,
            "quarantine": [
                {"issue_id": q.issue_id, "failed_at": q.failed_at, "reason": q.reason}
                for q in self.quarantine
            ],
            "history": [
                {
                    "issue_id": h.issue_id,
                    "outcome": h.outcome,
                    "duration_seconds": h.duration_seconds,
                    "finished_at": h.finished_at,
                    **(
                        {"total_cost_usd": h.total_cost_usd}
                        if h.total_cost_usd is not None
                        else {}
                    ),
                    **(
                        {"input_tokens": h.input_tokens}
                        if h.input_tokens is not None
                        else {}
                    ),
                    **(
                        {"output_tokens": h.output_tokens}
                        if h.output_tokens is not None
                        else {}
                    ),
                    **({"num_turns": h.num_turns} if h.num_turns is not None else {}),
                }
                for h in self.history
            ],
            "seen_comments": self.seen_comments,
        }

        STATE_FILE.write_text(
            yaml.dump(data, default_flow_style=False, sort_keys=False)
        )

    def is_quarantined(self, issue_id: str) -> bool:
        return any(q.issue_id == issue_id for q in self.quarantine)

    def add_to_quarantine(self, issue_id: str, reason: str) -> None:
        if self.is_quarantined(issue_id):
            return
        self.quarantine.append(
            QuarantineEntry(
                issue_id=issue_id,
                failed_at=_now_iso(),
                reason=reason,
            )
        )

    def add_to_history(
        self,
        issue_id: str,
        outcome: str,
        duration_seconds: float,
        total_cost_usd: float | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        num_turns: int | None = None,
    ) -> None:
        self.history.append(
            HistoryEntry(
                issue_id=issue_id,
                outcome=outcome,
                duration_seconds=duration_seconds,
                finished_at=_now_iso(),
                total_cost_usd=total_cost_usd,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                num_turns=num_turns,
            )
        )
        # Cap history at HISTORY_CAP entries, keeping most recent
        if len(self.history) > HISTORY_CAP:
            self.history = self.history[-HISTORY_CAP:]

    def clear_active_session(self) -> None:
        self.active_session = None

    def set_active_session(self, issue_id: str, pid: int) -> None:
        self.active_session = ActiveSession(
            issue_id=issue_id,
            started_at=_now_iso(),
            pid=pid,
        )

    def mark_comments_seen(self, issue_id: str, timestamp: str) -> None:
        """Record the latest comment timestamp seen for an issue."""
        self.seen_comments[issue_id] = timestamp

    def last_seen_comment_at(self, issue_id: str) -> str | None:
        """Return the last seen comment timestamp for an issue, or None."""
        return self.seen_comments.get(issue_id)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
