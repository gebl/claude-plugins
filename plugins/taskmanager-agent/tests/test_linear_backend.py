"""Tests for the Linear GraphQL backend using pytest-httpx mocks."""

from __future__ import annotations

import pytest
from pytest_httpx import HTTPXMock

from taskmanager.backends.linear import API_URL, LinearBackend
from taskmanager.models import Comment, Issue, Label, Project, Status, Team


@pytest.fixture
def backend():
    config = {"backend": "linear", "linear": {"token_env": "LINEAR_TOKEN"}}
    return LinearBackend(config, token="test-token")


def _gql_response(data: dict) -> dict:
    return {"data": data}


class TestListTeams:
    def test_returns_team_objects(self, backend: LinearBackend, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=API_URL,
            json=_gql_response({
                "teams": {
                    "nodes": [
                        {"id": "t1", "name": "Engineering", "key": "ENG"},
                        {"id": "t2", "name": "Design", "key": "DES"},
                    ]
                }
            }),
        )
        teams = backend.list_teams()
        assert len(teams) == 2
        assert isinstance(teams[0], Team)
        assert teams[0].id == "t1"
        assert teams[0].name == "Engineering"
        assert teams[0].key == "ENG"
        assert teams[1].key == "DES"

    def test_empty_teams(self, backend: LinearBackend, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=API_URL,
            json=_gql_response({"teams": {"nodes": []}}),
        )
        assert backend.list_teams() == []


class TestListStatuses:
    def test_returns_status_objects(self, backend: LinearBackend, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=API_URL,
            json=_gql_response({
                "workflowStates": {
                    "nodes": [
                        {"id": "s1", "name": "Backlog", "type": "backlog"},
                        {"id": "s2", "name": "In Progress", "type": "started"},
                    ]
                }
            }),
        )
        statuses = backend.list_statuses("t1")
        assert len(statuses) == 2
        assert isinstance(statuses[0], Status)
        assert statuses[0].name == "Backlog"
        assert statuses[0].type == "backlog"
        assert statuses[1].type == "started"


class TestCreateStatus:
    def test_returns_new_status(self, backend: LinearBackend, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=API_URL,
            json=_gql_response({
                "workflowStateCreate": {
                    "workflowState": {"id": "s3", "name": "Review", "type": "started"}
                }
            }),
        )
        status = backend.create_status("t1", "Review", "started", "#ff0000")
        assert isinstance(status, Status)
        assert status.id == "s3"
        assert status.name == "Review"
        assert status.type == "started"


class TestListIssues:
    def _issue_node(self, **overrides) -> dict:
        node = {
            "id": "i1",
            "identifier": "ENG-42",
            "title": "Fix the widget",
            "description": "It is broken",
            "priority": 2,
            "url": "https://linear.app/issue/ENG-42",
            "branchName": "fix/widget",
            "state": {"id": "s1", "name": "In Progress", "type": "started"},
            "project": {"id": "p1", "name": "Widget Rework"},
            "labels": {"nodes": [{"id": "l1", "name": "bug", "color": "#ff0000"}]},
            "parent": None,
        }
        node.update(overrides)
        return node

    def test_returns_issue_objects(self, backend: LinearBackend, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=API_URL,
            json=_gql_response({"issues": {"nodes": [self._issue_node()]}}),
        )
        issues = backend.list_issues()
        assert len(issues) == 1
        issue = issues[0]
        assert isinstance(issue, Issue)
        assert issue.id == "i1"
        assert issue.identifier == "ENG-42"
        assert issue.title == "Fix the widget"
        assert issue.priority == 2
        assert issue.url == "https://linear.app/issue/ENG-42"
        assert issue.branch_name == "fix/widget"

    def test_status_mapping(self, backend: LinearBackend, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=API_URL,
            json=_gql_response({"issues": {"nodes": [self._issue_node()]}}),
        )
        issue = backend.list_issues()[0]
        assert isinstance(issue.status, Status)
        assert issue.status.name == "In Progress"
        assert issue.status.type == "started"

    def test_labels_mapping(self, backend: LinearBackend, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=API_URL,
            json=_gql_response({"issues": {"nodes": [self._issue_node()]}}),
        )
        issue = backend.list_issues()[0]
        assert len(issue.labels) == 1
        assert isinstance(issue.labels[0], Label)
        assert issue.labels[0].name == "bug"

    def test_project_mapping(self, backend: LinearBackend, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=API_URL,
            json=_gql_response({"issues": {"nodes": [self._issue_node()]}}),
        )
        issue = backend.list_issues()[0]
        assert issue.project_id == "p1"
        assert issue.project_name == "Widget Rework"

    def test_null_project(self, backend: LinearBackend, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=API_URL,
            json=_gql_response({"issues": {"nodes": [self._issue_node(project=None)]}}),
        )
        issue = backend.list_issues()[0]
        assert issue.project_id is None
        assert issue.project_name is None

    def test_single_status_uses_eq(self, backend: LinearBackend, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=API_URL,
            json=_gql_response({"issues": {"nodes": [self._issue_node()]}}),
        )
        backend.list_issues(status="Todo")
        import json
        body = json.loads(httpx_mock.get_requests()[0].content)
        assert body["variables"]["filter"]["state"]["name"]["eq"] == "Todo"

    def test_multi_status_uses_in(self, backend: LinearBackend, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=API_URL,
            json=_gql_response({"issues": {"nodes": [self._issue_node()]}}),
        )
        backend.list_issues(status=["Todo", "Backlog"])
        import json
        body = json.loads(httpx_mock.get_requests()[0].content)
        assert body["variables"]["filter"]["state"]["name"]["in"] == ["Todo", "Backlog"]

    def test_parent_id_filter(self, backend: LinearBackend, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=API_URL,
            json=_gql_response({"issues": {"nodes": [self._issue_node(parent={"id": "parent-1"})]}}),
        )
        backend.list_issues(parent_id="parent-1")
        import json
        body = json.loads(httpx_mock.get_requests()[0].content)
        assert body["variables"]["filter"]["parent"]["id"]["eq"] == "parent-1"

    def test_parent_id_combined_with_status(self, backend: LinearBackend, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=API_URL,
            json=_gql_response({"issues": {"nodes": []}}),
        )
        backend.list_issues(status="Done", parent_id="parent-1")
        import json
        body = json.loads(httpx_mock.get_requests()[0].content)
        assert body["variables"]["filter"]["state"]["name"]["eq"] == "Done"
        assert body["variables"]["filter"]["parent"]["id"]["eq"] == "parent-1"


class TestSaveComment:
    def test_create_comment(self, backend: LinearBackend, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=API_URL,
            json=_gql_response({
                "commentCreate": {
                    "comment": {
                        "id": "c1",
                        "body": "Looks good!",
                        "createdAt": "2026-03-17T10:00:00Z",
                        "issue": {"id": "i1"},
                    }
                }
            }),
        )
        comment = backend.save_comment(issue_id="i1", body="Looks good!")
        assert isinstance(comment, Comment)
        assert comment.id == "c1"
        assert comment.issue_id == "i1"
        assert comment.body == "Looks good!"
        assert comment.created_at == "2026-03-17T10:00:00Z"

    def test_update_comment(self, backend: LinearBackend, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=API_URL,
            json=_gql_response({
                "commentUpdate": {
                    "comment": {
                        "id": "c1",
                        "body": "Updated text",
                        "createdAt": "2026-03-17T10:00:00Z",
                        "issue": {"id": "i1"},
                    }
                }
            }),
        )
        comment = backend.save_comment(id="c1", body="Updated text")
        assert comment.body == "Updated text"


class TestGetIssueWithRelations:
    def test_blocked_by_populated(self, backend: LinearBackend, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=API_URL,
            json=_gql_response({
                "issue": {
                    "id": "i1",
                    "identifier": "ENG-42",
                    "title": "Fix the widget",
                    "description": "Broken",
                    "priority": 2,
                    "url": "https://linear.app/issue/ENG-42",
                    "branchName": None,
                    "state": {"id": "s1", "name": "In Progress", "type": "started"},
                    "project": None,
                    "labels": {"nodes": []},
                    "parent": None,
                    "relations": {
                        "nodes": [
                            {
                                "type": "blocks",
                                "relatedIssue": {"id": "i2", "identifier": "ENG-43", "state": {"type": "started"}},
                            },
                            {
                                "type": "related",
                                "relatedIssue": {"id": "i3", "identifier": "ENG-44", "state": {"type": "started"}},
                            },
                        ]
                    },
                }
            }),
        )
        issue = backend.get_issue("i1", include_relations=True)
        assert issue.blocked_by == ["i2"]

    def test_no_relations(self, backend: LinearBackend, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=API_URL,
            json=_gql_response({
                "issue": {
                    "id": "i1",
                    "identifier": "ENG-42",
                    "title": "Fix the widget",
                    "description": "",
                    "priority": 0,
                    "url": "",
                    "branchName": None,
                    "state": {"id": "s1", "name": "Backlog", "type": "backlog"},
                    "project": None,
                    "labels": {"nodes": []},
                    "parent": None,
                }
            }),
        )
        issue = backend.get_issue("i1", include_relations=False)
        assert issue.blocked_by == []


class TestResolveStateId:
    def test_uuid_passes_through(self, backend: LinearBackend):
        result = backend._resolve_state_id("264dc49d-d819-4d66-8c3a-9025c2386fd8")
        assert result == "264dc49d-d819-4d66-8c3a-9025c2386fd8"

    def test_resolves_name(self, backend: LinearBackend, httpx_mock: HTTPXMock):
        backend._config["team"] = {"id": "t1"}
        httpx_mock.add_response(
            url=API_URL,
            json=_gql_response({
                "workflowStates": {
                    "nodes": [
                        {"id": "s1", "name": "Backlog", "type": "backlog"},
                        {"id": "s2", "name": "In Progress", "type": "started"},
                    ]
                }
            }),
        )
        assert backend._resolve_state_id("In Progress") == "s2"

    def test_case_insensitive(self, backend: LinearBackend, httpx_mock: HTTPXMock):
        backend._config["team"] = {"id": "t1"}
        httpx_mock.add_response(
            url=API_URL,
            json=_gql_response({
                "workflowStates": {"nodes": [{"id": "s1", "name": "Todo", "type": "unstarted"}]}
            }),
        )
        assert backend._resolve_state_id("todo") == "s1"

    def test_unknown_name_raises(self, backend: LinearBackend, httpx_mock: HTTPXMock):
        backend._config["team"] = {"id": "t1"}
        httpx_mock.add_response(
            url=API_URL,
            json=_gql_response({"workflowStates": {"nodes": []}}),
        )
        with pytest.raises(ValueError, match="No workflow state"):
            backend._resolve_state_id("Nonexistent")


class TestResolveLabelId:
    def test_uuid_passes_through(self, backend: LinearBackend):
        result = backend._resolve_label_id("97fd595b-bc14-4e86-8541-64fd6e863517")
        assert result == "97fd595b-bc14-4e86-8541-64fd6e863517"

    def test_resolves_issue_label_name(self, backend: LinearBackend, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=API_URL,
            json=_gql_response({
                "issueLabels": {"nodes": [{"id": "l1", "name": "Claude", "color": "#6366F1"}]}
            }),
        )
        assert backend._resolve_label_id("Claude") == "l1"

    def test_resolves_project_label_name(self, backend: LinearBackend, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=API_URL,
            json=_gql_response({
                "projectLabels": {"nodes": [{"id": "pl1", "name": "Claude Active", "color": "#6366F1"}]}
            }),
        )
        assert backend._resolve_label_id("Claude Active", scope="project") == "pl1"

    def test_unknown_label_raises(self, backend: LinearBackend, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=API_URL,
            json=_gql_response({"issueLabels": {"nodes": []}}),
        )
        with pytest.raises(ValueError, match="No issue label"):
            backend._resolve_label_id("Nonexistent")


class TestResolveProjectId:
    def test_uuid_passes_through(self, backend: LinearBackend):
        result = backend._resolve_project_id("bcbc588f-1127-4691-91a2-881c4ae12a33")
        assert result == "bcbc588f-1127-4691-91a2-881c4ae12a33"

    def test_resolves_name(self, backend: LinearBackend, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=API_URL,
            json=_gql_response({
                "projects": {"nodes": [{"id": "p1", "name": "Claude Plugins", "url": "", "labels": {"nodes": []}}]}
            }),
        )
        assert backend._resolve_project_id("Claude Plugins") == "p1"

    def test_unknown_project_raises(self, backend: LinearBackend, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=API_URL,
            json=_gql_response({"projects": {"nodes": []}}),
        )
        with pytest.raises(ValueError, match="No project matching"):
            backend._resolve_project_id("Nonexistent")


class TestSaveIssueResolution:
    """Test that save_issue resolves names to UUIDs."""

    def test_resolves_state_name(self, backend: LinearBackend, httpx_mock: HTTPXMock):
        backend._config["team"] = {"id": "t1"}
        # First call: resolve state name -> list_statuses
        httpx_mock.add_response(
            url=API_URL,
            json=_gql_response({
                "workflowStates": {"nodes": [{"id": "s1", "name": "Todo", "type": "unstarted"}]}
            }),
        )
        # Second call: the actual mutation
        httpx_mock.add_response(
            url=API_URL,
            json=_gql_response({
                "issueUpdate": {
                    "issue": {
                        "id": "i1", "identifier": "ENG-1", "title": "Test",
                        "description": "", "priority": 0, "url": "", "branchName": None,
                        "state": {"id": "s1", "name": "Todo", "type": "unstarted"},
                        "project": None, "labels": {"nodes": []}, "parent": None,
                    }
                }
            }),
        )
        backend.save_issue(id="i1", state="Todo")
        # Verify the mutation used the UUID
        requests = httpx_mock.get_requests()
        import json
        mutation_body = json.loads(requests[1].content)
        assert mutation_body["variables"]["input"]["stateId"] == "s1"

    def test_uuid_state_skips_resolution(self, backend: LinearBackend, httpx_mock: HTTPXMock):
        # Only one call needed: the mutation (no resolution)
        httpx_mock.add_response(
            url=API_URL,
            json=_gql_response({
                "issueUpdate": {
                    "issue": {
                        "id": "i1", "identifier": "ENG-1", "title": "Test",
                        "description": "", "priority": 0, "url": "", "branchName": None,
                        "state": {"id": "s1", "name": "Todo", "type": "unstarted"},
                        "project": None, "labels": {"nodes": []}, "parent": None,
                    }
                }
            }),
        )
        backend.save_issue(id="i1", state="264dc49d-d819-4d66-8c3a-9025c2386fd8")
        # Only 1 request (no resolution query)
        assert len(httpx_mock.get_requests()) == 1


class TestAuthHeader:
    def test_sends_token_in_header(self, backend: LinearBackend, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=API_URL,
            json=_gql_response({"teams": {"nodes": []}}),
        )
        backend.list_teams()
        request = httpx_mock.get_requests()[0]
        assert request.headers["authorization"] == "test-token"


class TestGraphQLErrors:
    def test_raises_on_graphql_errors(self, backend: LinearBackend, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=API_URL,
            json={"errors": [{"message": "Something went wrong"}]},
        )
        with pytest.raises(RuntimeError, match="GraphQL errors"):
            backend.list_teams()
