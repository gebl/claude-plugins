"""Tests for daemon issue selector."""

from taskmanager.daemon.selector import _passes_filters, _priority_sort_key


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
