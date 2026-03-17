# Task Manager Agent for Claude Code

**Date:** 2026-03-17
**Status:** Approved
**Supersedes:** `2026-03-16-linear-agent-design.md`

## Overview

A Claude Code plugin that pulls tasks from a task management backend, plans and executes work, and updates progress. Supports code tasks (git worktree + PR) and non-code tasks (documents). All backend communication goes through a Python package with a pluggable backend protocol — Linear is the first implementation, but Jira, GitHub Issues, etc. can be added without changing commands or references.

## Goals

- Pull the next highest-priority "Todo" issue
- Create a plan, post it as a comment, check off items as work progresses
- For code tasks: create a git worktree, do the work, submit a PR
- For non-code tasks: produce documents or comments
- Create sub-issues for discovered out-of-scope work (max 1 level deep)
- Create review issues assigned to the user when human input is needed
- Update statuses throughout the lifecycle
- Self-healing setup via `/tm-health`
- Backend-agnostic: commands and references never reference Linear directly

## Architecture

### Layered Design

```
┌─────────────────────────────────────────────────┐
│  Claude Code Commands (markdown)                │
│  /tm-health, /tm-next, /work-backlog, etc.      │
├─────────────────────────────────────────────────┤
│  Reference Files (markdown)                     │
│  config.md, next-flow.md, plan-flow.md, etc.    │
├─────────────────────────────────────────────────┤
│  CLI Scripts (Python)                           │
│  tm_list_issues.py, tm_save_issue.py, etc.      │
├─────────────────────────────────────────────────┤
│  taskmanager Python Package                     │
│  models.py, config.py, backends/base.py         │
├─────────────────────────────────────────────────┤
│  Backend Implementation                         │
│  backends/linear.py (GraphQL API)               │
│  Future: backends/jira.py, backends/github.py   │
└─────────────────────────────────────────────────┘
```

- **Commands** describe workflows in markdown, invoke scripts via Bash
- **References** contain shared flow logic, also invoke scripts via Bash
- **Scripts** are thin CLI wrappers — parse args, call backend, output JSON
- **Package** contains the backend protocol, models, and implementations
- **No MCP dependency** — everything goes through the Python package

### Backend Protocol

The `TaskBackend` protocol defines every operation the system needs. Each backend implements this protocol. Scripts instantiate the configured backend and call one method.

### Config File

`~/.claude/taskmanager.yaml` — specifies which backend to use, caches IDs, stores project mappings.

```yaml
backend: linear  # or "jira", "github", etc.

# Backend-specific config
linear:
  token_env: LINEAR_TOKEN  # env var name holding the API token

team:
  id: <uuid>
  name: Landq
  key: LAN

statuses:
  backlog: <uuid>
  todo: <uuid>
  in_progress: <uuid>
  in_review: <uuid>
  done: <uuid>
  blocked: <uuid>

labels:
  issue:
    claude: <uuid>
    review: <uuid>
  project:
    claude_active: <uuid>

operator:
  id: <uuid>
  name: Gabriel Lawrence

projects:
  blog-publication-pipeline:
    id: <uuid>
    repo: https://forgejo.bishop.landq.net/anvil/blog
    local_path: ~/Projects/blog
  overland-buildout:
    id: <uuid>
    repo: null

clone_base: ~/Projects
stale_threshold_hours: 4
last_health_check: 2026-03-17T10:00:00Z
```

## Status Flow

```
Backlog → Todo → In Progress → In Review → Done
                           ↘ Blocked
```

- **Backlog**: Unrefined work, not yet ready
- **Todo**: Available to pick up
- **In Progress**: Actively being worked on
- **In Review**: PR created or document produced, waiting for human review
- **Blocked**: Can't proceed — comment explains why
- **Done**: Completed (set by human)

## Labels & Statuses (auto-created by `/tm-health`)

All required structures are created automatically:

- **"Blocked" status** (type: started) — via `tm_create_status.py`
- **"Claude Active" project label** — via `tm_create_label.py --scope project`
- **"Review" issue label** — via `tm_create_label.py --scope issue`
- **"Claude" issue label** — via `tm_create_label.py --scope issue`

## Project Repo Convention

Each project that involves code should have a link resource with label "Repository" pointing to its git repo URL. This is the source of truth — the config caches it.

- Set via `/tm-project-create --repo <url>` (calls `tm_create_project_link.py`)
- Read via `tm_get_project_links.py`
- Projects without a "Repository" link are non-code (document mode)

## Issue Pull Logic

1. Query all issues with status "Todo", ordered by priority (Urgent > High > Normal > Low)
2. Filter to projects labeled "Claude Active"
3. Skip issues blocked by unfinished issues
4. Optionally filter by project name
5. Take the top one

## Plugin Directory Structure

```
taskmanager-agent/
├── .claude-plugin/
│   └── plugin.json
├── pyproject.toml
├── taskmanager/                         # Python package
│   ├── __init__.py
│   ├── models.py                        # Issue, Project, Comment, Status, Label, Document
│   ├── config.py                        # Read/write ~/.claude/taskmanager.yaml
│   └── backends/
│       ├── __init__.py                  # get_backend() factory
│       ├── base.py                      # TaskBackend protocol
│       └── linear.py                    # Linear GraphQL implementation
├── scripts/                             # CLI entry points (one per operation)
│   ├── tm_list_issues.py
│   ├── tm_get_issue.py
│   ├── tm_save_issue.py
│   ├── tm_list_comments.py
│   ├── tm_save_comment.py
│   ├── tm_list_projects.py
│   ├── tm_save_project.py
│   ├── tm_get_project_links.py
│   ├── tm_create_project_link.py
│   ├── tm_list_statuses.py
│   ├── tm_create_status.py
│   ├── tm_list_labels.py
│   ├── tm_create_label.py
│   ├── tm_create_document.py
│   ├── tm_get_user.py
│   └── create_forgejo_pr.py             # Git-host specific (not backend-abstracted)
├── commands/
│   ├── tm-health.md
│   ├── tm-next.md
│   ├── tm-plan.md
│   ├── tm-work.md
│   ├── tm-assign.md
│   ├── tm-update.md
│   ├── tm-project-create.md
│   ├── tm-issue-create.md
│   ├── tm-issues.md
│   └── work-backlog.md
├── references/
│   ├── config.md
│   ├── next-flow.md
│   ├── plan-flow.md
│   ├── work-flow.md
│   ├── pr-creation.md
│   └── review-issue-flow.md
├── tests/
│   ├── conftest.py
│   ├── test_models.py
│   ├── test_config.py
│   ├── test_linear_backend.py
│   └── test_scripts.py
└── docs/
    └── specs/
```

## Python Package: `taskmanager`

### `taskmanager/models.py`

Backend-agnostic data models:

```python
from dataclasses import dataclass

@dataclass
class Status:
    id: str
    name: str
    type: str  # backlog, unstarted, started, completed, canceled

@dataclass
class Label:
    id: str
    name: str
    color: str
    scope: str  # "issue" or "project"

@dataclass
class Comment:
    id: str
    issue_id: str
    body: str
    created_at: str

@dataclass
class Issue:
    id: str
    identifier: str      # e.g., "LAN-42"
    title: str
    description: str
    status: Status
    priority: int         # 0=None, 1=Urgent, 2=High, 3=Normal, 4=Low
    project_id: str | None
    project_name: str | None
    labels: list[Label]
    parent_id: str | None
    blocked_by: list[str]  # issue IDs
    url: str
    branch_name: str | None  # suggested git branch name

@dataclass
class Project:
    id: str
    name: str
    url: str
    labels: list[Label]

@dataclass
class ProjectLink:
    id: str
    label: str
    url: str

@dataclass
class User:
    id: str
    name: str
    email: str

@dataclass
class Team:
    id: str
    name: str
    key: str

@dataclass
class Document:
    id: str
    title: str
    url: str
```

### `taskmanager/backends/base.py`

```python
from typing import Protocol
from taskmanager.models import *

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
    def list_issues(self, status: str | None = None, project: str | None = None, priority: int | None = None) -> list[Issue]: ...
    def get_issue(self, issue_id: str, include_relations: bool = False) -> Issue: ...
    def save_issue(self, *, id: str | None = None, title: str | None = None, team: str | None = None,
                   state: str | None = None, labels: list[str] | None = None,
                   priority: int | None = None, description: str | None = None,
                   project: str | None = None, parent_id: str | None = None,
                   assignee: str | None = None, links: list[dict] | None = None) -> Issue: ...

    # Comments
    def list_comments(self, issue_id: str) -> list[Comment]: ...
    def save_comment(self, *, id: str | None = None, issue_id: str | None = None, body: str) -> Comment: ...

    # Documents
    def create_document(self, title: str, content: str, project: str | None = None) -> Document: ...
```

### `taskmanager/backends/linear.py`

Implements `TaskBackend` using Linear's GraphQL API. All Linear-specific logic lives here:
- GraphQL queries and mutations
- Linear-specific field mapping (e.g., priority values, state types)
- Authentication via `$LINEAR_TOKEN`
- Uses `httpx` for HTTP

### `taskmanager/backends/__init__.py`

Factory function:

```python
from taskmanager.config import load_config

def get_backend() -> TaskBackend:
    config = load_config()
    backend_name = config.get("backend", "linear")
    if backend_name == "linear":
        from taskmanager.backends.linear import LinearBackend
        return LinearBackend()
    raise ValueError(f"Unknown backend: {backend_name}")
```

### `taskmanager/config.py`

Read/write `~/.claude/taskmanager.yaml`. Used by both scripts and the backend factory.

## CLI Scripts

Each script follows this pattern:

```python
"""<description>"""
import argparse, json, sys
from taskmanager.backends import get_backend

def main():
    parser = argparse.ArgumentParser(description="...")
    # add args
    args = parser.parse_args()
    backend = get_backend()
    result = backend.<method>(args...)
    print(json.dumps(result.to_dict()))  # or dataclasses.asdict()

if __name__ == "__main__":
    main()
```

### Script inventory

| Script | Backend method | Purpose |
|--------|---------------|---------|
| `tm_list_issues.py` | `list_issues()` | Query issues by status/project |
| `tm_get_issue.py` | `get_issue()` | Get issue with optional relations |
| `tm_save_issue.py` | `save_issue()` | Create or update an issue |
| `tm_list_comments.py` | `list_comments()` | List comments on an issue |
| `tm_save_comment.py` | `save_comment()` | Create or update a comment |
| `tm_list_projects.py` | `list_projects()` | List projects, optionally by label |
| `tm_save_project.py` | `save_project()` | Create a project |
| `tm_get_project_links.py` | `get_project_links()` | Read link resources from a project |
| `tm_create_project_link.py` | `create_project_link()` | Add a link resource to a project |
| `tm_list_statuses.py` | `list_statuses()` | List workflow statuses for a team |
| `tm_create_status.py` | `create_status()` | Create a workflow status |
| `tm_list_labels.py` | `list_issue_labels()` / `list_project_labels()` | List labels |
| `tm_create_label.py` | `create_issue_label()` / `create_project_label()` | Create a label |
| `tm_create_document.py` | `create_document()` | Create a document |
| `tm_get_user.py` | `get_user()` | Get user info |
| `create_forgejo_pr.py` | (direct REST) | Create a Forgejo PR — not backend-abstracted |

### Script conventions

- All scripts output JSON to stdout, errors to stderr
- All scripts exit 0 on success, non-zero on error
- No interactive prompts
- Backend is resolved automatically from config via `get_backend()`
- Token env vars are backend-specific (Linear uses `$LINEAR_TOKEN`)

## Command Suite

Commands invoke scripts via `Bash("${CLAUDE_PLUGIN_ROOT}/venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/<script>.py ...")`. They never reference a specific backend.

### `/tm-health`

**Purpose:** Setup validation, cache refresh, and full self-healing.

**Actions:**
1. Discover team via `tm_list_statuses.py` (implicitly validates connection)
2. List and create missing statuses via `tm_list_statuses.py` / `tm_create_status.py`
3. List and create missing labels via `tm_list_labels.py` / `tm_create_label.py`
4. Get operator info via `tm_get_user.py --query me`
5. List active projects via `tm_list_projects.py --label "Claude Active"`
6. Read project links via `tm_get_project_links.py` for each project
7. Validate git access to repo URLs (`git ls-remote`)
8. Clean up merged worktrees
9. Detect stale "In Progress" issues via `tm_list_issues.py --status "In Progress"` + `tm_list_comments.py`
10. Write config to `~/.claude/taskmanager.yaml`
11. Report summary

### `/tm-project-create <name> [--repo <url>] [--description <text>]`

**Purpose:** Create a new project and mark it active.

1. `tm_save_project.py --name <name> --team <team> --labels "Claude Active" [--description <text>]`
2. If `--repo`: `tm_create_project_link.py --project-id <id> --label "Repository" --url <url>`
3. Update config with new project entry

### `/tm-issue-create <title> --project <name> [--priority <level>] [--description <text>]`

**Purpose:** Create a new issue in an active project.

1. Validate project is active (in config)
2. `tm_save_issue.py --title <title> --team <team> --project <name> --state Todo --priority <n> [--description <text>]`

### `/tm-issues [--project <name>] [--status <status>]`

**Purpose:** Show issues from active projects.

1. `tm_list_issues.py [--project <name>] [--status <status>]` (defaults to Todo + Backlog)
2. Display as a table: ID, title, priority, project, status

### `/tm-assign <issue-id>`

**Purpose:** Point Claude at a specific issue and begin working on it.

Self-contained orchestrator using shared references:
1. Read config per `${CLAUDE_PLUGIN_ROOT}/references/config.md`
2. Fetch issue via `tm_get_issue.py`, validate it's in an active project
3. `tm_save_issue.py` — apply "Claude" label, set status "In Progress"
4. Check for plan comment via `tm_list_comments.py`
5. Route:
   - No plan → follow `plan-flow.md` then `work-flow.md`
   - Plan with unchecked items → follow `work-flow.md`
   - Plan fully checked → set "In Review", post summary

### `/tm-next [--project <name>]`

**Purpose:** Pull the next issue (interactive).

1. Follow `next-flow.md` with `interactive: true`
2. On confirm: apply "Claude" label, set "In Progress"

### `/tm-plan <issue-id>`

**Purpose:** Create an execution plan for an issue.

Follow `plan-flow.md`.

### `/tm-work <issue-id>`

**Purpose:** Execute the plan for an issue.

Follow `work-flow.md`.

### `/tm-update <issue-id> <status> [--comment <message>]`

**Purpose:** Manual status update.

1. `tm_save_issue.py --id <issue-id> --state <status>`
2. If comment: `tm_save_comment.py --issue-id <issue-id> --body <message>`

### `/work-backlog [--project <name>] [--limit <n>]`

**Purpose:** Autonomous backlog processing loop.

Self-contained orchestrator:
1. Read config, validate freshness
2. Loop: `next-flow.md` → `plan-flow.md` → `work-flow.md`
3. Confirm every 3 issues
4. Summary on exit

## Reference Files

References are identical to the previous spec except all MCP tool calls are replaced with script invocations. For example:

**Old (MCP):** `Use list_issues MCP tool with state: "Todo"`
**New (script):** `Run: tm_list_issues.py --status Todo`

**Old (MCP):** `Use save_issue MCP tool with id, state, labels`
**New (script):** `Run: tm_save_issue.py --id <id> --state "In Progress" --labels Claude`

The reference file content otherwise remains the same. See the previous spec for full flow details:
- `config.md` — config read/write
- `next-flow.md` — issue selection logic
- `plan-flow.md` — planning (code mode + document mode)
- `work-flow.md` — execution (worktree + PR or document)
- `pr-creation.md` — Forgejo/GitHub PR creation
- `review-issue-flow.md` — creating review sub-issues

### Plan Comment Convention

Same as before: `## Execution Plan` heading as first line, checklist items as `- [ ]` / `- [x]`.

## Edge Cases & Guardrails

All unchanged from previous spec:
- Stale In-Progress detection (configurable threshold)
- Dependency awareness (skip blocked issues)
- Sub-issue depth limit (max 1 level)
- Plan comment convention
- Worktree cleanup
- Repo cloning
- Error recovery
- Concurrency (loose lock via status update)

## v2 Considerations

- `/tm-revise <issue-id>`: Handle PR review feedback
- Smart resume: pick up mid-checklist
- Configurable sub-issue depth
- Token/cost budget tracking
- Cron-based autonomous mode
- Multiple team support
- Additional backends: Jira, GitHub Issues, GitLab Issues

## Implementation Notes

**Python package:** `taskmanager/` with `httpx` for HTTP. Installed as editable (`uv pip install -e ".[dev]"`).

**Environment variables:**
- `$LINEAR_TOKEN` — Linear API key (backend-specific)
- `$FORGEJO_TOKEN` — Forgejo API key (for PR creation)

**Testing:** `pytest` with `pytest-httpx` for mocking HTTP. Tests cover:
- Models (serialization/deserialization)
- Config (read/write/validation)
- Linear backend (mocked HTTP, verify GraphQL queries)
- Scripts (CLI arg parsing, token validation)

The plugin lives at `~/Projects/taskmanager-agent` and is registered in Claude Code's plugin config.
