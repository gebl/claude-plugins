"""Tests for process-flow routing logic.

Process-flow is a markdown reference file that Claude follows. These tests
validate the routing decision table by testing the conditions that determine
which route is taken, using the same data structures the scripts produce.
"""


def make_issue(
    status_name: str, status_type: str, labels: list[str] | None = None
) -> dict:
    """Create a minimal issue dict matching tm_get_issue.py output."""
    return {
        "id": "test-issue-id",
        "identifier": "LAN-99",
        "title": "Test issue",
        "status": {"id": "status-id", "name": status_name, "type": status_type},
        "labels": [{"name": label} for label in (labels or [])],
        "branch_name": "test-branch",
        "project_id": "project-id",
        "project_name": "Test Project",
        "parent_id": None,
        "blocked_by": [],
    }


def make_comment(body: str, comment_id: str = "comment-id") -> dict:
    """Create a minimal comment dict matching tm_list_comments.py output."""
    return {"id": comment_id, "issue_id": "test-issue-id", "body": body}


def determine_route(issue: dict, comments: list[dict]) -> str:
    """Determine the process-flow route for an issue.

    This mirrors the routing logic in references/process-flow.md.
    Returns one of: 'in_review', 'blocked', 'plan', 'execute', 'wrap_up'
    """
    status = issue["status"]["name"]

    if status == "In Review":
        return "in_review"

    if status == "Blocked":
        return "blocked"

    plan_comment = None
    for comment in comments:
        if comment["body"].startswith("## Execution Plan"):
            plan_comment = comment
            break

    if status == "Todo" or (status == "In Progress" and plan_comment is None):
        return "plan"

    if plan_comment is not None:
        has_unchecked = "- [ ]" in plan_comment["body"]
        if has_unchecked:
            return "execute"
        return "wrap_up"

    return "plan"


class TestProcessFlowRouting:
    """Test the routing decision table from process-flow.md."""

    def test_in_review_routes_to_pr_check(self):
        issue = make_issue("In Review", "started", ["Claude"])
        assert determine_route(issue, []) == "in_review"

    def test_blocked_routes_to_review_check(self):
        issue = make_issue("Blocked", "started", ["Claude"])
        assert determine_route(issue, []) == "blocked"

    def test_todo_routes_to_plan(self):
        issue = make_issue("Todo", "unstarted")
        assert determine_route(issue, []) == "plan"

    def test_in_progress_no_plan_routes_to_plan(self):
        issue = make_issue("In Progress", "started", ["Claude"])
        assert determine_route(issue, []) == "plan"

    def test_in_progress_with_unchecked_plan_routes_to_execute(self):
        issue = make_issue("In Progress", "started", ["Claude"])
        plan = make_comment("## Execution Plan\n\n- [ ] Step 1\n- [x] Step 2")
        assert determine_route(issue, [plan]) == "execute"

    def test_in_progress_with_fully_checked_plan_routes_to_wrap_up(self):
        issue = make_issue("In Progress", "started", ["Claude"])
        plan = make_comment("## Execution Plan\n\n- [x] Step 1\n- [x] Step 2")
        assert determine_route(issue, [plan]) == "wrap_up"

    def test_non_plan_comments_ignored(self):
        issue = make_issue("In Progress", "started", ["Claude"])
        non_plan = make_comment("**[Activity]** Started work")
        assert determine_route(issue, [non_plan]) == "plan"

    def test_plan_comment_among_other_comments(self):
        issue = make_issue("In Progress", "started", ["Claude"])
        activity = make_comment("**[Activity]** Started work")
        plan = make_comment("## Execution Plan\n\n- [ ] Step 1")
        blocked = make_comment("Plan posted — blocked until reviewed.")
        assert determine_route(issue, [blocked, plan, activity]) == "execute"

    def test_in_progress_with_only_checked_items(self):
        issue = make_issue("In Progress", "started", ["Claude"])
        plan = make_comment("## Execution Plan\n\n- [x] Only step")
        assert determine_route(issue, [plan]) == "wrap_up"


class TestNextFlowSelection:
    """Test the priority sorting logic used by next-flow.md."""

    def test_priority_sort_order(self):
        """Priority 1=Urgent first, 0=None last."""
        issues = [
            {"priority": 0, "id": "none"},
            {"priority": 3, "id": "normal"},
            {"priority": 1, "id": "urgent"},
            {"priority": 4, "id": "low"},
            {"priority": 2, "id": "high"},
        ]

        def sort_key(issue):
            p = issue["priority"]
            return p if p > 0 else 5  # 0 (None) sorts last

        sorted_issues = sorted(issues, key=sort_key)
        assert [i["id"] for i in sorted_issues] == [
            "urgent",
            "high",
            "normal",
            "low",
            "none",
        ]

    def test_blocked_issues_skipped(self):
        """Issues with unresolved blockers should be skipped."""
        issue_with_blocker = {
            "id": "blocked",
            "blocked_by": [
                {"id": "blocker-1", "status": {"type": "started"}},
            ],
        }
        issue_without_blocker = {
            "id": "unblocked",
            "blocked_by": [],
        }

        def is_blocked(issue):
            for blocker in issue.get("blocked_by", []):
                if blocker["status"]["type"] not in ("completed", "canceled"):
                    return True
            return False

        assert is_blocked(issue_with_blocker) is True
        assert is_blocked(issue_without_blocker) is False

    def test_completed_blocker_does_not_block(self):
        """A completed blocker should not prevent selection."""
        issue = {
            "id": "ready",
            "blocked_by": [
                {"id": "done-blocker", "status": {"type": "completed"}},
            ],
        }

        def is_blocked(issue):
            for blocker in issue.get("blocked_by", []):
                if blocker["status"]["type"] not in ("completed", "canceled"):
                    return True
            return False

        assert is_blocked(issue) is False
