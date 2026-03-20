"""Issue selection logic for the daemon — no AI tokens consumed.

Reimplements the selection phases from next-flow.md using direct
subprocess calls to the existing Python scripts.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

from taskmanager import config

log = logging.getLogger("tm-daemon.selector")


@dataclass
class SelectedIssue:
    issue_id: str
    identifier: str
    title: str
    status: str
    priority: int
    project_id: str
    project_name: str
    branch_name: str | None = None


def select_next_issue(
    quarantined_ids: set[str],
    project_filter: str | None = None,
) -> SelectedIssue | None:
    """Select the next issue to process, following next-flow.md phases.

    Returns None if no actionable issues exist.
    """
    cfg = config.load_config()
    active_project_ids = {p["id"] for p in cfg.get("projects", [])}

    # Phase 1: In Review issues needing attention
    result = _phase_in_review(cfg, active_project_ids, quarantined_ids, project_filter)
    if result:
        return result

    # Phase 2: Blocked issues with resolved reviews
    result = _phase_resolved_reviews(
        cfg, active_project_ids, quarantined_ids, project_filter
    )
    if result:
        return result

    # Phase 3: In Progress issues
    result = _phase_in_progress(
        cfg, active_project_ids, quarantined_ids, project_filter
    )
    if result:
        return result

    # Phase 4: Todo issues by priority
    result = _phase_todo(cfg, active_project_ids, quarantined_ids, project_filter)
    if result:
        return result

    return None


def _phase_in_review(
    cfg: dict,
    active_project_ids: set[str],
    quarantined_ids: set[str],
    project_filter: str | None,
) -> SelectedIssue | None:
    """Phase 1: Find In Review issues with actionable PR status."""
    issues = _run_list_script(
        "tm_list_issues.py", "--status", "In Review", "--label", "Claude"
    )
    if not issues:
        return None

    projects_by_id = {p["id"]: p for p in cfg.get("projects", [])}

    for issue in issues:
        if not _passes_filters(
            issue, active_project_ids, quarantined_ids, project_filter
        ):
            continue

        project = projects_by_id.get(issue.get("project_id", ""))
        if not project or not project.get("repo"):
            continue

        branch = issue.get("branch_name")
        if not branch:
            continue

        pr_status = _run_dict_script(
            "check_pr_status.py",
            "--repo-url",
            project["repo"],
            "--branch",
            branch,
        )
        if not pr_status:
            continue

        state = pr_status.get("state", "")
        comments = pr_status.get("comments", [])

        if state == "merged" or state == "closed" or (state == "open" and comments):
            return _to_selected(issue)

    return None


def _phase_resolved_reviews(
    _cfg: dict,
    active_project_ids: set[str],
    quarantined_ids: set[str],
    project_filter: str | None,
) -> SelectedIssue | None:
    """Phase 2: Find Blocked issues with resolved review sub-issues."""
    review_issues = _run_list_script(
        "tm_list_issues.py", "--status", "Done", "--label", "Review"
    )
    if not review_issues:
        return None

    candidates = []
    for review in review_issues:
        parent_id = review.get("parent_id")
        if not parent_id:
            continue

        parent = _run_dict_script("tm_get_issue.py", parent_id)
        if not parent:
            continue

        parent_status = parent.get("status", {}).get("name", "")
        parent_status_type = parent.get("status", {}).get("type", "")
        if parent_status_type in ("completed", "canceled"):
            continue
        if parent_status != "Blocked":
            continue
        if not _passes_filters(
            parent, active_project_ids, quarantined_ids, project_filter
        ):
            continue

        candidates.append(parent)

    if not candidates:
        return None

    candidates.sort(key=_priority_sort_key)
    return _to_selected(candidates[0])


def _phase_in_progress(
    _cfg: dict,
    active_project_ids: set[str],
    quarantined_ids: set[str],
    project_filter: str | None,
) -> SelectedIssue | None:
    """Phase 3: Find In Progress issues with Claude label."""
    issues = _run_list_script(
        "tm_list_issues.py", "--status", "In Progress", "--label", "Claude"
    )
    if not issues:
        return None

    filtered = [
        i
        for i in issues
        if _passes_filters(i, active_project_ids, quarantined_ids, project_filter)
    ]
    if not filtered:
        return None

    filtered.sort(key=_priority_sort_key)
    return _to_selected(filtered[0])


def _phase_todo(
    _cfg: dict,
    active_project_ids: set[str],
    quarantined_ids: set[str],
    project_filter: str | None,
) -> SelectedIssue | None:
    """Phase 4: Select highest-priority unblocked Todo issue."""
    issues = _run_list_script("tm_list_issues.py", "--status", "Todo")
    if not issues:
        return None

    filtered = [
        i
        for i in issues
        if _passes_filters(i, active_project_ids, quarantined_ids, project_filter)
    ]
    filtered.sort(key=_priority_sort_key)

    for issue in filtered:
        detail = _run_dict_script("tm_get_issue.py", issue["id"], "--relations")
        if not detail:
            continue
        blocked_by = detail.get("blocked_by", [])
        is_blocked = any(
            b.get("status", {}).get("type") not in ("completed", "canceled")
            for b in blocked_by
        )
        if not is_blocked:
            return _to_selected(issue)

    return None


def _passes_filters(
    issue: dict,
    active_project_ids: set[str],
    quarantined_ids: set[str],
    project_filter: str | None,
) -> bool:
    """Check if an issue passes the active project and quarantine filters."""
    if issue.get("id") in quarantined_ids:
        return False
    if issue.get("project_id") not in active_project_ids:
        return False
    if project_filter and issue.get("project_name") != project_filter:
        return False
    return True


def _priority_sort_key(issue: dict) -> int:
    """Sort key: 1=Urgent first, 0=None last."""
    p = issue.get("priority", 0)
    return p if p > 0 else 5


def _to_selected(issue: dict) -> SelectedIssue:
    return SelectedIssue(
        issue_id=issue["id"],
        identifier=issue.get("identifier", ""),
        title=issue.get("title", ""),
        status=issue.get("status", {}).get("name", ""),
        priority=issue.get("priority", 0),
        project_id=issue.get("project_id", ""),
        project_name=issue.get("project_name", ""),
        branch_name=issue.get("branch_name"),
    )


def _find_scripts_dir() -> Path:
    """Locate the scripts directory relative to this package."""
    # Walk up from taskmanager/daemon/selector.py to repo root
    pkg_dir = Path(__file__).resolve().parent.parent.parent
    scripts_dir = pkg_dir / "scripts"
    if scripts_dir.exists():
        return scripts_dir
    raise FileNotFoundError(f"Scripts directory not found at {scripts_dir}")


def _find_venv_python() -> str:
    """Locate the venv python relative to this package."""
    pkg_dir = Path(__file__).resolve().parent.parent.parent
    venv_python = pkg_dir / ".venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    return "python"


def _run_list_script(script_name: str, *args: str) -> list[dict]:
    """Run a script that returns a JSON array."""
    result = _run_script(script_name, *args)
    if isinstance(result, list):
        return result
    return []


def _run_dict_script(script_name: str, *args: str) -> dict | None:
    """Run a script that returns a JSON object."""
    result = _run_script(script_name, *args)
    if isinstance(result, dict):
        return result
    return None


def _run_script(script_name: str, *args: str) -> dict | list | None:
    """Run a script and return parsed JSON output."""
    scripts_dir = _find_scripts_dir()
    python = _find_venv_python()
    script_path = scripts_dir / script_name

    cmd = [python, str(script_path), *args]
    log.debug("Running: %s", " ".join(cmd))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        log.warning("Script timed out: %s", script_name)
        return None

    if result.returncode != 0:
        log.warning(
            "Script failed (%d): %s\n%s", result.returncode, script_name, result.stderr
        )
        return None

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        log.warning("Invalid JSON from %s: %s", script_name, result.stdout[:200])
        return None
