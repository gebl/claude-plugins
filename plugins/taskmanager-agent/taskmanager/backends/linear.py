"""Linear GraphQL backend implementation."""

from __future__ import annotations

import os
import re

import httpx

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)

from taskmanager.models import Comment, Document, Issue, Label, Project, ProjectLink, Status, Team, User

API_URL = "https://api.linear.app/graphql"

ISSUE_FIELDS = """
    id identifier title description priority url branchName
    state { id name type }
    project { id name }
    labels { nodes { id name color } }
    parent { id }
"""

ISSUE_FIELDS_WITH_RELATIONS = ISSUE_FIELDS + """
    relations { nodes { relatedIssue { id identifier state { type } } type } }
"""


class LinearBackend:
    """TaskBackend implementation backed by Linear's GraphQL API."""

    def __init__(self, config: dict, token: str | None = None) -> None:
        token_env = config.get("linear", {}).get("token_env", "LINEAR_TOKEN")
        self._token = token or os.environ.get(token_env, "")
        self._config = config

    def _request(self, query: str, variables: dict | None = None) -> dict:
        """Execute a GraphQL request and return the data dict."""
        payload: dict = {"query": query}
        if variables:
            payload["variables"] = variables
        resp = httpx.post(
            API_URL,
            json=payload,
            headers={"Authorization": self._token, "Content-Type": "application/json"},
        )
        resp.raise_for_status()
        body = resp.json()
        if "errors" in body:
            raise RuntimeError(f"GraphQL errors: {body['errors']}")
        return body["data"]

    # ------------------------------------------------------------------
    # Name-to-UUID resolvers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_uuid(value: str) -> bool:
        return bool(_UUID_RE.match(value))

    def _resolve_state_id(self, name_or_id: str, team_id: str | None = None) -> str:
        """Resolve a workflow state name to its UUID, or pass through if already a UUID."""
        if self._is_uuid(name_or_id):
            return name_or_id
        tid = team_id or self._config.get("team", {}).get("id", "")
        if not tid:
            raise ValueError(f"Cannot resolve state '{name_or_id}': no team ID in config")
        statuses = self.list_statuses(tid)
        for s in statuses:
            if s.name.lower() == name_or_id.lower():
                return s.id
        raise ValueError(f"No workflow state matching '{name_or_id}'")

    def _resolve_label_id(self, name_or_id: str, scope: str = "issue") -> str:
        """Resolve a label name to its UUID, or pass through if already a UUID."""
        if self._is_uuid(name_or_id):
            return name_or_id
        labels = self.list_issue_labels() if scope == "issue" else self.list_project_labels()
        for label in labels:
            if label.name.lower() == name_or_id.lower():
                return label.id
        raise ValueError(f"No {scope} label matching '{name_or_id}'")

    def _resolve_label_ids(self, names_or_ids: list[str], scope: str = "issue") -> list[str]:
        """Resolve a list of label names/UUIDs to UUIDs."""
        return [self._resolve_label_id(v, scope) for v in names_or_ids]

    def _resolve_project_id(self, name_or_id: str) -> str:
        """Resolve a project name to its UUID, or pass through if already a UUID."""
        if self._is_uuid(name_or_id):
            return name_or_id
        projects = self.list_projects()
        for p in projects:
            if p.name.lower() == name_or_id.lower():
                return p.id
        raise ValueError(f"No project matching '{name_or_id}'")

    # ------------------------------------------------------------------
    # Teams
    # ------------------------------------------------------------------

    def list_teams(self) -> list[Team]:
        data = self._request("{ teams { nodes { id name key } } }")
        return [Team(id=t["id"], name=t["name"], key=t["key"]) for t in data["teams"]["nodes"]]

    def get_user(self, query: str) -> User:
        if query == "me":
            data = self._request("{ viewer { id name email } }")
            v = data["viewer"]
            return User(id=v["id"], name=v["name"], email=v.get("email", ""))
        data = self._request(
            'query($filter: UserFilter) { users(filter: $filter) { nodes { id name email } } }',
            {"filter": {"displayName": {"containsIgnoreCase": query}}},
        )
        nodes = data["users"]["nodes"]
        if not nodes:
            raise ValueError(f"No user found matching '{query}'")
        u = nodes[0]
        return User(id=u["id"], name=u["name"], email=u.get("email", ""))

    # ------------------------------------------------------------------
    # Statuses
    # ------------------------------------------------------------------

    def list_statuses(self, team_id: str) -> list[Status]:
        data = self._request(
            "query($teamId: ID!) { workflowStates(filter: { team: { id: { eq: $teamId } } }) { nodes { id name type } } }",
            {"teamId": team_id},
        )
        return [Status(id=s["id"], name=s["name"], type=s["type"]) for s in data["workflowStates"]["nodes"]]

    def create_status(self, team_id: str, name: str, type: str, color: str) -> Status:
        data = self._request(
            "mutation($input: WorkflowStateCreateInput!) { workflowStateCreate(input: $input) { workflowState { id name type } } }",
            {"input": {"teamId": team_id, "name": name, "type": type, "color": color}},
        )
        s = data["workflowStateCreate"]["workflowState"]
        return Status(id=s["id"], name=s["name"], type=s["type"])

    # ------------------------------------------------------------------
    # Labels
    # ------------------------------------------------------------------

    def list_issue_labels(self) -> list[Label]:
        data = self._request("{ issueLabels { nodes { id name color } } }")
        return [Label(id=l["id"], name=l["name"], color=l["color"], scope="issue") for l in data["issueLabels"]["nodes"]]

    def create_issue_label(self, name: str, color: str) -> Label:
        data = self._request(
            "mutation($input: IssueLabelCreateInput!) { issueLabelCreate(input: $input) { issueLabel { id name color } } }",
            {"input": {"name": name, "color": color}},
        )
        l = data["issueLabelCreate"]["issueLabel"]
        return Label(id=l["id"], name=l["name"], color=l["color"], scope="issue")

    def list_project_labels(self) -> list[Label]:
        data = self._request("{ projectLabels { nodes { id name color } } }")
        return [Label(id=l["id"], name=l["name"], color=l["color"], scope="project") for l in data["projectLabels"]["nodes"]]

    def create_project_label(self, name: str, color: str, description: str = "") -> Label:
        inp: dict = {"name": name, "color": color}
        if description:
            inp["description"] = description
        data = self._request(
            "mutation($input: ProjectLabelCreateInput!) { projectLabelCreate(input: $input) { projectLabel { id name color } } }",
            {"input": inp},
        )
        l = data["projectLabelCreate"]["projectLabel"]
        return Label(id=l["id"], name=l["name"], color=l["color"], scope="project")

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------

    def list_projects(self, label: str | None = None) -> list[Project]:
        if label:
            query = """
                query($label: String!) {
                    projects(filter: { labels: { name: { eq: $label } } }) {
                        nodes { id name url labels { nodes { id name color } } }
                    }
                }
            """
            data = self._request(query, {"label": label})
        else:
            data = self._request("{ projects { nodes { id name url labels { nodes { id name color } } } } }")
        nodes = data["projects"]["nodes"]
        return [self._parse_project(p) for p in nodes]

    def save_project(self, name: str, team: str, description: str = "", labels: list[str] | None = None) -> Project:
        inp: dict = {"name": name, "teamIds": [team]}
        if description:
            inp["description"] = description
        if labels:
            inp["labelIds"] = self._resolve_label_ids(labels, scope="project")
        data = self._request(
            "mutation($input: ProjectCreateInput!) { projectCreate(input: $input) { project { id name url labels { nodes { id name color } } } } }",
            {"input": inp},
        )
        return self._parse_project(data["projectCreate"]["project"])

    def get_project_links(self, project_id: str) -> list[ProjectLink]:
        data = self._request(
            "query($id: String!) { project(id: $id) { externalLinks { nodes { id label url } } } }",
            {"id": project_id},
        )
        return [
            ProjectLink(id=l["id"], label=l["label"], url=l["url"])
            for l in data["project"]["externalLinks"]["nodes"]
        ]

    def create_project_link(self, project_id: str, label: str, url: str) -> ProjectLink:
        data = self._request(
            'mutation($input: EntityExternalLinkCreateInput!) { entityExternalLinkCreate(input: $input) { entityExternalLink { id label url } } }',
            {"input": {"projectId": project_id, "label": label, "url": url}},
        )
        l = data["entityExternalLinkCreate"]["entityExternalLink"]
        return ProjectLink(id=l["id"], label=l["label"], url=l["url"])

    # ------------------------------------------------------------------
    # Issues
    # ------------------------------------------------------------------

    def list_issues(self, status: str | list[str] | None = None, project: str | None = None) -> list[Issue]:
        filters: dict = {}
        if status:
            if isinstance(status, list):
                filters["state"] = {"name": {"in": [s.replace("_", " ").title() for s in status]}}
            else:
                filters["state"] = {"name": {"eq": status.replace("_", " ").title()}}
        if project:
            filters["project"] = {"name": {"eq": project}}

        if filters:
            query = "query($filter: IssueFilter) { issues(filter: $filter) { nodes { " + ISSUE_FIELDS + " } } }"
            data = self._request(query, {"filter": filters})
        else:
            query = "{ issues { nodes { " + ISSUE_FIELDS + " } } }"
            data = self._request(query)
        return [self._parse_issue(n) for n in data["issues"]["nodes"]]

    def get_issue(self, issue_id: str, include_relations: bool = False) -> Issue:
        fields = ISSUE_FIELDS_WITH_RELATIONS if include_relations else ISSUE_FIELDS
        query = "query($id: String!) { issue(id: $id) { " + fields + " } }"
        data = self._request(query, {"id": issue_id})
        return self._parse_issue(data["issue"], include_relations=include_relations)

    def save_issue(
        self,
        *,
        id: str | None = None,
        title: str | None = None,
        team: str | None = None,
        state: str | None = None,
        labels: list[str] | None = None,
        priority: int | None = None,
        description: str | None = None,
        project: str | None = None,
        parent_id: str | None = None,
        assignee: str | None = None,
        links: list[dict] | None = None,
    ) -> Issue:
        inp: dict = {}
        if title is not None:
            inp["title"] = title
        if team is not None:
            inp["teamId"] = team
        if state is not None:
            inp["stateId"] = self._resolve_state_id(state)
        if labels is not None:
            inp["labelIds"] = self._resolve_label_ids(labels)
        if priority is not None:
            inp["priority"] = priority
        if description is not None:
            inp["description"] = description
        if project is not None:
            inp["projectId"] = self._resolve_project_id(project)
        if parent_id is not None:
            inp["parentId"] = parent_id
        if assignee is not None:
            inp["assigneeId"] = assignee

        if id:
            mutation = "mutation($id: String!, $input: IssueUpdateInput!) { issueUpdate(id: $id, input: $input) { issue { " + ISSUE_FIELDS + " } } }"
            data = self._request(mutation, {"id": id, "input": inp})
            issue = self._parse_issue(data["issueUpdate"]["issue"])
        else:
            mutation = "mutation($input: IssueCreateInput!) { issueCreate(input: $input) { issue { " + ISSUE_FIELDS + " } } }"
            data = self._request(mutation, {"input": inp})
            issue = self._parse_issue(data["issueCreate"]["issue"])

        if links:
            for link in links:
                self._request(
                    'mutation($input: AttachmentCreateInput!) { attachmentCreate(input: $input) { attachment { id } } }',
                    {"input": {"issueId": issue.id, "title": link["label"], "url": link["url"]}},
                )
        return issue

    # ------------------------------------------------------------------
    # Comments
    # ------------------------------------------------------------------

    def list_comments(self, issue_id: str) -> list[Comment]:
        data = self._request(
            "query($id: String!) { issue(id: $id) { comments { nodes { id body createdAt } } } }",
            {"id": issue_id},
        )
        return [
            Comment(id=c["id"], issue_id=issue_id, body=c["body"], created_at=c["createdAt"])
            for c in data["issue"]["comments"]["nodes"]
        ]

    def save_comment(self, *, id: str | None = None, issue_id: str | None = None, body: str) -> Comment:
        if id:
            data = self._request(
                "mutation($id: String!, $input: CommentUpdateInput!) { commentUpdate(id: $id, input: $input) { comment { id body createdAt issue { id } } } }",
                {"id": id, "input": {"body": body}},
            )
            c = data["commentUpdate"]["comment"]
            return Comment(id=c["id"], issue_id=c["issue"]["id"], body=c["body"], created_at=c["createdAt"])
        data = self._request(
            "mutation($input: CommentCreateInput!) { commentCreate(input: $input) { comment { id body createdAt issue { id } } } }",
            {"input": {"issueId": issue_id, "body": body}},
        )
        c = data["commentCreate"]["comment"]
        return Comment(id=c["id"], issue_id=c["issue"]["id"], body=c["body"], created_at=c["createdAt"])

    # ------------------------------------------------------------------
    # Documents
    # ------------------------------------------------------------------

    def create_document(self, title: str, content: str, project: str | None = None) -> Document:
        inp: dict = {"title": title, "content": content}
        if project:
            inp["projectId"] = project
        data = self._request(
            "mutation($input: DocumentCreateInput!) { documentCreate(input: $input) { document { id title url } } }",
            {"input": inp},
        )
        d = data["documentCreate"]["document"]
        return Document(id=d["id"], title=d["title"], url=d.get("url", ""))

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_issue(node: dict, include_relations: bool = False) -> Issue:
        state = node.get("state") or {}
        proj = node.get("project")
        label_nodes = (node.get("labels") or {}).get("nodes", [])
        labels = [Label(id=l["id"], name=l["name"], color=l["color"], scope="issue") for l in label_nodes]

        blocked_by: list[str] = []
        if include_relations:
            for rel in (node.get("relations") or {}).get("nodes", []):
                if rel["type"] == "blocks":
                    blocked_by.append(rel["relatedIssue"]["id"])

        return Issue(
            id=node["id"],
            identifier=node.get("identifier", ""),
            title=node.get("title", ""),
            description=node.get("description", ""),
            status=Status(id=state.get("id", ""), name=state.get("name", ""), type=state.get("type", "")),
            priority=node.get("priority", 0),
            project_id=proj["id"] if proj else None,
            project_name=proj["name"] if proj else None,
            labels=labels,
            parent_id=(node.get("parent") or {}).get("id"),
            blocked_by=blocked_by,
            url=node.get("url", ""),
            branch_name=node.get("branchName"),
        )

    @staticmethod
    def _parse_project(node: dict) -> Project:
        label_nodes = (node.get("labels") or {}).get("nodes", [])
        labels = [Label(id=l["id"], name=l["name"], color=l["color"], scope="project") for l in label_nodes]
        return Project(id=node["id"], name=node["name"], url=node.get("url", ""), labels=labels)
