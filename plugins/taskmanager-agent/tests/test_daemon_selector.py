"""Tests for daemon issue selector."""

from taskmanager.daemon.selector import (
    _has_human_comments,
    _passes_filters,
    _phase_conversation,
    _priority_sort_key,
)


class TestPassesFilters:
    def test_passes_all_filters(self):
        issue = {"id": "i1", "project_id": "p1", "project_name": "Proj"}
        assert _passes_filters(issue, {"p1"}, set(), None) is True

    def test_rejected_by_quarantine(self):
        issue = {"id": "i1", "project_id": "p1", "project_name": "Proj"}
        assert _passes_filters(issue, {"p1"}, {"i1"}, None) is False

    def test_rejected_by_project_not_active(self):
        issue = {"id": "i1", "project_id": "p2", "project_name": "Proj"}
        assert _passes_filters(issue, {"p1"}, set(), None) is False

    def test_rejected_by_project_filter(self):
        issue = {"id": "i1", "project_id": "p1", "project_name": "Proj A"}
        assert _passes_filters(issue, {"p1"}, set(), "Proj B") is False

    def test_passes_with_matching_project_filter(self):
        issue = {"id": "i1", "project_id": "p1", "project_name": "Proj A"}
        assert _passes_filters(issue, {"p1"}, set(), "Proj A") is True


class TestPrioritySortKey:
    def test_urgent_first(self):
        assert _priority_sort_key({"priority": 1}) == 1

    def test_none_last(self):
        assert _priority_sort_key({"priority": 0}) == 5

    def test_sort_order(self):
        issues = [
            {"priority": 0},
            {"priority": 3},
            {"priority": 1},
            {"priority": 4},
            {"priority": 2},
        ]
        sorted_priorities = [
            i["priority"] for i in sorted(issues, key=_priority_sort_key)
        ]
        assert sorted_priorities == [1, 2, 3, 4, 0]


class TestHasHumanComments:
    def test_no_comments(self, monkeypatch):
        monkeypatch.setattr(
            "taskmanager.daemon.selector._run_list_script", lambda *a: []
        )
        issue = {"id": "i1", "identifier": "LAN-1"}
        assert _has_human_comments(issue, "operator-id") is False

    def test_only_operator_comments(self, monkeypatch):
        monkeypatch.setattr(
            "taskmanager.daemon.selector._run_list_script",
            lambda *a: [
                {"user_id": "operator-id", "user_name": "Claude", "body": "Done"},
            ],
        )
        issue = {"id": "i1", "identifier": "LAN-1"}
        assert _has_human_comments(issue, "operator-id") is False

    def test_only_activity_comments(self, monkeypatch):
        monkeypatch.setattr(
            "taskmanager.daemon.selector._run_list_script",
            lambda *a: [
                {
                    "user_id": "human-id",
                    "user_name": "Gabe",
                    "body": "**[Activity]** PR merged.",
                },
            ],
        )
        issue = {"id": "i1", "identifier": "LAN-1"}
        assert _has_human_comments(issue, "operator-id") is False

    def test_human_comment_detected(self, monkeypatch):
        monkeypatch.setattr(
            "taskmanager.daemon.selector._run_list_script",
            lambda *a: [
                {
                    "user_id": "operator-id",
                    "user_name": "Claude",
                    "body": "**[Activity]** Moved to In Review",
                },
                {
                    "user_id": "human-id",
                    "user_name": "Gabe",
                    "body": "Please fix the error handling",
                },
            ],
        )
        issue = {"id": "i1", "identifier": "LAN-1"}
        assert _has_human_comments(issue, "operator-id") is True

    def test_already_seen_comment_ignored(self, monkeypatch):
        """A human comment created at or before last_seen_at should be skipped."""
        monkeypatch.setattr(
            "taskmanager.daemon.selector._run_list_script",
            lambda *a: [
                {
                    "user_id": "human-id",
                    "user_name": "Gabe",
                    "body": "Please fix the error handling",
                    "created_at": "2024-01-15T10:00:00+00:00",
                },
            ],
        )
        issue = {"id": "i1", "identifier": "LAN-1"}
        # last_seen_at is equal to the comment timestamp — should be skipped
        assert (
            _has_human_comments(
                issue, "operator-id", last_seen_at="2024-01-15T10:00:00+00:00"
            )
            is False
        )

    def test_newer_comment_triggers(self, monkeypatch):
        """A human comment created after last_seen_at should still trigger."""
        monkeypatch.setattr(
            "taskmanager.daemon.selector._run_list_script",
            lambda *a: [
                {
                    "user_id": "human-id",
                    "user_name": "Gabe",
                    "body": "New feedback here",
                    "created_at": "2024-01-16T09:00:00+00:00",
                },
            ],
        )
        issue = {"id": "i1", "identifier": "LAN-1"}
        # last_seen_at is before the comment — should trigger
        assert (
            _has_human_comments(
                issue, "operator-id", last_seen_at="2024-01-15T10:00:00+00:00"
            )
            is True
        )


class TestPassesFiltersProjectless:
    """Tests for _passes_filters with allow_projectless support."""

    def test_projectless_rejected_by_default(self):
        """Projectless issues are rejected when allow_projectless is False."""
        issue = {"id": "i1", "project_id": None, "assignee_id": "op1"}
        assert _passes_filters(issue, {"p1"}, set(), None) is False

    def test_projectless_accepted_when_opted_in(self):
        """Projectless issues pass when assigned to operator and opted in."""
        issue = {"id": "i1", "project_id": None, "assignee_id": "op1"}
        assert (
            _passes_filters(
                issue, {"p1"}, set(), None, allow_projectless=True, operator_id="op1"
            )
            is True
        )

    def test_projectless_rejected_wrong_assignee(self):
        """Projectless issues are rejected if not assigned to operator."""
        issue = {"id": "i1", "project_id": None, "assignee_id": "other-user"}
        assert (
            _passes_filters(
                issue, {"p1"}, set(), None, allow_projectless=True, operator_id="op1"
            )
            is False
        )

    def test_projectless_rejected_no_assignee(self):
        """Projectless issues are rejected if no assignee."""
        issue = {"id": "i1", "project_id": None, "assignee_id": None}
        assert (
            _passes_filters(
                issue, {"p1"}, set(), None, allow_projectless=True, operator_id="op1"
            )
            is False
        )

    def test_projectless_quarantined_still_rejected(self):
        """Quarantine takes precedence over projectless acceptance."""
        issue = {"id": "i1", "project_id": None, "assignee_id": "op1"}
        assert (
            _passes_filters(
                issue, {"p1"}, {"i1"}, None, allow_projectless=True, operator_id="op1"
            )
            is False
        )


class TestPhaseConversation:
    """Tests for _phase_conversation (Phase 5)."""

    def _make_cfg(self, operator_id: str = "op1") -> dict:
        return {
            "operator": {"id": operator_id},
            "projects": [{"id": "p1", "name": "Active Project"}],
        }

    def test_no_operator_id_skips(self, monkeypatch):
        """Phase 5 is skipped if no operator ID is configured."""
        cfg = {"operator": {}, "projects": []}
        result = _phase_conversation(cfg, {"p1"}, set())
        assert result is None

    def test_finds_projectless_issue(self, monkeypatch):
        """Phase 5 picks up projectless issues assigned to operator."""
        issue = {
            "id": "conv1",
            "identifier": "LAN-50",
            "title": "Set up new project",
            "status": {"name": "In Progress"},
            "priority": 2,
            "project_id": None,
            "project_name": None,
            "assignee_id": "op1",
        }
        monkeypatch.setattr(
            "taskmanager.daemon.selector._run_list_script",
            lambda script, *args: [issue] if "In Progress" in args else [],
        )
        result = _phase_conversation(self._make_cfg(), {"p1"}, set())
        assert result is not None
        assert result.issue_id == "conv1"
        assert result.identifier == "LAN-50"

    def test_skips_active_project_issues(self, monkeypatch):
        """Phase 5 skips issues that belong to active projects."""
        issue = {
            "id": "proj1",
            "identifier": "LAN-51",
            "title": "Active project issue",
            "status": {"name": "In Progress"},
            "priority": 2,
            "project_id": "p1",
            "project_name": "Active Project",
            "assignee_id": "op1",
        }
        monkeypatch.setattr(
            "taskmanager.daemon.selector._run_list_script",
            lambda script, *args: [issue],
        )
        result = _phase_conversation(self._make_cfg(), {"p1"}, set())
        assert result is None

    def test_skips_quarantined_issues(self, monkeypatch):
        """Phase 5 skips quarantined issues."""
        issue = {
            "id": "conv2",
            "identifier": "LAN-52",
            "title": "Quarantined conversation",
            "status": {"name": "Todo"},
            "priority": 3,
            "project_id": None,
            "project_name": None,
            "assignee_id": "op1",
        }
        monkeypatch.setattr(
            "taskmanager.daemon.selector._run_list_script",
            lambda script, *args: [issue],
        )
        result = _phase_conversation(self._make_cfg(), set(), {"conv2"})
        assert result is None

    def test_prefers_in_progress_over_todo(self, monkeypatch):
        """Phase 5 checks In Progress before Todo."""
        in_progress_issue = {
            "id": "ip1",
            "identifier": "LAN-60",
            "title": "In progress conversation",
            "status": {"name": "In Progress"},
            "priority": 3,
            "project_id": None,
            "project_name": None,
            "assignee_id": "op1",
        }
        todo_issue = {
            "id": "td1",
            "identifier": "LAN-61",
            "title": "Todo conversation",
            "status": {"name": "Todo"},
            "priority": 1,
            "project_id": None,
            "project_name": None,
            "assignee_id": "op1",
        }

        def mock_list(script, *args):
            if "In Progress" in args:
                return [in_progress_issue]
            if "Todo" in args:
                return [todo_issue]
            return []

        monkeypatch.setattr("taskmanager.daemon.selector._run_list_script", mock_list)
        result = _phase_conversation(self._make_cfg(), set(), set())
        assert result is not None
        assert result.issue_id == "ip1"

    def test_no_issues_returns_none(self, monkeypatch):
        """Phase 5 returns None when no conversation issues exist."""
        monkeypatch.setattr(
            "taskmanager.daemon.selector._run_list_script",
            lambda script, *args: [],
        )
        result = _phase_conversation(self._make_cfg(), {"p1"}, set())
        assert result is None
