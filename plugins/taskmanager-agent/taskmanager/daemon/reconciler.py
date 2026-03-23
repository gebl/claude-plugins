"""Reconcile Review sub-issues with PR state on the git host.

Runs as a pre-pass before issue selection. Closes Review sub-issues
whose PRs have been merged/closed, and mirrors new PR comments to
Linear for the daemon to pick up.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from taskmanager.config import load_config
from taskmanager.daemon.selector import (
    _find_scripts_dir,
    _find_venv_python,
    _run_dict_script,
    _run_list_script,
)

log = logging.getLogger("tm-daemon.reconciler")

_PR_URL_RE = re.compile(r"https?://[^\s\]\)>]+/pulls?/\d+")
_PR_COMMENT_PREFIX = "**[PR Comment]**"


def reconcile_review_issues() -> None:
    """Sync open Review sub-issues with their PR state on the git host."""
    review_issues = _run_list_script("tm_list_issues.py", "--label", "Review")
    if not review_issues:
        return

    # Filter to open issues only
    open_reviews = [
        r
        for r in review_issues
        if r.get("status", {}).get("name") not in ("Done", "Canceled")
    ]
    if not open_reviews:
        return

    log.info("Reconciler: checking %d open Review issue(s)", len(open_reviews))

    for issue in open_reviews:
        pr_url = _extract_pr_url(issue.get("description", ""))
        if not pr_url:
            continue
        _check_and_reconcile(issue, pr_url)


def _extract_pr_url(description: str) -> str | None:
    """Extract the first PR URL from a Review sub-issue description."""
    match = _PR_URL_RE.search(description)
    return match.group(0) if match else None


def _check_and_reconcile(issue: dict, pr_url: str) -> None:
    """Check PR status and take action on the Review sub-issue."""
    issue_id = issue.get("id", "")
    identifier = issue.get("identifier", issue_id)

    pr_status = _run_dict_script("check_pr_status.py", "--pr-url", pr_url)
    if not pr_status:
        log.warning("Reconciler: failed to check PR for %s", identifier)
        return

    state = pr_status.get("state", "")
    comments = pr_status.get("comments", [])

    if state == "merged":
        log.info("Reconciler: %s — PR merged, auto-closing", identifier)
        _auto_close_review(issue, "PR was merged")
    elif state == "closed":
        log.info("Reconciler: %s — PR closed, auto-closing", identifier)
        _auto_close_review(issue, "PR was closed")
    elif state == "open" and comments:
        log.info(
            "Reconciler: %s — PR open with %d comment(s), mirroring",
            identifier,
            len(comments),
        )
        _mirror_pr_comments(issue, comments)
    else:
        log.debug("Reconciler: %s — PR %s, no action", identifier, state)


def _auto_close_review(issue: dict, reason: str) -> None:
    """Post an Activity comment and mark the Review sub-issue as Done."""
    issue_id = issue.get("id", "")
    identifier = issue.get("identifier", issue_id)

    import subprocess

    scripts_dir = _find_scripts_dir()
    python = _find_venv_python()

    # Post activity comment
    try:
        subprocess.run(
            [
                python,
                str(scripts_dir / "tm_save_comment.py"),
                "--issue-id",
                issue_id,
                "--body",
                f"**[Activity]** Auto-closed: {reason}.",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        log.error("Reconciler: failed to post close comment on %s", identifier)

    # Mark as Done
    try:
        subprocess.run(
            [
                python,
                str(scripts_dir / "tm_save_issue.py"),
                "--id",
                issue_id,
                "--state",
                "Done",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        log.error("Reconciler: failed to close %s", identifier)

    # Clean up worktree and local branch for merged PRs
    if reason == "PR was merged":
        _cleanup_worktree(issue, identifier)


def _cleanup_worktree(issue: dict, identifier: str) -> None:
    """Remove the worktree and local branch for a merged PR's parent issue."""
    import subprocess

    parent_id = issue.get("parent_id")
    if not parent_id:
        log.debug("Reconciler: %s has no parent, skipping worktree cleanup", identifier)
        return

    parent = _run_dict_script("tm_get_issue.py", parent_id)
    if not parent:
        log.warning("Reconciler: could not fetch parent %s for cleanup", parent_id)
        return

    branch_name = parent.get("branch_name")
    project_id = parent.get("project_id")
    if not branch_name or not project_id:
        log.debug(
            "Reconciler: parent %s missing branch_name or project_id, skipping cleanup",
            parent_id,
        )
        return

    # Find the project's local_path from config
    config = load_config()
    projects = config.get("projects", [])
    local_path = None
    for project in projects:
        if project.get("id") == project_id:
            local_path = project.get("local_path")
            break

    if not local_path:
        log.debug(
            "Reconciler: no local_path for project %s, skipping cleanup", project_id
        )
        return

    repo_path = Path(local_path)
    if not repo_path.exists():
        return

    worktree_path = repo_path / ".worktrees" / branch_name
    parent_identifier = parent.get("identifier", parent_id)

    # Remove worktree
    if worktree_path.exists():
        try:
            subprocess.run(
                ["git", "worktree", "remove", str(worktree_path), "--force"],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                timeout=30,
            )
            log.info("Reconciler: removed worktree for %s", parent_identifier)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            log.error("Reconciler: failed to remove worktree for %s", parent_identifier)

    # Delete local branch
    try:
        subprocess.run(
            ["git", "branch", "-d", branch_name],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=30,
        )
        log.info("Reconciler: deleted local branch %s", branch_name)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        # Branch may not exist locally or may not be fully merged — not critical
        log.debug("Reconciler: could not delete branch %s (may not exist)", branch_name)


def _mirror_pr_comments(issue: dict, pr_comments: list[dict]) -> None:
    """Mirror new PR comments to the Review sub-issue, skipping duplicates."""
    issue_id = issue.get("id", "")
    identifier = issue.get("identifier", issue_id)

    # Fetch existing comments on the Review sub-issue for dedup
    existing_comments = _run_list_script("tm_list_comments.py", issue_id)
    existing_bodies = {c.get("body", "") for c in existing_comments}

    import subprocess

    scripts_dir = _find_scripts_dir()
    python = _find_venv_python()

    mirrored_count = 0
    for pr_comment in pr_comments:
        author = pr_comment.get("author", "unknown")
        body = pr_comment.get("body", "").strip()
        if not body:
            continue

        mirror_body = f"{_PR_COMMENT_PREFIX} @{author}: {body}"

        # Check if already mirrored
        if mirror_body in existing_bodies:
            continue

        try:
            subprocess.run(
                [
                    python,
                    str(scripts_dir / "tm_save_comment.py"),
                    "--issue-id",
                    issue_id,
                    "--body",
                    mirror_body,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            mirrored_count += 1
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            log.error("Reconciler: failed to mirror comment to %s", identifier)

    if mirrored_count:
        log.info(
            "Reconciler: mirrored %d new comment(s) to %s",
            mirrored_count,
            identifier,
        )
