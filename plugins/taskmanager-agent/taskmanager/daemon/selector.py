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
    source_phase: str | None = None


def select_next_issue(
    quarantined_ids: set[str],
    project_filter: str | None = None,
    seen_comments: dict[str, str] | None = None,
) -> SelectedIssue | None:
    """Select the next issue to process, following next-flow.md phases.

    Returns None if no actionable issues exist.
    """
    cfg = config.load_config()
    active_project_ids = {p["id"] for p in cfg.get("projects", [])}

    # Phase 1: In Review issues needing attention
    result = _phase_in_review(
        cfg,
        active_project_ids,
        quarantined_ids,
        project_filter,
        seen_comments=seen_comments,
    )
    if result:
        return result

    # Phase 1.5: Bug triage — quarantined issues with human guidance
    result = _phase_bug_triage(
        cfg, active_project_ids, quarantined_ids, project_filter,
        seen_comments=seen_comments,
    )
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

    # Phase 5: Conversation issues (projectless, assigned to operator)
    if cfg.get("conversation_issues") and not project_filter:
        result = _phase_conversation(cfg, active_project_ids, quarantined_ids)
        if result:
            return result

    return None


def _phase_in_review(
    cfg: dict,
    active_project_ids: set[str],
    quarantined_ids: set[str],
    project_filter: str | None,
    seen_comments: dict[str, str] | None = None,
) -> SelectedIssue | None:
    """Phase 1: Find In Review issues with actionable PR or Linear comments."""
    log.info("Phase 1: checking In Review issues")
    issues = _run_list_script(
        "tm_list_issues.py", "--status", "In Review", "--label", "Claude"
    )
    if not issues:
        log.info("  → no In Review issues found")
        return None
    log.info("  → found %d In Review issue(s)", len(issues))

    operator_id = cfg.get("operator", {}).get("id", "")
    projects_by_id = {p["id"]: p for p in cfg.get("projects", [])}

    for issue in issues:
        if not _passes_filters(
            issue, active_project_ids, quarantined_ids, project_filter
        ):
            continue

        project = projects_by_id.get(issue.get("project_id", ""))
        branch = issue.get("branch_name")

        # Check PR status first (cheap — single HTTP call to Forgejo)
        if project and project.get("repo") and branch:
            pr_status = _run_dict_script(
                "check_pr_status.py",
                "--repo-url",
                project["repo"],
                "--branch",
                branch,
            )
            if pr_status:
                state = pr_status.get("state", "")
                comments = pr_status.get("comments", [])

                if (
                    state == "merged"
                    or state == "closed"
                    or (state == "open" and comments)
                ):
                    return _to_selected(issue)

        # Fallback: check Linear issue comments (only if PR had no actionable state)
        last_seen_at = (seen_comments or {}).get(issue.get("id", ""))
        if _has_human_comments(issue, operator_id, last_seen_at):
            return _to_selected(issue)

    return None


def _has_human_comments(
    issue: dict,
    operator_id: str,
    last_seen_at: str | None = None,
) -> bool:
    """Check if an In Review issue has new comments from non-operator users.

    Filters out activity comments (prefixed with **[Activity]**) and comments
    from the operator (Claude agent) to find genuine human feedback.
    Skips comments created at or before last_seen_at when provided.
    """
    issue_id = issue.get("id", "")
    comments = _run_list_script("tm_list_comments.py", issue_id)
    if not comments:
        return False

    for comment in comments:
        user_id = comment.get("user_id", "")
        body = comment.get("body", "")
        created_at = comment.get("created_at", "")

        # Skip comments already processed in a previous session
        if last_seen_at and created_at and created_at <= last_seen_at:
            continue

        # Skip operator (Claude agent) comments
        if user_id == operator_id:
            continue

        # Skip automated activity comments
        if body.startswith("**[Activity]**"):
            continue

        log.info(
            "  → %s has human comment from %s",
            issue.get("identifier", issue_id),
            comment.get("user_name", user_id),
        )
        return True

    return False


def _phase_bug_triage(
    cfg: dict,
    active_project_ids: set[str],
    quarantined_ids: set[str],
    project_filter: str | None,
    seen_comments: dict[str, str] | None = None,
) -> SelectedIssue | None:
    """Phase 1.5: Find Bug sub-issues with human comments on quarantined parents.

    When the daemon quarantines an issue, it creates a Bug-labeled sub-issue
    assigned to the human. When the human comments with guidance, this phase
    detects it and returns the parent issue for re-processing. The runner
    auto-removes the parent from quarantine before spawning the session.
    """
    log.info("Phase 1.5: checking Bug sub-issues for human guidance")
    bug_issues = _run_list_script("tm_list_issues.py", "--label", "Bug")
    if not bug_issues:
        log.info("  → no Bug issues found")
        return None

    # Filter to open Bug issues only
    open_bugs = [
        b for b in bug_issues
        if b.get("status", {}).get("name") not in ("Done", "Canceled")
    ]
    if not open_bugs:
        log.info("  → no open Bug issues found")
        return None

    log.info("  → found %d open Bug issue(s), checking for comments", len(open_bugs))

    operator_id = cfg.get("operator", {}).get("id", "")

    for bug in open_bugs:
        bug_id = bug.get("id", "")
        parent_id = bug.get("parent_id")
        if not parent_id:
            continue

        # Check if this bug has human comments
        last_seen_at = (seen_comments or {}).get(bug_id)
        if not _has_human_comments(bug, operator_id, last_seen_at):
            continue

        # Look up the parent issue
        parent = _run_dict_script("tm_get_issue.py", parent_id)
        if not parent:
            continue

        parent_project_id = parent.get("project_id", "")
        if parent_project_id not in active_project_ids:
            continue
        if project_filter and parent.get("project_name") != project_filter:
            continue

        # Check the parent is actually quarantined
        parent_uuid = parent.get("id", "")
        if parent_uuid not in quarantined_ids:
            log.info(
                "  → %s has comment but parent %s is not quarantined, skipping",
                bug.get("identifier", bug_id),
                parent.get("identifier", parent_id),
            )
            continue

        log.info(
            "  → %s has human guidance for quarantined parent %s",
            bug.get("identifier", bug_id),
            parent.get("identifier", parent_id),
        )

        selected = SelectedIssue(
            issue_id=parent_uuid,
            identifier=parent.get("identifier", ""),
            title=parent.get("title", ""),
            status=parent.get("status", {}).get("name", ""),
            priority=parent.get("priority", 0),
            project_id=parent_project_id,
            project_name=parent.get("project_name", ""),
            branch_name=parent.get("branch_name"),
            source_phase="bug_triage",
        )
        return selected

    log.info("  → no Bug issues with human guidance found")
    return None


def _phase_resolved_reviews(
    _cfg: dict,
    active_project_ids: set[str],
    quarantined_ids: set[str],
    project_filter: str | None,
) -> SelectedIssue | None:
    """Phase 2: Find Blocked issues whose review sub-issues are resolved.

    Also auto-resolves Review sub-issues whose parent's PR has been merged.
    """
    log.info("Phase 2: checking Blocked issues for resolved reviews")
    blocked_issues = _run_list_script(
        "tm_list_issues.py", "--status", "Blocked", "--label", "Claude"
    )
    if not blocked_issues:
        log.info("  → no Blocked issues found")
        return None

    filtered = [
        i
        for i in blocked_issues
        if _passes_filters(i, active_project_ids, quarantined_ids, project_filter)
    ]
    if not filtered:
        log.info(
            "  → %d Blocked issue(s) found, none in active projects",
            len(blocked_issues),
        )
        return None

    log.info("  → found %d Blocked issue(s), checking sub-issues", len(filtered))
    filtered.sort(key=_priority_sort_key)

    for issue in filtered:
        children = _run_list_script(
            "tm_list_issues.py", "--parent", issue["id"], "--label", "Review"
        )
        if not children:
            continue

        unresolved = [
            c for c in children
            if c.get("status", {}).get("name") not in ("Done", "Canceled")
        ]

        # All Review sub-issues resolved — ready to unblock
        if not unresolved:
            log.info(
                "  → %s has all %d review(s) resolved",
                issue.get("identifier", issue["id"]),
                len(children),
            )
            return _to_selected(issue)

    log.info("  → no Blocked issues have resolved reviews")
    return None


def _phase_in_progress(
    _cfg: dict,
    active_project_ids: set[str],
    quarantined_ids: set[str],
    project_filter: str | None,
) -> SelectedIssue | None:
    """Phase 3: Find In Progress issues with Claude label."""
    log.info("Phase 3: checking In Progress issues")
    issues = _run_list_script(
        "tm_list_issues.py", "--status", "In Progress", "--label", "Claude"
    )
    if not issues:
        log.info("  → no In Progress issues found")
        return None
    log.info("  → found %d In Progress issue(s)", len(issues))

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
    log.info("Phase 4: checking Todo issues")
    issues = _run_list_script("tm_list_issues.py", "--status", "Todo")
    if not issues:
        log.info("  → no Todo issues found")
        return None
    log.info("  → found %d Todo issue(s), checking blockers", len(issues))

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


def _phase_conversation(
    cfg: dict,
    active_project_ids: set[str],
    quarantined_ids: set[str],
) -> SelectedIssue | None:
    """Phase 5: Find conversation issues — projectless, assigned to operator.

    These are issues without an active project that are assigned to the daemon
    operator. They use a comment-based conversation workflow instead of the
    standard plan→execute→PR pipeline.
    """
    operator_id = cfg.get("operator", {}).get("id", "")
    if not operator_id:
        log.info("Phase 5: skipped — no operator ID configured")
        return None

    log.info("Phase 5: checking conversation issues (assigned to operator)")

    # Fetch issues assigned to the operator across actionable statuses
    for status in ("In Progress", "Todo"):
        issues = _run_list_script(
            "tm_list_issues.py", "--status", status, "--assignee", operator_id
        )
        if not issues:
            continue

        for issue in issues:
            if issue.get("id") in quarantined_ids:
                continue
            # Only pick up issues that are NOT in active projects
            project_id = issue.get("project_id")
            if project_id and project_id in active_project_ids:
                continue
            log.info(
                "  → found conversation issue: %s — %s (%s)",
                issue.get("identifier", "?"),
                issue.get("title", "?"),
                status,
            )
            return _to_selected(issue)

    log.info("  → no conversation issues found")
    return None


def _passes_filters(
    issue: dict,
    active_project_ids: set[str],
    quarantined_ids: set[str],
    project_filter: str | None,
    *,
    allow_projectless: bool = False,
    operator_id: str = "",
) -> bool:
    """Check if an issue passes the active project and quarantine filters.

    When allow_projectless is True, issues with no project are accepted if
    they are assigned to the operator (conversation issues).
    """
    identifier = issue.get("identifier", issue.get("id", "?"))
    if issue.get("id") in quarantined_ids:
        log.info("  ⊘ %s — skipped (quarantined)", identifier)
        return False

    project_id = issue.get("project_id")
    if project_id not in active_project_ids:
        # Allow projectless issues assigned to operator when opted in
        if allow_projectless and not project_id:
            if issue.get("assignee_id") == operator_id:
                return True
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
    args_str = " ".join(args) if args else "(no args)"
    log.info("    query: %s %s", script_name, args_str)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        log.warning("    query timed out: %s", script_name)
        return None

    if result.returncode != 0:
        log.warning(
            "    query failed (%d): %s\n%s",
            result.returncode,
            script_name,
            result.stderr,
        )
        return None

    try:
        parsed = json.loads(result.stdout)
        if isinstance(parsed, list):
            log.info("    result: %d item(s)", len(parsed))
        elif isinstance(parsed, dict):
            summary = parsed.get("identifier") or parsed.get("id", "")
            log.info("    result: %s", summary or "1 object")
        return parsed
    except json.JSONDecodeError:
        log.warning("    invalid JSON from %s: %s", script_name, result.stdout[:200])
        return None
