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
