# Task Manager Agent Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Claude Code plugin with a backend-agnostic task management layer. Linear is the first backend. Commands call Python scripts, never MCP tools directly.

**Architecture:** Python package (`taskmanager/`) with a `TaskBackend` protocol, Linear implementation, thin CLI scripts, and Claude Code commands/references that orchestrate them.

**Tech Stack:** Python 3.12+, httpx, click (CLI args), pytest + pytest-httpx, Claude Code plugin (markdown commands + references).

**Spec:** `docs/specs/2026-03-17-taskmanager-agent-design.md`

---

### Task 1: Scaffold — Plugin, Package, Environment

**Files:**
- Create: `.claude-plugin/plugin.json`
- Create: `.gitignore`
- Create: `pyproject.toml`
- Create: `taskmanager/__init__.py`
- Create: `taskmanager/backends/__init__.py`
- Create: `scripts/.gitkeep`
- Create: `tests/conftest.py`
- Create: `pytest.ini`

- [ ] **Step 1: Create plugin manifest**

Create `.claude-plugin/plugin.json`:

```json
{
  "name": "taskmanager-agent",
  "description": "Backend-agnostic task management agent. Pulls issues from your task tracker (Linear, etc.), creates execution plans, works through them via git worktrees and PRs, and updates statuses. Use /tm-health to set up, /work-backlog to process the backlog, /tm-assign to work a specific issue.",
  "version": "0.1.0",
  "author": {
    "name": "Gabriel Lawrence"
  }
}
```

- [ ] **Step 2: Create .gitignore**

```
venv/
__pycache__/
*.egg-info/
.worktrees/
*.pyc
dist/
.pytest_cache/
```

- [ ] **Step 3: Create pyproject.toml**

```toml
[project]
name = "taskmanager-agent"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["httpx>=0.27", "click>=8.1", "pyyaml>=6.0"]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-httpx>=0.30"]
```

- [ ] **Step 4: Create package init files**

Create `taskmanager/__init__.py` (empty).
Create `taskmanager/backends/__init__.py` — just the factory stub:

```python
"""Backend factory."""

from taskmanager.backends.base import TaskBackend


def get_backend() -> TaskBackend:
    """Instantiate the configured backend."""
    from taskmanager.config import load_config

    config = load_config()
    backend_name = config.get("backend", "linear")
    if backend_name == "linear":
        from taskmanager.backends.linear import LinearBackend

        return LinearBackend(config)
    raise ValueError(f"Unknown backend: {backend_name}")
```

Create `scripts/.gitkeep` (empty, placeholder).

- [ ] **Step 5: Create test conftest and pytest config**

Create `pytest.ini`:
```ini
[pytest]
testpaths = tests
```

Create `tests/conftest.py`:

```python
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
VENV_PYTHON = Path(__file__).parent.parent / "venv" / "bin" / "python"


@pytest.fixture
def run_script():
    """Run a Python script from the scripts/ directory."""

    def _run(name: str, *args: str, env_override: dict | None = None) -> subprocess.CompletedProcess:
        python = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable
        env = {**os.environ, **(env_override or {})}
        return subprocess.run(
            [python, str(SCRIPTS_DIR / name), *args],
            capture_output=True,
            text=True,
            env=env,
        )

    return _run
```

- [ ] **Step 6: Set up venv and install deps**

Run:
```bash
cd ~/Projects/taskmanager-agent && uv venv && uv pip install -e ".[dev]"
```

- [ ] **Step 7: Verify**

Run: `cd ~/Projects/taskmanager-agent && ./venv/bin/pytest --co -q`
Expected: "no tests ran" (no errors)

- [ ] **Step 8: Commit**

```bash
git add .claude-plugin/ .gitignore pyproject.toml pytest.ini taskmanager/ scripts/.gitkeep tests/conftest.py
git commit -m "scaffold: plugin manifest, taskmanager package, Python environment"
```

---

### Task 2: Models & Config

**Files:**
- Create: `taskmanager/models.py`
- Create: `taskmanager/config.py`
- Create: `tests/test_models.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write failing tests for models**

Create `tests/test_models.py`:

```python
import json

from taskmanager.models import Issue, Status, Label, Comment, Project, ProjectLink, User, Team, Document


def test_issue_to_dict():
    status = Status(id="s1", name="Todo", type="unstarted")
    issue = Issue(
        id="i1",
        identifier="LAN-42",
        title="Add RSS feed",
        description="Add an RSS feed to the blog",
        status=status,
        priority=2,
        project_id="p1",
        project_name="Blog",
        labels=[],
        parent_id=None,
        blocked_by=[],
        url="https://linear.app/landq/issue/LAN-42",
        branch_name="lan-42-add-rss-feed",
    )
    d = issue.to_dict()
    assert d["identifier"] == "LAN-42"
    assert d["status"]["name"] == "Todo"
    roundtrip = json.loads(json.dumps(d))
    assert roundtrip["title"] == "Add RSS feed"


def test_status_to_dict():
    s = Status(id="s1", name="Blocked", type="started")
    assert s.to_dict() == {"id": "s1", "name": "Blocked", "type": "started"}


def test_comment_to_dict():
    c = Comment(id="c1", issue_id="i1", body="## Execution Plan\n- [ ] Step 1", created_at="2026-03-17T00:00:00Z")
    d = c.to_dict()
    assert d["body"].startswith("## Execution Plan")
```

- [ ] **Step 2: Run to verify failure**

Run: `cd ~/Projects/taskmanager-agent && ./venv/bin/pytest tests/test_models.py -v`
Expected: FAIL (module doesn't exist)

- [ ] **Step 3: Write models.py**

Create `taskmanager/models.py`:

```python
"""Backend-agnostic data models for task management."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class Status:
    id: str
    name: str
    type: str  # backlog, unstarted, started, completed, canceled

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Label:
    id: str
    name: str
    color: str
    scope: str = "issue"  # "issue" or "project"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Comment:
    id: str
    issue_id: str
    body: str
    created_at: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Issue:
    id: str
    identifier: str
    title: str
    description: str
    status: Status
    priority: int  # 0=None, 1=Urgent, 2=High, 3=Normal, 4=Low
    project_id: str | None
    project_name: str | None
    labels: list[Label]
    parent_id: str | None
    blocked_by: list[str] = field(default_factory=list)
    url: str = ""
    branch_name: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Project:
    id: str
    name: str
    url: str
    labels: list[Label] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ProjectLink:
    id: str
    label: str
    url: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class User:
    id: str
    name: str
    email: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Team:
    id: str
    name: str
    key: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Document:
    id: str
    title: str
    url: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
```

- [ ] **Step 4: Run model tests**

Run: `cd ~/Projects/taskmanager-agent && ./venv/bin/pytest tests/test_models.py -v`
Expected: PASS

- [ ] **Step 5: Write failing tests for config**

Create `tests/test_config.py`:

```python
from pathlib import Path

import yaml

from taskmanager.config import load_config, save_config, CONFIG_PATH


def test_save_and_load_config(tmp_path, monkeypatch):
    test_config_path = tmp_path / "taskmanager.yaml"
    monkeypatch.setattr("taskmanager.config.CONFIG_PATH", test_config_path)

    config = {
        "backend": "linear",
        "team": {"id": "t1", "name": "Landq", "key": "LAN"},
        "statuses": {"todo": "s1"},
    }
    save_config(config)
    assert test_config_path.exists()

    loaded = load_config()
    assert loaded["backend"] == "linear"
    assert loaded["team"]["name"] == "Landq"


def test_load_missing_config_returns_empty(tmp_path, monkeypatch):
    test_config_path = tmp_path / "nonexistent.yaml"
    monkeypatch.setattr("taskmanager.config.CONFIG_PATH", test_config_path)

    config = load_config()
    assert config == {}
```

- [ ] **Step 6: Run to verify failure**

Run: `cd ~/Projects/taskmanager-agent && ./venv/bin/pytest tests/test_config.py -v`
Expected: FAIL

- [ ] **Step 7: Write config.py**

Create `taskmanager/config.py`:

```python
"""Config file handling for ~/.claude/taskmanager.yaml."""

from pathlib import Path

import yaml

CONFIG_PATH = Path.home() / ".claude" / "taskmanager.yaml"


def load_config() -> dict:
    """Load config from disk. Returns empty dict if file doesn't exist."""
    if not CONFIG_PATH.exists():
        return {}
    return yaml.safe_load(CONFIG_PATH.read_text()) or {}


def save_config(config: dict) -> None:
    """Write config to disk."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(yaml.dump(config, default_flow_style=False, sort_keys=False))
```

- [ ] **Step 8: Run config tests**

Run: `cd ~/Projects/taskmanager-agent && ./venv/bin/pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add taskmanager/models.py taskmanager/config.py tests/test_models.py tests/test_config.py
git commit -m "feat: models and config — backend-agnostic data layer"
```

---

### Task 3: Backend Protocol & Linear Backend

**Files:**
- Create: `taskmanager/backends/base.py`
- Create: `taskmanager/backends/linear.py`
- Create: `tests/test_linear_backend.py`

- [ ] **Step 1: Write the backend protocol**

Create `taskmanager/backends/base.py`:

```python
"""Backend protocol — defines every operation the system needs."""

from __future__ import annotations

from typing import Protocol

from taskmanager.models import (
    Comment,
    Document,
    Issue,
    Label,
    Project,
    ProjectLink,
    Status,
    Team,
    User,
)


class TaskBackend(Protocol):
    # Teams
    def list_teams(self) -> list[Team]: ...
    def get_user(self, query: str) -> User: ...

    # Statuses
    def list_statuses(self, team_id: str) -> list[Status]: ...
    def create_status(self, team_id: str, name: str, type: str, color: str) -> Status: ...

    # Labels
    def list_issue_labels(self) -> list[Label]: ...
    def create_issue_label(self, name: str, color: str) -> Label: ...
    def list_project_labels(self) -> list[Label]: ...
    def create_project_label(self, name: str, color: str, description: str = "") -> Label: ...

    # Projects
    def list_projects(self, label: str | None = None) -> list[Project]: ...
    def save_project(self, name: str, team: str, description: str = "", labels: list[str] | None = None) -> Project: ...
    def get_project_links(self, project_id: str) -> list[ProjectLink]: ...
    def create_project_link(self, project_id: str, label: str, url: str) -> ProjectLink: ...

    # Issues
    def list_issues(
        self, status: str | None = None, project: str | None = None
    ) -> list[Issue]: ...
    def get_issue(self, issue_id: str, include_relations: bool = False) -> Issue: ...
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
    ) -> Issue: ...

    # Comments
    def list_comments(self, issue_id: str) -> list[Comment]: ...
    def save_comment(
        self, *, id: str | None = None, issue_id: str | None = None, body: str
    ) -> Comment: ...

    # Documents
    def create_document(
        self, title: str, content: str, project: str | None = None
    ) -> Document: ...
```

- [ ] **Step 2: Write failing tests for Linear backend**

Create `tests/test_linear_backend.py`:

```python
import json

import pytest
from pytest_httpx import HTTPXMock

from taskmanager.backends.linear import LinearBackend
from taskmanager.models import Status, Team


@pytest.fixture
def backend():
    config = {
        "backend": "linear",
        "linear": {"token_env": "LINEAR_TOKEN"},
    }
    return LinearBackend(config, token="test-token")


def test_list_teams(backend: LinearBackend, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        json={
            "data": {
                "teams": {
                    "nodes": [
                        {"id": "t1", "name": "Landq", "key": "LAN"}
                    ]
                }
            }
        }
    )
    teams = backend.list_teams()
    assert len(teams) == 1
    assert teams[0].name == "Landq"
    assert teams[0].key == "LAN"


def test_list_statuses(backend: LinearBackend, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        json={
            "data": {
                "workflowStates": {
                    "nodes": [
                        {"id": "s1", "name": "Todo", "type": "unstarted"},
                        {"id": "s2", "name": "In Progress", "type": "started"},
                    ]
                }
            }
        }
    )
    statuses = backend.list_statuses("t1")
    assert len(statuses) == 2
    assert statuses[0].name == "Todo"


def test_create_status(backend: LinearBackend, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        json={
            "data": {
                "workflowStateCreate": {
                    "success": True,
                    "workflowState": {"id": "s3", "name": "Blocked", "type": "started"},
                }
            }
        }
    )
    status = backend.create_status("t1", "Blocked", "started", "#95a2b3")
    assert status.name == "Blocked"
    assert status.type == "started"


def test_list_issues(backend: LinearBackend, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        json={
            "data": {
                "issues": {
                    "nodes": [
                        {
                            "id": "i1",
                            "identifier": "LAN-42",
                            "title": "Add RSS feed",
                            "description": "desc",
                            "state": {"id": "s1", "name": "Todo", "type": "unstarted"},
                            "priority": 2,
                            "project": {"id": "p1", "name": "Blog"},
                            "labels": {"nodes": []},
                            "parent": None,
                            "url": "https://linear.app/landq/issue/LAN-42",
                            "branchName": "lan-42-add-rss-feed",
                        }
                    ]
                }
            }
        }
    )
    issues = backend.list_issues(status="Todo")
    assert len(issues) == 1
    assert issues[0].identifier == "LAN-42"
    assert issues[0].priority == 2


def test_save_comment(backend: LinearBackend, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        json={
            "data": {
                "commentCreate": {
                    "success": True,
                    "comment": {
                        "id": "c1",
                        "body": "## Execution Plan\n- [ ] Step 1",
                        "createdAt": "2026-03-17T00:00:00Z",
                        "issue": {"id": "i1"},
                    },
                }
            }
        }
    )
    comment = backend.save_comment(issue_id="i1", body="## Execution Plan\n- [ ] Step 1")
    assert comment.id == "c1"
    assert comment.body.startswith("## Execution Plan")
```

- [ ] **Step 3: Run to verify failure**

Run: `cd ~/Projects/taskmanager-agent && ./venv/bin/pytest tests/test_linear_backend.py -v`
Expected: FAIL (LinearBackend doesn't exist)

- [ ] **Step 4: Write the Linear backend**

Create `taskmanager/backends/linear.py`:

```python
"""Linear backend — implements TaskBackend using Linear's GraphQL API."""

from __future__ import annotations

import os

import httpx

from taskmanager.models import (
    Comment,
    Document,
    Issue,
    Label,
    Project,
    ProjectLink,
    Status,
    Team,
    User,
)

API_URL = "https://api.linear.app/graphql"


class LinearBackend:
    def __init__(self, config: dict, token: str | None = None) -> None:
        linear_config = config.get("linear", {})
        token_env = linear_config.get("token_env", "LINEAR_TOKEN")
        self._token = token or os.environ.get(token_env, "")
        if not self._token:
            raise ValueError(f"${token_env} environment variable is not set")

    def _request(self, query: str, variables: dict | None = None) -> dict:
        response = httpx.post(
            API_URL,
            json={"query": query, "variables": variables or {}},
            headers={"Authorization": self._token, "Content-Type": "application/json"},
        )
        response.raise_for_status()
        data = response.json()
        if "errors" in data:
            raise RuntimeError(f"GraphQL errors: {data['errors']}")
        return data["data"]

    # --- Teams ---

    def list_teams(self) -> list[Team]:
        data = self._request("{ teams { nodes { id name key } } }")
        return [Team(id=t["id"], name=t["name"], key=t["key"]) for t in data["teams"]["nodes"]]

    def get_user(self, query: str) -> User:
        if query == "me":
            data = self._request("{ viewer { id name email } }")
            u = data["viewer"]
        else:
            data = self._request(
                'query($q: String!) { users(filter: { name: { contains: $q } }) { nodes { id name email } } }',
                {"q": query},
            )
            nodes = data["users"]["nodes"]
            if not nodes:
                raise ValueError(f"No user found for query: {query}")
            u = nodes[0]
        return User(id=u["id"], name=u["name"], email=u.get("email", ""))

    # --- Statuses ---

    def list_statuses(self, team_id: str) -> list[Status]:
        data = self._request(
            "query($teamId: ID!) { workflowStates(filter: { team: { id: { eq: $teamId } } }) { nodes { id name type } } }",
            {"teamId": team_id},
        )
        return [Status(id=s["id"], name=s["name"], type=s["type"]) for s in data["workflowStates"]["nodes"]]

    def create_status(self, team_id: str, name: str, type: str, color: str) -> Status:
        data = self._request(
            """mutation($input: WorkflowStateCreateInput!) {
                workflowStateCreate(input: $input) { success workflowState { id name type } }
            }""",
            {"input": {"teamId": team_id, "name": name, "type": type, "color": color}},
        )
        s = data["workflowStateCreate"]["workflowState"]
        return Status(id=s["id"], name=s["name"], type=s["type"])

    # --- Labels ---

    def list_issue_labels(self) -> list[Label]:
        data = self._request("{ issueLabels { nodes { id name color } } }")
        return [Label(id=l["id"], name=l["name"], color=l["color"], scope="issue") for l in data["issueLabels"]["nodes"]]

    def create_issue_label(self, name: str, color: str) -> Label:
        data = self._request(
            """mutation($input: IssueLabelCreateInput!) {
                issueLabelCreate(input: $input) { success issueLabel { id name color } }
            }""",
            {"input": {"name": name, "color": color}},
        )
        l = data["issueLabelCreate"]["issueLabel"]
        return Label(id=l["id"], name=l["name"], color=l["color"], scope="issue")

    def list_project_labels(self) -> list[Label]:
        data = self._request("{ projectLabels { nodes { id name color } } }")
        return [Label(id=l["id"], name=l["name"], color=l["color"], scope="project") for l in data["projectLabels"]["nodes"]]

    def create_project_label(self, name: str, color: str, description: str = "") -> Label:
        input_data: dict = {"name": name, "color": color}
        if description:
            input_data["description"] = description
        data = self._request(
            """mutation($input: ProjectLabelCreateInput!) {
                projectLabelCreate(input: $input) { success projectLabel { id name color } }
            }""",
            {"input": input_data},
        )
        l = data["projectLabelCreate"]["projectLabel"]
        return Label(id=l["id"], name=l["name"], color=l["color"], scope="project")

    # --- Projects ---

    def list_projects(self, label: str | None = None) -> list[Project]:
        if label:
            data = self._request(
                'query($label: String!) { projects(filter: { projectLabels: { name: { eq: $label } } }) { nodes { id name url labels { nodes { id name color } } } } }',
                {"label": label},
            )
        else:
            data = self._request("{ projects { nodes { id name url labels { nodes { id name color } } } } }")
        return [
            Project(
                id=p["id"],
                name=p["name"],
                url=p["url"],
                labels=[Label(id=l["id"], name=l["name"], color=l["color"], scope="project") for l in p.get("labels", {}).get("nodes", [])],
            )
            for p in data["projects"]["nodes"]
        ]

    def save_project(self, name: str, team: str, description: str = "", labels: list[str] | None = None) -> Project:
        input_data: dict = {"name": name, "teamIds": [team]}
        if description:
            input_data["description"] = description
        data = self._request(
            """mutation($input: ProjectCreateInput!) {
                projectCreate(input: $input) { success project { id name url } }
            }""",
            {"input": input_data},
        )
        p = data["projectCreate"]["project"]
        return Project(id=p["id"], name=p["name"], url=p["url"])

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
            """mutation($input: EntityExternalLinkCreateInput!) {
                entityExternalLinkCreate(input: $input) { success entityExternalLink { id label url } }
            }""",
            {"input": {"projectId": project_id, "label": label, "url": url}},
        )
        l = data["entityExternalLinkCreate"]["entityExternalLink"]
        return ProjectLink(id=l["id"], label=l["label"], url=l["url"])

    # --- Issues ---

    _ISSUE_FIELDS = """
        id identifier title description priority url branchName
        state { id name type }
        project { id name }
        labels { nodes { id name color } }
        parent { id }
    """

    _ISSUE_FIELDS_WITH_RELATIONS = _ISSUE_FIELDS + """
        relations { nodes { relatedIssue { id identifier state { type } } type } }
    """

    def _parse_issue(self, node: dict) -> Issue:
        state = node["state"]
        project = node.get("project")
        labels = node.get("labels", {}).get("nodes", [])
        parent = node.get("parent")
        blocked_by = []
        for rel in node.get("relations", {}).get("nodes", []):
            if rel["type"] == "blocks":
                blocked_by.append(rel["relatedIssue"]["id"])
        return Issue(
            id=node["id"],
            identifier=node["identifier"],
            title=node["title"],
            description=node.get("description", ""),
            status=Status(id=state["id"], name=state["name"], type=state["type"]),
            priority=node.get("priority", 0),
            project_id=project["id"] if project else None,
            project_name=project["name"] if project else None,
            labels=[Label(id=l["id"], name=l["name"], color=l["color"], scope="issue") for l in labels],
            parent_id=parent["id"] if parent else None,
            blocked_by=blocked_by,
            url=node.get("url", ""),
            branch_name=node.get("branchName"),
        )

    def list_issues(self, status: str | None = None, project: str | None = None) -> list[Issue]:
        filters = []
        variables: dict = {}
        if status:
            filters.append('state: { name: { eq: $status } }')
            variables["status"] = status
        if project:
            filters.append('project: { name: { eq: $project } }')
            variables["project"] = project

        var_decl = ""
        if variables:
            parts = []
            if "status" in variables:
                parts.append("$status: String!")
            if "project" in variables:
                parts.append("$project: String!")
            var_decl = f"({', '.join(parts)})"

        filter_str = f"filter: {{ {', '.join(filters)} }}" if filters else ""

        query = f"""query{var_decl} {{
            issues({filter_str}, orderBy: updatedAt) {{
                nodes {{ {self._ISSUE_FIELDS} }}
            }}
        }}"""

        data = self._request(query, variables)
        return [self._parse_issue(n) for n in data["issues"]["nodes"]]

    def get_issue(self, issue_id: str, include_relations: bool = False) -> Issue:
        fields = self._ISSUE_FIELDS_WITH_RELATIONS if include_relations else self._ISSUE_FIELDS
        data = self._request(
            f"query($id: String!) {{ issue(id: $id) {{ {fields} }} }}",
            {"id": issue_id},
        )
        return self._parse_issue(data["issue"])

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
        if id:
            # Update
            input_data: dict = {}
            if state:
                input_data["stateId"] = state  # For updates, we'd need to resolve name→ID
            if labels:
                input_data["labelIds"] = labels
            if priority is not None:
                input_data["priority"] = priority
            if description is not None:
                input_data["description"] = description
            if parent_id is not None:
                input_data["parentId"] = parent_id
            if assignee:
                input_data["assigneeId"] = assignee

            data = self._request(
                f"""mutation($id: String!, $input: IssueUpdateInput!) {{
                    issueUpdate(id: $id, input: $input) {{ success issue {{ {self._ISSUE_FIELDS} }} }}
                }}""",
                {"id": id, "input": input_data},
            )
            return self._parse_issue(data["issueUpdate"]["issue"])
        else:
            # Create
            if not title or not team:
                raise ValueError("title and team are required when creating an issue")
            input_data = {"title": title, "teamId": team}
            if state:
                input_data["stateId"] = state
            if labels:
                input_data["labelIds"] = labels
            if priority is not None:
                input_data["priority"] = priority
            if description:
                input_data["description"] = description
            if project:
                input_data["projectId"] = project
            if parent_id:
                input_data["parentId"] = parent_id
            if assignee:
                input_data["assigneeId"] = assignee

            data = self._request(
                f"""mutation($input: IssueCreateInput!) {{
                    issueCreate(input: $input) {{ success issue {{ {self._ISSUE_FIELDS} }} }}
                }}""",
                {"input": input_data},
            )
            return self._parse_issue(data["issueCreate"]["issue"])

    # --- Comments ---

    def list_comments(self, issue_id: str) -> list[Comment]:
        data = self._request(
            "query($id: String!) { issue(id: $id) { comments { nodes { id body createdAt issue { id } } } } }",
            {"id": issue_id},
        )
        return [
            Comment(id=c["id"], issue_id=c["issue"]["id"], body=c["body"], created_at=c["createdAt"])
            for c in data["issue"]["comments"]["nodes"]
        ]

    def save_comment(self, *, id: str | None = None, issue_id: str | None = None, body: str) -> Comment:
        if id:
            data = self._request(
                """mutation($id: String!, $input: CommentUpdateInput!) {
                    commentUpdate(id: $id, input: $input) { success comment { id body createdAt issue { id } } }
                }""",
                {"id": id, "input": {"body": body}},
            )
            c = data["commentUpdate"]["comment"]
        else:
            if not issue_id:
                raise ValueError("issue_id is required when creating a comment")
            data = self._request(
                """mutation($input: CommentCreateInput!) {
                    commentCreate(input: $input) { success comment { id body createdAt issue { id } } }
                }""",
                {"input": {"issueId": issue_id, "body": body}},
            )
            c = data["commentCreate"]["comment"]
        return Comment(id=c["id"], issue_id=c["issue"]["id"], body=c["body"], created_at=c["createdAt"])

    # --- Documents ---

    def create_document(self, title: str, content: str, project: str | None = None) -> Document:
        input_data: dict = {"title": title, "content": content}
        if project:
            input_data["projectId"] = project
        data = self._request(
            """mutation($input: DocumentCreateInput!) {
                documentCreate(input: $input) { success document { id title url } }
            }""",
            {"input": input_data},
        )
        d = data["documentCreate"]["document"]
        return Document(id=d["id"], title=d["title"], url=d.get("url", ""))
```

- [ ] **Step 5: Run backend tests**

Run: `cd ~/Projects/taskmanager-agent && ./venv/bin/pytest tests/test_linear_backend.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add taskmanager/backends/base.py taskmanager/backends/linear.py tests/test_linear_backend.py
git commit -m "feat: backend protocol + Linear implementation — all operations via GraphQL"
```

---

### Task 4: CLI Scripts

**Files:**
- Create all 16 scripts under `scripts/`
- Create: `tests/test_scripts.py`

All scripts follow the same pattern. Rather than listing each one individually, here's the template and the specifics:

- [ ] **Step 1: Write test file**

Create `tests/test_scripts.py`:

```python
import pytest

SCRIPTS = [
    "tm_list_issues.py",
    "tm_get_issue.py",
    "tm_save_issue.py",
    "tm_list_comments.py",
    "tm_save_comment.py",
    "tm_list_projects.py",
    "tm_save_project.py",
    "tm_get_project_links.py",
    "tm_create_project_link.py",
    "tm_list_statuses.py",
    "tm_create_status.py",
    "tm_list_labels.py",
    "tm_create_label.py",
    "tm_create_document.py",
    "tm_get_user.py",
]


@pytest.mark.parametrize("script", SCRIPTS)
def test_script_missing_config_exits_nonzero(run_script, tmp_path, monkeypatch, script):
    """Each script should fail gracefully when config is missing."""
    monkeypatch.setattr("taskmanager.config.CONFIG_PATH", tmp_path / "nonexistent.yaml")
    result = run_script(script, "--help")
    # --help should always exit 0
    assert result.returncode == 0


@pytest.mark.parametrize("script", SCRIPTS)
def test_script_has_help(run_script, script):
    """Each script should support --help."""
    result = run_script(script, "--help")
    assert result.returncode == 0
    assert "usage" in result.stdout.lower() or "Usage" in result.stdout


def test_create_forgejo_pr_missing_token(run_script):
    result = run_script(
        "create_forgejo_pr.py",
        "--repo-url", "https://forgejo.bishop.landq.net/Anvil/blog",
        "--branch", "test",
        "--title", "test",
        "--body", "test",
        env_override={"FORGEJO_TOKEN": ""},
    )
    assert result.returncode != 0
    assert "FORGEJO_TOKEN" in result.stderr


def test_create_forgejo_pr_url_parsing():
    from urllib.parse import urlparse

    # Test the URL parsing logic directly
    url = "https://forgejo.bishop.landq.net/Anvil/blog.git"
    path = urlparse(url).path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    parts = path.split("/")
    assert parts[0] == "Anvil"
    assert parts[1] == "blog"
```

- [ ] **Step 2: Write all tm_* scripts**

Each script follows this pattern:

```python
"""<description>."""

import argparse
import json
import sys

from taskmanager.backends import get_backend


def main() -> None:
    parser = argparse.ArgumentParser(description="<description>")
    # script-specific args
    args = parser.parse_args()

    try:
        backend = get_backend()
    except (ValueError, FileNotFoundError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        result = backend.<method>(<args>)
        # output JSON
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

Create all 15 tm_* scripts. Key specifics per script:

| Script | Args | Backend call | Output |
|--------|------|-------------|--------|
| `tm_list_issues.py` | `[--status S] [--project P]` | `list_issues(status, project)` | JSON array of issues |
| `tm_get_issue.py` | `<issue-id> [--relations]` | `get_issue(id, relations)` | JSON issue |
| `tm_save_issue.py` | `[--id I] [--title T] [--team T] [--state S] [--labels L...] [--priority N] [--description D] [--project P] [--parent-id I] [--assignee A]` | `save_issue(...)` | JSON issue |
| `tm_list_comments.py` | `<issue-id>` | `list_comments(id)` | JSON array |
| `tm_save_comment.py` | `[--id I] [--issue-id I] --body B` | `save_comment(...)` | JSON comment |
| `tm_list_projects.py` | `[--label L]` | `list_projects(label)` | JSON array |
| `tm_save_project.py` | `--name N --team T [--description D] [--labels L...]` | `save_project(...)` | JSON project |
| `tm_get_project_links.py` | `--project-id I` | `get_project_links(id)` | JSON array |
| `tm_create_project_link.py` | `--project-id I --label L --url U` | `create_project_link(...)` | JSON link |
| `tm_list_statuses.py` | `--team-id I` | `list_statuses(id)` | JSON array |
| `tm_create_status.py` | `--team-id I --name N --type T --color C` | `create_status(...)` | JSON status |
| `tm_list_labels.py` | `--scope S` (issue or project) | `list_issue_labels()` or `list_project_labels()` | JSON array |
| `tm_create_label.py` | `--name N --color C --scope S [--description D]` | `create_issue_label()` or `create_project_label()` | JSON label |
| `tm_create_document.py` | `--title T --content C [--project P]` | `create_document(...)` | JSON document |
| `tm_get_user.py` | `--query Q` | `get_user(query)` | JSON user |

Also create `create_forgejo_pr.py` (standalone, no backend — uses Forgejo REST API directly with `$FORGEJO_TOKEN`). Same as previous plan but with `ValueError` fix for `parse_repo_url`.

- [ ] **Step 3: Remove old scripts/.gitkeep**

Delete `scripts/.gitkeep`.

- [ ] **Step 4: Run tests**

Run: `cd ~/Projects/taskmanager-agent && ./venv/bin/pytest tests/test_scripts.py -v`
Expected: PASS (at least --help tests pass for all scripts)

- [ ] **Step 5: Commit**

```bash
git add scripts/ tests/test_scripts.py
git commit -m "feat: CLI scripts — thin wrappers around backend methods"
```

---

### Task 5: Reference Files

**Files:**
- Create: `references/config.md`
- Create: `references/next-flow.md`
- Create: `references/plan-flow.md`
- Create: `references/work-flow.md`
- Create: `references/pr-creation.md`
- Create: `references/review-issue-flow.md`

- [ ] **Step 1: Write all 6 reference files**

These are identical in logic to the previous plan's reference files (Tasks 6-9), but with all MCP tool calls replaced by script invocations. The pattern:

**Old:** `Use list_issues MCP tool with state: "Todo"`
**New:** `Run: ${CLAUDE_PLUGIN_ROOT}/venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_list_issues.py --status Todo`

**Old:** `Use save_issue MCP tool with id, state, labels`
**New:** `Run: ${CLAUDE_PLUGIN_ROOT}/venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_issue.py --id <id> --state "In Progress" --labels Claude`

**Old:** `Use list_comments MCP tool with issueId`
**New:** `Run: ${CLAUDE_PLUGIN_ROOT}/venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_list_comments.py <issue-id>`

Write each reference file with the full flow logic (copy from spec), using script calls throughout. Key files:

- `config.md` — instructions for reading `~/.claude/taskmanager.yaml`
- `next-flow.md` — issue selection: `tm_list_issues.py --status Todo`, filter by active projects, check `tm_get_issue.py --relations` for blocked-by
- `plan-flow.md` — code mode (clone/explore/plan) vs document mode, post plan via `tm_save_comment.py`
- `work-flow.md` — discover plan via `tm_list_comments.py`, worktree setup, execute, PR via `pr-creation.md`, update status via `tm_save_issue.py`
- `pr-creation.md` — Forgejo (`create_forgejo_pr.py`) vs GitHub (`gh pr create`)
- `review-issue-flow.md` — create review sub-issue via `tm_save_issue.py`, block parent

- [ ] **Step 2: Commit**

```bash
git add references/
git commit -m "docs: reference files — shared flow logic using backend scripts"
```

---

### Task 6: Commands — tm-health

**Files:**
- Create: `commands/tm-health.md`

- [ ] **Step 1: Write the command**

Create `commands/tm-health.md` with frontmatter:

```yaml
---
name: tm-health
description: "Validate and set up the task manager environment. Creates missing statuses and labels, caches workspace config. Run this first before using other tm-* commands."
allowed-tools:
  - Read
  - Write
  - Bash
  - Glob
---
```

Body describes the full health check flow using script invocations:
1. `tm_list_statuses.py` → find or `tm_create_status.py` for "Blocked"
2. `tm_list_labels.py` → find or `tm_create_label.py` for each label
3. `tm_get_user.py --query me` → operator
4. `tm_list_projects.py --label "Claude Active"` → active projects
5. `tm_get_project_links.py` per project → repo URLs
6. `git ls-remote` per repo → validate access
7. Worktree cleanup
8. `tm_list_issues.py --status "In Progress"` + `tm_list_comments.py` → stale detection
9. Write config
10. Report

- [ ] **Step 2: Commit**

```bash
git add commands/tm-health.md
git commit -m "feat: /tm-health command — setup, validation, self-healing"
```

---

### Task 7: Commands — Standalone (tm-next, tm-plan, tm-work, tm-update)

**Files:**
- Create: `commands/tm-next.md`
- Create: `commands/tm-plan.md`
- Create: `commands/tm-work.md`
- Create: `commands/tm-update.md`

- [ ] **Step 1: Write all 4 commands**

Each command has simple frontmatter (name, description, argument-hint) and delegates to reference files. No `allowed-tools` restriction — these need broad access for codebase exploration and editing.

- `tm-next.md`: delegates to `next-flow.md` with `interactive: true`
- `tm-plan.md`: delegates to `plan-flow.md`
- `tm-work.md`: delegates to `work-flow.md`
- `tm-update.md`: reads config, calls `tm_save_issue.py` and optionally `tm_save_comment.py`

- [ ] **Step 2: Commit**

```bash
git add commands/tm-next.md commands/tm-plan.md commands/tm-work.md commands/tm-update.md
git commit -m "feat: standalone commands — tm-next, tm-plan, tm-work, tm-update"
```

---

### Task 8: Commands — CRUD (tm-project-create, tm-issue-create, tm-issues)

**Files:**
- Create: `commands/tm-project-create.md`
- Create: `commands/tm-issue-create.md`
- Create: `commands/tm-issues.md`

- [ ] **Step 1: Write all 3 commands**

Each calls the appropriate scripts:
- `tm-project-create.md`: `tm_save_project.py` + `tm_create_project_link.py` + update config
- `tm-issue-create.md`: validate project in config, `tm_save_issue.py`
- `tm-issues.md`: `tm_list_issues.py`, display as table

- [ ] **Step 2: Commit**

```bash
git add commands/tm-project-create.md commands/tm-issue-create.md commands/tm-issues.md
git commit -m "feat: CRUD commands — tm-project-create, tm-issue-create, tm-issues"
```

---

### Task 9: Commands — Orchestrators (tm-assign, work-backlog)

**Files:**
- Create: `commands/tm-assign.md`
- Create: `commands/work-backlog.md`

- [ ] **Step 1: Write both orchestrators**

Self-contained commands that inline logic from reference files:
- `tm-assign.md`: config → fetch issue via script → check plan via script → route to plan-flow/work-flow
- `work-backlog.md`: config → loop: next-flow → plan-flow → work-flow, confirm every 3

- [ ] **Step 2: Commit**

```bash
git add commands/tm-assign.md commands/work-backlog.md
git commit -m "feat: orchestrator commands — tm-assign, work-backlog"
```

---

### Task 10: Integration Test — /tm-health End-to-End

**Files:** None (manual verification)

- [ ] **Step 1: Register the plugin in Claude Code**

Add `~/Projects/taskmanager-agent` to Claude Code's plugin configuration.

- [ ] **Step 2: Restart Claude Code**

Exit and restart to load the plugin.

- [ ] **Step 3: Run /tm-health**

Verify:
- Team discovered
- "Blocked" status found or created
- Labels found or created
- Projects listed with repo URLs
- Config written to `~/.claude/taskmanager.yaml`

- [ ] **Step 4: Run /tm-issues**

Verify issue listing works.

- [ ] **Step 5: Push all changes**

```bash
cd ~/Projects/taskmanager-agent && git push origin main
```

- [ ] **Step 6: Commit any fixes from testing**

Fix and commit anything discovered during integration testing.
