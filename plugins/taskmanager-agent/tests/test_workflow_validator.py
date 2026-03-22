"""Tests for taskmanager.daemon.validator — artifact validation."""

from taskmanager.daemon.validator import validate_artifacts


class TestValidateArtifacts:
    """Test artifact requirements for each transition."""

    # --- Todo -> In Progress ---

    def test_todo_to_in_progress_valid(self):
        comments = [{"body": "## Execution Plan\n- [ ] Step 1"}]
        sub_issues = [{"labels": [{"name": "Review"}]}]
        ok, _ = validate_artifacts("Todo", "In Progress", {}, comments, sub_issues)
        assert ok is True

    def test_todo_to_in_progress_missing_plan(self):
        sub_issues = [{"labels": [{"name": "Review"}]}]
        ok, reason = validate_artifacts("Todo", "In Progress", {}, [], sub_issues)
        assert ok is False
        assert "execution plan" in reason.lower()

    def test_todo_to_in_progress_missing_review_sub(self):
        comments = [{"body": "## Execution Plan\n- [ ] Step 1"}]
        ok, reason = validate_artifacts("Todo", "In Progress", {}, comments, [])
        assert ok is False
        assert "review sub-issue" in reason.lower()

    def test_todo_to_in_progress_wrong_label(self):
        comments = [{"body": "## Execution Plan\n- [ ] Step 1"}]
        sub_issues = [{"labels": [{"name": "Bug"}]}]
        ok, reason = validate_artifacts("Todo", "In Progress", {}, comments, sub_issues)
        assert ok is False
        assert "review sub-issue" in reason.lower()

    # --- Todo -> In Review (multi-step: planned + implemented + PR in one session) ---

    def test_todo_to_in_review_valid(self):
        comments = [{"body": "## Execution Plan\n- [x] Step 1"}]
        sub_issues = [{"labels": [{"name": "Review"}]}]
        issue = {"branch_name": "gabe/lan-100-feature"}
        ok, _ = validate_artifacts("Todo", "In Review", issue, comments, sub_issues)
        assert ok is True

    def test_todo_to_in_review_missing_plan(self):
        sub_issues = [{"labels": [{"name": "Review"}]}]
        issue = {"branch_name": "gabe/lan-100-feature"}
        ok, reason = validate_artifacts("Todo", "In Review", issue, [], sub_issues)
        assert ok is False
        assert "execution plan" in reason.lower()

    def test_todo_to_in_review_missing_review_sub(self):
        comments = [{"body": "## Execution Plan\n- [x] Step 1"}]
        issue = {"branch_name": "gabe/lan-100-feature"}
        ok, reason = validate_artifacts("Todo", "In Review", issue, comments, [])
        assert ok is False
        assert "review sub-issue" in reason.lower()

    def test_todo_to_in_review_missing_pr(self):
        comments = [{"body": "## Execution Plan\n- [x] Step 1"}]
        sub_issues = [{"labels": [{"name": "Review"}]}]
        ok, reason = validate_artifacts("Todo", "In Review", {}, comments, sub_issues)
        assert ok is False
        assert "pr" in reason.lower() or "branch" in reason.lower()

    # --- In Progress -> In Review ---

    def test_in_progress_to_in_review_valid(self):
        issue = {"branch_name": "gabe/lan-99-feature"}
        ok, _ = validate_artifacts("In Progress", "In Review", issue, [], [])
        assert ok is True

    def test_in_progress_to_in_review_no_branch(self):
        ok, reason = validate_artifacts("In Progress", "In Review", {}, [], [])
        assert ok is False
        assert "pr" in reason.lower() or "branch" in reason.lower()

    def test_in_progress_to_in_review_empty_branch(self):
        issue = {"branch_name": ""}
        ok, reason = validate_artifacts("In Progress", "In Review", issue, [], [])
        assert ok is False

    # --- In Progress -> Blocked ---

    def test_in_progress_to_blocked_valid(self):
        sub_issues = [{"labels": [{"name": "Review"}]}]
        ok, _ = validate_artifacts("In Progress", "Blocked", {}, [], sub_issues)
        assert ok is True

    def test_in_progress_to_blocked_no_review(self):
        ok, reason = validate_artifacts("In Progress", "Blocked", {}, [], [])
        assert ok is False
        assert "review sub-issue" in reason.lower()

    # --- Transitions with no artifact requirements ---

    def test_in_review_to_done_no_artifacts_needed(self):
        ok, _ = validate_artifacts("In Review", "Done", {}, [], [])
        assert ok is True

    def test_in_review_to_in_progress_no_artifacts_needed(self):
        ok, _ = validate_artifacts("In Review", "In Progress", {}, [], [])
        assert ok is True

    def test_blocked_to_in_progress_no_artifacts_needed(self):
        ok, _ = validate_artifacts("Blocked", "In Progress", {}, [], [])
        assert ok is True


class TestHelperFunctions:
    """Test the internal helper functions."""

    def test_plan_comment_detected(self):
        from taskmanager.daemon.validator import _has_plan_comment

        assert _has_plan_comment([{"body": "## Execution Plan\n- [ ] Do X"}]) is True
        assert _has_plan_comment([{"body": "Some other comment"}]) is False
        assert _has_plan_comment([]) is False

    def test_review_sub_issue_detected(self):
        from taskmanager.daemon.validator import _has_review_sub_issue

        assert _has_review_sub_issue([{"labels": [{"name": "Review"}]}]) is True
        assert _has_review_sub_issue([{"labels": [{"name": "Bug"}]}]) is False
        assert _has_review_sub_issue([{"labels": []}]) is False
        assert _has_review_sub_issue([]) is False

    def test_pr_link_detected(self):
        from taskmanager.daemon.validator import _has_pr_link

        assert _has_pr_link({"branch_name": "feature/x"}) is True
        assert _has_pr_link({"branch_name": ""}) is False
        assert _has_pr_link({}) is False
