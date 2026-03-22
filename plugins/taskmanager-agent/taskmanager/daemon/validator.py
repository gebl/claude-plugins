"""Workflow artifact validator for the daemon.

Validates that required artifacts exist for each state transition,
complementing the transition map in runner.py.
"""

from __future__ import annotations

import logging

log = logging.getLogger("tm-daemon.validator")


def _has_plan_comment(comments: list[dict]) -> bool:
    """Check if any comment starts with '## Execution Plan'."""
    return any(c.get("body", "").startswith("## Execution Plan") for c in comments)


def _has_review_sub_issue(sub_issues: list[dict]) -> bool:
    """Check if any sub-issue has the Review label."""
    for sub in sub_issues:
        labels = sub.get("labels", [])
        if any(label.get("name") == "Review" for label in labels):
            return True
    return False


def _has_pr_link(issue: dict) -> bool:
    """Check if the issue has a branch (proxy for PR existence)."""
    return bool(issue.get("branch_name"))


def validate_artifacts(
    pre_status: str,
    post_status: str,
    post_issue: dict,
    comments: list[dict],
    sub_issues: list[dict],
) -> tuple[bool, str]:
    """Validate that required artifacts exist for a transition.

    Call this AFTER confirming the transition is in the valid set.
    Returns (valid, reason).
    """
    if pre_status == "Todo" and post_status == "In Progress":
        if not _has_plan_comment(comments):
            return False, "Todo -> In Progress requires an execution plan comment"
        if not _has_review_sub_issue(sub_issues):
            return False, "Todo -> In Progress requires a review sub-issue"

    if pre_status == "Todo" and post_status == "In Review":
        if not _has_plan_comment(comments):
            return False, "Todo -> In Review requires an execution plan comment"
        if not _has_review_sub_issue(sub_issues):
            return False, "Todo -> In Review requires a review sub-issue"
        if not _has_pr_link(post_issue):
            return False, "Todo -> In Review requires a linked PR (branch_name)"

    if pre_status == "In Progress" and post_status == "In Review":
        if not _has_pr_link(post_issue):
            return False, "In Progress -> In Review requires a linked PR (branch_name)"

    if pre_status == "In Progress" and post_status == "Blocked":
        if not _has_review_sub_issue(sub_issues):
            return (
                False,
                "In Progress -> Blocked requires a review sub-issue with Review label",
            )

    return True, "Valid"
