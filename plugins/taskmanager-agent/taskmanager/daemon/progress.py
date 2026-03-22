"""Progress reporting — posts periodic status comments to Linear issues."""

from __future__ import annotations

import json
import logging
import subprocess
import time
from collections import Counter
from pathlib import Path

log = logging.getLogger("tm-daemon.progress")

PROGRESS_INTERVAL = 300  # 5 minutes
MAX_SNIPPETS = 10


def _find_scripts_dir() -> Path:
    pkg_dir = Path(__file__).resolve().parent.parent.parent
    scripts_dir = pkg_dir / "scripts"
    if scripts_dir.exists():
        return scripts_dir
    raise FileNotFoundError(f"Scripts directory not found at {scripts_dir}")


def _find_venv_python() -> str:
    pkg_dir = Path(__file__).resolve().parent.parent.parent
    venv_python = pkg_dir / ".venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    return "python"


class ProgressTracker:
    """Tracks session activity and posts progress comments to Linear."""

    def __init__(self, issue_id: str, issue_identifier: str) -> None:
        self._issue_id = issue_id
        self._issue_identifier = issue_identifier
        self._start_time = time.monotonic()
        self._last_post_time = time.monotonic()
        self._snippets: list[str] = []
        self._tool_counts: Counter[str] = Counter()
        self._posted_count = 0

    def on_event(self, raw_line: str) -> None:
        """Process a stream-json event. Posts a comment if triggered."""
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError:
            return

        event_type = event.get("type", "")
        triggered = False

        if event_type == "assistant":
            self._extract_text(event)

        elif event_type == "tool_use":
            tool_name = event.get("tool", {}).get("name", event.get("name", ""))
            if tool_name:
                self._tool_counts[tool_name] += 1
            if self._is_checklist_tick(event):
                triggered = True

        elif event_type == "result":
            # Always post a final summary
            triggered = True

        # Time-based trigger
        elapsed_since_post = time.monotonic() - self._last_post_time
        if elapsed_since_post >= PROGRESS_INTERVAL:
            triggered = True

        if triggered and self._snippets:
            self._post_progress()

    def _extract_text(self, event: dict) -> None:
        """Extract text snippets from assistant events."""
        msg = event.get("message", {})
        for block in msg.get("content", []):
            if block.get("type") != "text":
                continue
            text = block.get("text", "").strip()
            if not text:
                continue
            # Split into lines and keep meaningful ones
            for line in text.splitlines():
                line = line.strip()
                if len(line) > 15:
                    self._snippets.append(line)
                    if len(self._snippets) > MAX_SNIPPETS:
                        self._snippets.pop(0)

    def _is_checklist_tick(self, event: dict) -> bool:
        """Detect if a tool_use is updating a plan checklist."""
        tool_name = event.get("tool", {}).get("name", event.get("name", ""))
        if tool_name != "Bash":
            return False
        tool_input = event.get("tool", {}).get("input", {})
        command = tool_input.get("command", "")
        return "tm_save_comment" in command and "- [x]" in command

    def _post_progress(self) -> None:
        """Post a progress comment to the Linear issue."""
        elapsed_minutes = int((time.monotonic() - self._start_time) / 60)
        self._posted_count += 1

        lines = [f"**[Progress]** {elapsed_minutes}m elapsed"]
        lines.append("")

        for snippet in self._snippets:
            # Truncate long lines
            if len(snippet) > 120:
                snippet = snippet[:117] + "..."
            lines.append(f"- {snippet}")

        if self._tool_counts:
            lines.append("")
            tool_parts = []
            for name, count in self._tool_counts.most_common():
                tool_parts.append(f"{count}× {name}")
            lines.append(f"Tools: {', '.join(tool_parts)}")

        body = "\n".join(lines)

        scripts_dir = _find_scripts_dir()
        python = _find_venv_python()

        try:
            subprocess.run(
                [
                    python,
                    str(scripts_dir / "tm_save_comment.py"),
                    "--issue-id",
                    self._issue_id,
                    "--body",
                    body,
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            log.info(
                "Posted progress comment #%d for %s (%dm elapsed)",
                self._posted_count,
                self._issue_identifier,
                elapsed_minutes,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            log.warning(
                "Failed to post progress comment for %s", self._issue_identifier
            )

        self._last_post_time = time.monotonic()
        self._snippets.clear()
