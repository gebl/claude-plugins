# Linear Agent Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Claude Code plugin that pulls tasks from Linear, plans and executes work, and updates Linear with progress.

**Architecture:** Composable command suite with shared reference files. Python scripts handle Linear GraphQL API operations not covered by the MCP plugin. Commands are markdown files with YAML frontmatter that reference shared flow docs.

**Tech Stack:** Claude Code plugin (markdown commands + references), Python 3.12+ with httpx (scripts), Linear MCP plugin, Forgejo REST API, git worktrees.

**Spec:** `docs/specs/2026-03-16-linear-agent-design.md`

---

### Task 1: Plugin Scaffold & Python Environment

**Files:**
- Create: `.claude-plugin/plugin.json`
- Create: `pyproject.toml`
- Create: `scripts/__init__.py` (empty, for test imports)

- [ ] **Step 1: Create plugin manifest**

Create `.claude-plugin/plugin.json`:

```json
{
  "name": "linear-agent",
  "description": "Linear-driven task execution agent. Pulls issues from Linear backlog, creates execution plans, works through them (code via git worktrees + PRs, non-code via Linear documents), and updates Linear statuses. Use /linear-health to set up, /work-backlog to process the backlog, /linear-assign to work a specific issue.",
  "version": "0.1.0",
  "author": {
    "name": "Gabriel Lawrence"
  }
}
```

- [ ] **Step 2: Create pyproject.toml for scripts**

```toml
[project]
name = "linear-agent-scripts"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["httpx>=0.27"]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-httpx>=0.30"]
```

- [ ] **Step 3: Set up venv and install deps**

Run:
```bash
cd ~/Projects/linear-agent && uv venv && uv pip install -e ".[dev]"
```

- [ ] **Step 4: Create .gitignore**

Create `.gitignore`:
```
venv/
__pycache__/
*.egg-info/
.worktrees/
*.pyc
dist/
```

- [ ] **Step 5: Create empty init file and test conftest**

Create `scripts/__init__.py` (empty file).

Create `tests/conftest.py`:

```python
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"


@pytest.fixture
def run_script():
    """Run a Python script from the scripts/ directory."""

    def _run(name: str, *args: str, env_override: dict | None = None) -> subprocess.CompletedProcess:
        env = {**os.environ, **(env_override or {})}
        return subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / name), *args],
            capture_output=True,
            text=True,
            env=env,
        )

    return _run
```

- [ ] **Step 6: Create pytest config**

Create `pytest.ini`:
```ini
[pytest]
testpaths = tests
```

- [ ] **Step 6: Verify setup**

Run: `cd ~/Projects/linear-agent && ./venv/bin/pytest --co -q`
Expected: "no tests ran" (no errors)

- [ ] **Step 7: Commit**

```bash
git add .claude-plugin/ pyproject.toml pytest.ini scripts/__init__.py tests/conftest.py .gitignore
git commit -m "scaffold: plugin manifest, Python environment, pytest config"
```

---

### Task 2: Python Script — create_workflow_state.py

**Files:**
- Create: `scripts/create_workflow_state.py`
- Create: `tests/test_create_workflow_state.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_create_workflow_state.py`:

```python
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = str(Path(__file__).parent.parent / "scripts" / "create_workflow_state.py")


def run_script(*args: str, env_override: dict | None = None) -> subprocess.CompletedProcess:
    import os

    env = {**os.environ, **(env_override or {})}
    return subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True,
        text=True,
        env=env,
    )


def test_missing_token_exits_nonzero():
    result = run_script(
        "--team-id", "fake-uuid",
        "--name", "Blocked",
        "--type", "started",
        "--color", "#95a2b3",
        env_override={"LINEAR_TOKEN": ""},
    )
    assert result.returncode != 0
    assert "LINEAR_TOKEN" in result.stderr


def test_missing_required_args_exits_nonzero():
    result = run_script(env_override={"LINEAR_TOKEN": "fake"})
    assert result.returncode != 0


def test_valid_args_are_parsed():
    """Verify the script at least parses args without crashing on bad token."""
    result = run_script(
        "--team-id", "fake-uuid",
        "--name", "Blocked",
        "--type", "started",
        "--color", "#95a2b3",
        env_override={"LINEAR_TOKEN": "fake-token"},
    )
    # Will fail on API call, but should NOT fail on arg parsing
    assert "LINEAR_TOKEN" not in result.stderr or result.returncode != 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/Projects/linear-agent && ./venv/bin/pytest tests/test_create_workflow_state.py -v`
Expected: FAIL (script doesn't exist)

- [ ] **Step 3: Write the implementation**

Create `scripts/create_workflow_state.py`:

```python
"""Create a workflow state (status) on a Linear team via GraphQL API."""

import argparse
import json
import os
import sys

import httpx

API_URL = "https://api.linear.app/graphql"

MUTATION = """
mutation WorkflowStateCreate($input: WorkflowStateCreateInput!) {
  workflowStateCreate(input: $input) {
    success
    workflowState {
      id
      name
      type
    }
  }
}
"""


def main() -> None:
    token = os.environ.get("LINEAR_TOKEN", "")
    if not token:
        print("Error: LINEAR_TOKEN environment variable is not set", file=sys.stderr)
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Create a Linear workflow state")
    parser.add_argument("--team-id", required=True, help="Team UUID")
    parser.add_argument("--name", required=True, help="State name")
    parser.add_argument("--type", required=True, choices=["backlog", "unstarted", "started", "completed", "canceled"])
    parser.add_argument("--color", required=True, help="Hex color (e.g., #95a2b3)")
    parser.add_argument("--description", default="", help="State description")
    args = parser.parse_args()

    variables = {
        "input": {
            "teamId": args.team_id,
            "name": args.name,
            "type": args.type,
            "color": args.color,
        }
    }
    if args.description:
        variables["input"]["description"] = args.description

    response = httpx.post(
        API_URL,
        json={"query": MUTATION, "variables": variables},
        headers={"Authorization": token, "Content-Type": "application/json"},
    )
    response.raise_for_status()
    data = response.json()

    if "errors" in data:
        print(f"Error: {json.dumps(data['errors'])}", file=sys.stderr)
        sys.exit(1)

    result = data["data"]["workflowStateCreate"]["workflowState"]
    print(json.dumps(result))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/Projects/linear-agent && ./venv/bin/pytest tests/test_create_workflow_state.py -v`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/create_workflow_state.py tests/test_create_workflow_state.py
git commit -m "feat: create_workflow_state.py — create Linear workflow states via GraphQL"
```

---

### Task 3: Python Script — create_project_label.py

**Files:**
- Create: `scripts/create_project_label.py`
- Create: `tests/test_create_project_label.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_create_project_label.py`:

```python
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = str(Path(__file__).parent.parent / "scripts" / "create_project_label.py")


def run_script(*args: str, env_override: dict | None = None) -> subprocess.CompletedProcess:
    import os

    env = {**os.environ, **(env_override or {})}
    return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True, env=env)


def test_missing_token_exits_nonzero():
    result = run_script("--name", "Claude Active", env_override={"LINEAR_TOKEN": ""})
    assert result.returncode != 0
    assert "LINEAR_TOKEN" in result.stderr


def test_missing_name_exits_nonzero():
    result = run_script(env_override={"LINEAR_TOKEN": "fake"})
    assert result.returncode != 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/Projects/linear-agent && ./venv/bin/pytest tests/test_create_project_label.py -v`
Expected: FAIL

- [ ] **Step 3: Write the implementation**

Create `scripts/create_project_label.py`:

```python
"""Create a project-level label in Linear via GraphQL API."""

import argparse
import json
import os
import sys

import httpx

API_URL = "https://api.linear.app/graphql"

MUTATION = """
mutation ProjectLabelCreate($input: ProjectLabelCreateInput!) {
  projectLabelCreate(input: $input) {
    success
    projectLabel {
      id
      name
      color
    }
  }
}
"""


def main() -> None:
    token = os.environ.get("LINEAR_TOKEN", "")
    if not token:
        print("Error: LINEAR_TOKEN environment variable is not set", file=sys.stderr)
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Create a Linear project label")
    parser.add_argument("--name", required=True, help="Label name")
    parser.add_argument("--color", default="#6366F1", help="Hex color")
    parser.add_argument("--description", default="", help="Label description")
    args = parser.parse_args()

    variables = {"input": {"name": args.name, "color": args.color}}
    if args.description:
        variables["input"]["description"] = args.description

    response = httpx.post(
        API_URL,
        json={"query": MUTATION, "variables": variables},
        headers={"Authorization": token, "Content-Type": "application/json"},
    )
    response.raise_for_status()
    data = response.json()

    if "errors" in data:
        print(f"Error: {json.dumps(data['errors'])}", file=sys.stderr)
        sys.exit(1)

    result = data["data"]["projectLabelCreate"]["projectLabel"]
    print(json.dumps(result))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/Projects/linear-agent && ./venv/bin/pytest tests/test_create_project_label.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/create_project_label.py tests/test_create_project_label.py
git commit -m "feat: create_project_label.py — create Linear project labels via GraphQL"
```

---

### Task 4: Python Scripts — create_project_link.py & get_project_links.py

**Files:**
- Create: `scripts/create_project_link.py`
- Create: `scripts/get_project_links.py`
- Create: `tests/test_project_links.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_project_links.py`:

```python
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"


def run_script(name: str, *args: str, env_override: dict | None = None) -> subprocess.CompletedProcess:
    import os

    env = {**os.environ, **(env_override or {})}
    return subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / name), *args],
        capture_output=True, text=True, env=env,
    )


def test_create_link_missing_token():
    result = run_script(
        "create_project_link.py",
        "--project-id", "fake", "--label", "Repository", "--url", "https://example.com",
        env_override={"LINEAR_TOKEN": ""},
    )
    assert result.returncode != 0
    assert "LINEAR_TOKEN" in result.stderr


def test_create_link_missing_args():
    result = run_script("create_project_link.py", env_override={"LINEAR_TOKEN": "fake"})
    assert result.returncode != 0


def test_get_links_missing_token():
    result = run_script(
        "get_project_links.py", "--project-id", "fake",
        env_override={"LINEAR_TOKEN": ""},
    )
    assert result.returncode != 0
    assert "LINEAR_TOKEN" in result.stderr


def test_get_links_missing_args():
    result = run_script("get_project_links.py", env_override={"LINEAR_TOKEN": "fake"})
    assert result.returncode != 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/Projects/linear-agent && ./venv/bin/pytest tests/test_project_links.py -v`
Expected: FAIL

- [ ] **Step 3: Write create_project_link.py**

Create `scripts/create_project_link.py`:

```python
"""Add a link resource (entity external link) to a Linear project via GraphQL API."""

import argparse
import json
import os
import sys

import httpx

API_URL = "https://api.linear.app/graphql"

MUTATION = """
mutation EntityExternalLinkCreate($input: EntityExternalLinkCreateInput!) {
  entityExternalLinkCreate(input: $input) {
    success
    entityExternalLink {
      id
      label
      url
    }
  }
}
"""


def main() -> None:
    token = os.environ.get("LINEAR_TOKEN", "")
    if not token:
        print("Error: LINEAR_TOKEN environment variable is not set", file=sys.stderr)
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Add a link resource to a Linear project")
    parser.add_argument("--project-id", required=True, help="Project UUID")
    parser.add_argument("--label", required=True, help="Link label (e.g., 'Repository')")
    parser.add_argument("--url", required=True, help="Link URL")
    args = parser.parse_args()

    variables = {
        "input": {
            "projectId": args.project_id,
            "label": args.label,
            "url": args.url,
        }
    }

    response = httpx.post(
        API_URL,
        json={"query": MUTATION, "variables": variables},
        headers={"Authorization": token, "Content-Type": "application/json"},
    )
    response.raise_for_status()
    data = response.json()

    if "errors" in data:
        print(f"Error: {json.dumps(data['errors'])}", file=sys.stderr)
        sys.exit(1)

    result = data["data"]["entityExternalLinkCreate"]["entityExternalLink"]
    print(json.dumps(result))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Write get_project_links.py**

Create `scripts/get_project_links.py`:

```python
"""Read link resources from a Linear project via GraphQL API."""

import argparse
import json
import os
import sys

import httpx

API_URL = "https://api.linear.app/graphql"

QUERY = """
query ProjectLinks($id: String!) {
  project(id: $id) {
    externalLinks {
      nodes {
        id
        label
        url
      }
    }
  }
}
"""


def main() -> None:
    token = os.environ.get("LINEAR_TOKEN", "")
    if not token:
        print("Error: LINEAR_TOKEN environment variable is not set", file=sys.stderr)
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Read link resources from a Linear project")
    parser.add_argument("--project-id", required=True, help="Project UUID")
    args = parser.parse_args()

    response = httpx.post(
        API_URL,
        json={"query": QUERY, "variables": {"id": args.project_id}},
        headers={"Authorization": token, "Content-Type": "application/json"},
    )
    response.raise_for_status()
    data = response.json()

    if "errors" in data:
        print(f"Error: {json.dumps(data['errors'])}", file=sys.stderr)
        sys.exit(1)

    links = data["data"]["project"]["externalLinks"]["nodes"]
    print(json.dumps(links))


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd ~/Projects/linear-agent && ./venv/bin/pytest tests/test_project_links.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add scripts/create_project_link.py scripts/get_project_links.py tests/test_project_links.py
git commit -m "feat: project link scripts — create and read Linear project resources"
```

---

### Task 5: Python Script — create_forgejo_pr.py

**Files:**
- Create: `scripts/create_forgejo_pr.py`
- Create: `tests/test_create_forgejo_pr.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_create_forgejo_pr.py`:

```python
import subprocess
import sys
from pathlib import Path

SCRIPT = str(Path(__file__).parent.parent / "scripts" / "create_forgejo_pr.py")


def run_script(*args: str, env_override: dict | None = None) -> subprocess.CompletedProcess:
    import os

    env = {**os.environ, **(env_override or {})}
    return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True, env=env)


def test_missing_token_exits_nonzero():
    result = run_script(
        "--repo-url", "https://forgejo.bishop.landq.net/Anvil/blog",
        "--branch", "lan-42-test",
        "--title", "test PR",
        "--body", "test body",
        env_override={"FORGEJO_TOKEN": ""},
    )
    assert result.returncode != 0
    assert "FORGEJO_TOKEN" in result.stderr


def test_missing_args_exits_nonzero():
    result = run_script(env_override={"FORGEJO_TOKEN": "fake"})
    assert result.returncode != 0


def test_url_parsing():
    """Verify repo URL is parsed into owner/repo correctly."""
    # Import the module to test the parsing function directly
    import importlib.util

    spec = importlib.util.spec_from_file_location("create_forgejo_pr", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    owner, repo = mod.parse_repo_url("https://forgejo.bishop.landq.net/Anvil/blog")
    assert owner == "Anvil"
    assert repo == "blog"

    owner, repo = mod.parse_repo_url("https://forgejo.bishop.landq.net/Anvil/blog.git")
    assert owner == "Anvil"
    assert repo == "blog"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/Projects/linear-agent && ./venv/bin/pytest tests/test_create_forgejo_pr.py -v`
Expected: FAIL

- [ ] **Step 3: Write the implementation**

Create `scripts/create_forgejo_pr.py`:

```python
"""Create a pull request on a Forgejo instance."""

import argparse
import json
import os
import sys
from urllib.parse import urlparse

import httpx


def parse_repo_url(url: str) -> tuple[str, str]:
    """Extract owner and repo name from a Forgejo/Gitea repo URL."""
    path = urlparse(url).path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    parts = path.split("/")
    if len(parts) < 2:
        raise ValueError(f"Cannot parse owner/repo from URL: {url}")
    return parts[0], parts[1]


def main() -> None:
    token = os.environ.get("FORGEJO_TOKEN", "")
    if not token:
        print("Error: FORGEJO_TOKEN environment variable is not set", file=sys.stderr)
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Create a Forgejo pull request")
    parser.add_argument("--repo-url", required=True, help="Full repo URL")
    parser.add_argument("--branch", required=True, help="Head branch name")
    parser.add_argument("--title", required=True, help="PR title")
    parser.add_argument("--body", default="", help="PR body (markdown)")
    parser.add_argument("--base", default="main", help="Base branch (default: main)")
    args = parser.parse_args()

    parsed = urlparse(args.repo_url)
    base_url = f"{parsed.scheme}://{parsed.hostname}"
    if parsed.port:
        base_url += f":{parsed.port}"

    try:
        owner, repo = parse_repo_url(args.repo_url)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    response = httpx.post(
        f"{base_url}/api/v1/repos/{owner}/{repo}/pulls",
        json={
            "title": args.title,
            "head": args.branch,
            "base": args.base,
            "body": args.body,
        },
        headers={"Authorization": f"token {token}", "Content-Type": "application/json"},
    )
    response.raise_for_status()
    data = response.json()

    print(json.dumps({"number": data["number"], "html_url": data["html_url"]}))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/Projects/linear-agent && ./venv/bin/pytest tests/test_create_forgejo_pr.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/create_forgejo_pr.py tests/test_create_forgejo_pr.py
git commit -m "feat: create_forgejo_pr.py — create PRs on Forgejo via REST API"
```

---

### Task 6: Reference File — config.md

**Files:**
- Create: `references/config.md`

- [ ] **Step 1: Write the reference file**

Create `references/config.md`:

```markdown
# Config: Reading and Writing linear-worker.yaml

## Reading the Config

1. Use the Read tool to read `~/.claude/linear-worker.yaml`
2. If the file does not exist, stop and tell the user: "Config not found. Run `/linear-health` first to set up."
3. Parse the YAML content. Extract these values:

| Key | Type | Description |
|-----|------|-------------|
| `team.id` | string | Team UUID |
| `team.name` | string | Team name |
| `team.key` | string | Team key prefix (e.g., "LAN") |
| `statuses.*` | string | UUID for each status name |
| `labels.issue.claude` | string | UUID of "Claude" issue label |
| `labels.issue.review` | string | UUID of "Review" issue label |
| `labels.project.claude_active` | string | UUID of "Claude Active" project label |
| `operator.id` | string | Human operator's user UUID |
| `operator.name` | string | Human operator's name |
| `projects.<slug>` | object | Each active project |
| `projects.<slug>.id` | string | Project UUID |
| `projects.<slug>.repo` | string or null | Git repo URL (null = document mode) |
| `projects.<slug>.local_path` | string or null | Local clone path |
| `clone_base` | string | Base directory for cloning repos |
| `stale_threshold_hours` | number | Hours before an In Progress issue is considered stale |

4. If `last_health_check` is more than 24 hours old, warn: "Config is stale (last health check: <date>). Consider running `/linear-health` to refresh."

## Writing the Config

When updating the config (e.g., after cloning a repo and setting `local_path`):

1. Read the current file
2. Modify the specific field
3. Write the full file back using the Write tool
4. Preserve all existing fields — only change what's needed
```

- [ ] **Step 2: Commit**

```bash
git add references/config.md
git commit -m "docs: references/config.md — config file read/write instructions"
```

---

### Task 7: Reference File — next-flow.md

**Files:**
- Create: `references/next-flow.md`

- [ ] **Step 1: Write the reference file**

Create `references/next-flow.md`:

```markdown
# Next Flow: Select the Next Issue to Work On

## Inputs

- Config loaded per `${CLAUDE_PLUGIN_ROOT}/references/config.md`
- Optional: `project_filter` (project name to restrict selection)
- Optional: `interactive` (boolean, default true — set false for orchestrator use)

## Steps

### 1. Query Todo Issues

Use the `list_issues` MCP tool:
- `state`: "Todo"
- `orderBy`: "updatedAt" (priority is not a direct sort — we filter by it below)

### 2. Filter to Active Projects

For each returned issue, check that its project ID matches one of the projects in the config. Discard issues from non-active projects.

If `project_filter` is provided, further restrict to issues whose project name matches.

### 3. Sort by Priority

Sort the remaining issues by priority value (1=Urgent, 2=High, 3=Normal, 4=Low, 0=None). Lower number = higher priority. Issues with priority 0 (None) sort last.

### 4. Check Dependencies

For each candidate (in priority order), call `get_issue` with `includeRelations: true`.

Check the `blockedBy` relations. If any blocking issue has a status that is NOT of type "completed" or "canceled", skip this candidate.

### 5. Return Result

Return the first qualifying issue, or null if none found.

If `interactive` is true and an issue is found:
- Display: issue identifier, title, priority, project name, description (first 200 chars)
- Ask: "Work on this issue? (y/n)"
- If no: skip and try the next candidate
- If yes: return this issue

If `interactive` is false:
- Return the first qualifying issue without prompting
```

- [ ] **Step 2: Commit**

```bash
git add references/next-flow.md
git commit -m "docs: references/next-flow.md — issue selection logic"
```

---

### Task 8: Reference File — plan-flow.md

**Files:**
- Create: `references/plan-flow.md`

- [ ] **Step 1: Write the reference file**

Create `references/plan-flow.md`:

```markdown
# Plan Flow: Analyze an Issue and Create an Execution Plan

## Inputs

- Config loaded per `${CLAUDE_PLUGIN_ROOT}/references/config.md`
- `issue_id`: The Linear issue identifier (e.g., LAN-42)

## Steps

### 1. Fetch Issue Details

Use `get_issue` MCP tool with `includeRelations: true` to get:
- Title, description, priority, labels
- Project (to determine code vs. document mode)
- Relations (blocking/blocked-by)

### 2. Read Existing Comments

Use `list_comments` MCP tool with `issueId` to check if a plan comment already exists (starts with `## Execution Plan`). If one exists, skip planning — the issue is already planned.

### 3. Determine Mode

Look up the issue's project in the config:
- If the project has a `repo` value (not null) → **Code mode**
- If the project has `repo: null` → **Document mode**

### 4a. Code Mode Planning

1. Navigate to the project's `local_path`. If `local_path` is null but `repo` exists:
   - Clone: `git clone <repo> <clone_base>/<repo-name>`
   - Update config with the new `local_path`
2. Pull latest: `git checkout main && git pull`
3. Explore the codebase using Read, Glob, Grep tools to understand:
   - Project structure and conventions
   - Files relevant to the issue
   - Existing tests and patterns
4. Create a checklist plan with concrete steps

### 4b. Document Mode Planning

1. Analyze the issue description and any linked resources
2. Determine what research, writing, or analysis is needed
3. Create a checklist plan with concrete deliverables

### 5. Post the Plan

Use `save_comment` MCP tool to post a comment on the issue:

```
## Execution Plan

- [ ] Step 1: <description>
- [ ] Step 2: <description>
- [ ] Step 3: <description>
...
```

The `## Execution Plan` heading MUST be the first line of the comment body. This is how `work-flow.md` discovers the plan later.

### 6. Check for Ambiguity

If the issue is too vague to create a concrete plan (missing requirements, unclear scope, needs human decision):

Follow `${CLAUDE_PLUGIN_ROOT}/references/review-issue-flow.md` to create a review sub-issue with specific questions. This will set the parent issue to "Blocked".

### 7. Create Sub-Issues for Discovered Work

If during exploration you discover work that is out of scope for this issue:

Use `save_issue` MCP tool to create sub-issues:
- `parentId`: the current issue's ID
- `team`: from config
- `status`: "Backlog"
- Title should clearly describe the discovered work

**Max 1 level deep.** Never create children of sub-issues.
```

- [ ] **Step 2: Commit**

```bash
git add references/plan-flow.md
git commit -m "docs: references/plan-flow.md — issue planning logic"
```

---

### Task 9: Reference Files — work-flow.md, pr-creation.md, review-issue-flow.md

**Files:**
- Create: `references/work-flow.md`
- Create: `references/pr-creation.md`
- Create: `references/review-issue-flow.md`

- [ ] **Step 1: Write work-flow.md**

Create `references/work-flow.md`:

```markdown
# Work Flow: Execute the Plan for an Issue

## Inputs

- Config loaded per `${CLAUDE_PLUGIN_ROOT}/references/config.md`
- `issue_id`: The Linear issue identifier (e.g., LAN-42)

## Steps

### 1. Discover the Plan Comment

Use `list_comments` MCP tool with `issueId`.

Find the comment whose body starts with `## Execution Plan`. This is the plan comment. Note its `id` — you'll need it to update the comment as you check off items.

If no plan comment exists, stop and report: "No execution plan found for this issue. Run `/linear-plan <issue-id>` first."

### 2. Parse Checklist

Extract lines matching `- [ ] ` (unchecked) and `- [x] ` (checked). These are the plan items. Work through unchecked items in order.

### 3. Determine Mode

Look up the issue's project in config:
- `repo` exists → Code mode
- `repo` is null → Document mode

### 4. Code Mode Execution

#### 4a. Set Up Worktree

1. Navigate to the project's `local_path`
2. Ensure main branch is up to date: `git checkout main && git pull`
3. Get the branch name from `get_issue` MCP tool response (it provides a suggested branch name). If not available, construct as: `<team-key-lower>-<issue-number>-<slugified-title>` (e.g., `lan-42-add-rss-feed`)
4. Create worktree: `git worktree add .worktrees/<branch> -b <branch> main`
5. Change to the worktree directory

#### 4b. Work Through Checklist

For each unchecked item:
1. Do the work (edit files, create files, run commands)
2. Update the plan comment by calling `save_comment` with:
   - `id`: the plan comment's ID
   - `body`: the full comment body with this item changed from `- [ ]` to `- [x]`

If blocked on any item (need info, access issue, unexpected complexity):
- Follow `${CLAUDE_PLUGIN_ROOT}/references/review-issue-flow.md`
- The review flow will set the issue to "Blocked" and stop execution

#### 4c. Complete

After all items are checked:
1. Stage and commit all changes with a descriptive message
2. Push the branch: `git push origin <branch>`
   - If push requires auth, use: `git push https://<user>:$FORGEJO_TOKEN@<host>/<owner>/<repo>.git <branch>`
3. Create a PR per `${CLAUDE_PLUGIN_ROOT}/references/pr-creation.md`
4. Link the PR on the Linear issue using `save_issue` MCP tool with `links`:
   ```json
   [{"url": "<pr-url>", "title": "Pull Request"}]
   ```
5. Set issue status to "In Review" using `save_issue` with `state`: "In Review"
6. Post a summary comment on the issue describing what was done

### 5. Document Mode Execution

#### 5a. Work Through Checklist

For each unchecked item:
1. Do the research, analysis, or writing
2. Update the plan comment to check off the item (same as code mode)

If the deliverable is a document, create it using `create_document` MCP tool:
- `title`: descriptive title
- `project`: the project name from config
- `content`: the document content in markdown

If blocked: follow `review-issue-flow.md` (same as code mode)

#### 5b. Complete

1. Post a summary comment on the issue describing deliverables and findings
2. Set issue status to "In Review" using `save_issue` with `state`: "In Review"
```

- [ ] **Step 2: Write pr-creation.md**

Create `references/pr-creation.md`:

```markdown
# PR Creation

## Inputs

- `repo_url`: the project's git repo URL from config
- `branch`: the branch name with the changes
- `issue_key`: the Linear issue identifier (e.g., LAN-42)
- `issue_title`: the Linear issue title
- `issue_url`: the Linear issue URL
- `summary`: brief description of changes

## Determine Git Host

Parse the `repo_url`:
- If hostname contains "forgejo" or matches `forgejo.bishop.landq.net` → **Forgejo**
- If hostname contains "github.com" → **GitHub**

## Forgejo PR Creation

Run the script:

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/create_forgejo_pr.py" \
  --repo-url "<repo_url>" \
  --branch "<branch>" \
  --title "<issue_key>: <issue_title>" \
  --body "Resolves [<issue_key>](<issue_url>)

<summary>"
```

The script outputs JSON with `number` and `html_url`. Use the `html_url` as the PR URL.

## GitHub PR Creation

From within the worktree directory, run:

```bash
gh pr create \
  --title "<issue_key>: <issue_title>" \
  --body "Resolves [<issue_key>](<issue_url>)

<summary>" \
  --head "<branch>" \
  --base "main"
```

Parse the output to get the PR URL.
```

- [ ] **Step 3: Write review-issue-flow.md**

Create `references/review-issue-flow.md`:

```markdown
# Review Issue Flow: Request Human Input

Use this flow when you encounter something that requires human judgment, decision, or information you don't have access to.

## Inputs

- Config loaded per `${CLAUDE_PLUGIN_ROOT}/references/config.md`
- `parent_issue_id`: the issue you're working on
- `parent_issue_key`: its identifier (e.g., LAN-42)
- `question`: the specific question or decision needed

## Steps

### 1. Create Review Sub-Issue

Use `save_issue` MCP tool:
- `title`: `[Review] <parent_issue_key>: <concise question>`
- `team`: config `team.name`
- `parentId`: `parent_issue_id`
- `assignee`: config `operator.name`
- `labels`: ["Review"]
- `state`: "Todo"
- `description`: Include:
  - Context: what you were doing when you hit the block
  - What you've tried or considered
  - The specific question(s) that need answering
  - Any options you've identified with trade-offs

### 2. Block the Parent Issue

Use `save_issue` MCP tool:
- `id`: `parent_issue_id`
- `state`: "Blocked"

### 3. Post Blocking Comment

Use `save_comment` MCP tool:
- `issueId`: `parent_issue_id`
- `body`: `Blocked — waiting for human input on <review_issue_key>: <question summary>`

### 4. Stop Execution

After creating the review issue and blocking the parent, **stop working on this issue**. Return control to the caller (the orchestrator will move to the next issue, or the standalone command will exit).
```

- [ ] **Step 4: Commit**

```bash
git add references/work-flow.md references/pr-creation.md references/review-issue-flow.md
git commit -m "docs: work-flow, pr-creation, review-issue-flow reference files"
```

---

### Task 10: Commands — linear-health

**Files:**
- Create: `commands/linear-health.md`

- [ ] **Step 1: Write the command**

Create `commands/linear-health.md`:

```markdown
---
name: linear-health
description: "Validate and set up the Linear agent environment. Creates missing statuses, labels, and caches workspace config. Run this first before using any other linear-agent commands."
allowed-tools:
  - Read
  - Write
  - Bash
  - Glob
  - mcp__plugin_linear_linear__list_teams
  - mcp__plugin_linear_linear__list_issue_statuses
  - mcp__plugin_linear_linear__list_issue_labels
  - mcp__plugin_linear_linear__list_project_labels
  - mcp__plugin_linear_linear__list_projects
  - mcp__plugin_linear_linear__get_project
  - mcp__plugin_linear_linear__create_issue_label
  - mcp__plugin_linear_linear__get_user
  - mcp__plugin_linear_linear__list_issues
  - mcp__plugin_linear_linear__list_comments
---

# /linear-health — Setup & Validate Linear Agent

Run this command to set up or refresh the Linear agent configuration.

## Process

### 1. Discover Team

Use `list_teams` to find the team. If multiple teams exist, use the first one (single-team support for v1). Note the team ID, name, and key.

### 2. Discover & Create Statuses

Use `list_issue_statuses` with the team name.

Map these statuses by name (case-insensitive):
- backlog, todo, in_progress (name: "In Progress"), in_review (name: "In Review"), done, blocked

If **"Blocked"** status is missing, create it:
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/create_workflow_state.py" \
  --team-id "<team-id>" --name "Blocked" --type "started" --color "#95a2b3"
```

Re-query statuses after creation to get the new ID.

### 3. Discover & Create Labels

**Issue labels:** Use `list_issue_labels`.
- If "Claude" label missing → create via `create_issue_label` with name "Claude", color "#6366F1"
- If "Review" label missing → create via `create_issue_label` with name "Review", color "#F59E0B"

**Project labels:** Use `list_project_labels`.
- If "Claude Active" label missing → create it:
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/create_project_label.py" \
  --name "Claude Active" --color "#6366F1" --description "Projects that Claude agent is allowed to work on"
```

Re-query after creation to get IDs.

### 4. Discover Operator

Use `get_user` with query "me" to get the current user's ID and name for the `operator` config field.

### 5. Discover Active Projects

Use `list_projects` with label "Claude Active".

For each active project, read its link resources:
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/get_project_links.py" --project-id "<project-id>"
```

Find the link with label "Repository" — its URL is the repo URL. If no such link exists, `repo` is null (document mode project).

### 6. Validate Git Access

For each project with a repo URL, verify access:
```bash
git ls-remote "<repo-url>" HEAD
```

Report any failures as warnings (don't fail the whole health check).

### 7. Clean Up Merged Worktrees

For each project with a `local_path`, check for worktrees:
```bash
cd "<local_path>" && git worktree list --porcelain
```

For each worktree, check if its branch has been merged:
```bash
git branch --merged main | grep "<branch-name>"
```

If merged, remove: `git worktree remove <path>`

Report cleanups.

### 8. Detect Stale Issues

Use `list_issues` with state "In Progress" to find in-flight issues. For each, check `list_comments` for recent activity. If no comment in the last `stale_threshold_hours` (default 4), report as stale.

### 9. Write Config

Write the complete config to `~/.claude/linear-worker.yaml` using the Write tool. Use the format from the spec. Set `last_health_check` to the current ISO-8601 timestamp.

### 10. Report

Display a summary:
- Team: name (key)
- Statuses: found N, created N
- Labels: found N, created N
- Active projects: list with repo status
- Git access: verified/failed per project
- Worktrees cleaned: N
- Stale issues: list (if any)
- Config written to: `~/.claude/linear-worker.yaml`
```

- [ ] **Step 2: Commit**

```bash
git add commands/linear-health.md
git commit -m "feat: /linear-health command — setup, validation, self-healing"
```

---

### Task 11: Commands — Simple Standalone (linear-next, linear-plan, linear-work, linear-update)

**Files:**
- Create: `commands/linear-next.md`
- Create: `commands/linear-plan.md`
- Create: `commands/linear-work.md`
- Create: `commands/linear-update.md`

- [ ] **Step 1: Write linear-next.md**

Create `commands/linear-next.md`:

```markdown
---
name: linear-next
description: "Pull the next highest-priority Todo issue from Linear's backlog. Filters to Claude Active projects, skips blocked issues, and lets you choose whether to start working on it."
argument-hint: "[--project <name>]"
---

# /linear-next — Pull the Next Issue

Read config per `${CLAUDE_PLUGIN_ROOT}/references/config.md`.

Follow the issue selection logic in `${CLAUDE_PLUGIN_ROOT}/references/next-flow.md` with `interactive: true`.

Parse arguments: if `--project <name>` is provided, pass it as the `project_filter`.

After the user confirms an issue:
1. Apply the "Claude" label using `save_issue` with `labels: ["Claude"]`
2. Set status to "In Progress" using `save_issue` with `state: "In Progress"`
3. Display: "Issue <key> is now In Progress. Run `/linear-plan <key>` to create a plan, or `/linear-assign <key>` to plan and work on it."
```

- [ ] **Step 2: Write linear-plan.md**

Create `commands/linear-plan.md`:

```markdown
---
name: linear-plan
description: "Analyze a Linear issue and create an execution plan. Posts the plan as a checklist comment on the issue. Creates review sub-issues if the issue needs clarification."
argument-hint: "<issue-id>"
---

# /linear-plan — Create an Execution Plan

The `<issue-id>` argument is required (e.g., LAN-42).

Read config per `${CLAUDE_PLUGIN_ROOT}/references/config.md`.

Follow `${CLAUDE_PLUGIN_ROOT}/references/plan-flow.md` with the provided issue ID.
```

- [ ] **Step 3: Write linear-work.md**

Create `commands/linear-work.md`:

```markdown
---
name: linear-work
description: "Execute the plan for a Linear issue. For code tasks: creates a git worktree, works through the checklist, and creates a PR. For non-code tasks: creates Linear documents. Updates the plan comment as items are completed."
argument-hint: "<issue-id>"
---

# /linear-work — Execute an Issue's Plan

The `<issue-id>` argument is required (e.g., LAN-42).

Read config per `${CLAUDE_PLUGIN_ROOT}/references/config.md`.

Follow `${CLAUDE_PLUGIN_ROOT}/references/work-flow.md` with the provided issue ID.
```

- [ ] **Step 4: Write linear-update.md**

Create `commands/linear-update.md`:

```markdown
---
name: linear-update
description: "Manually update a Linear issue's status with an optional comment. Useful for re-queuing blocked issues or manual status changes."
argument-hint: "<issue-id> <status> [--comment <message>]"
---

# /linear-update — Update Issue Status

Arguments:
- `<issue-id>`: required (e.g., LAN-42)
- `<status>`: required — one of: backlog, todo, in_progress, in_review, done, blocked
- `--comment <message>`: optional

Read config per `${CLAUDE_PLUGIN_ROOT}/references/config.md`.

1. Validate `<status>` is one of the known status names in config
2. Use `save_issue` MCP tool with `id: <issue-id>` and `state: <status>`
3. If `--comment` provided, use `save_comment` MCP tool with `issueId: <issue-id>` and `body: <message>`
4. Display confirmation: "Updated <issue-id> to <status>"
```

- [ ] **Step 5: Commit**

```bash
git add commands/linear-next.md commands/linear-plan.md commands/linear-work.md commands/linear-update.md
git commit -m "feat: standalone commands — linear-next, linear-plan, linear-work, linear-update"
```

---

### Task 12: Commands — CRUD (linear-project-create, linear-issue-create, linear-issues)

**Files:**
- Create: `commands/linear-project-create.md`
- Create: `commands/linear-issue-create.md`
- Create: `commands/linear-issues.md`

- [ ] **Step 1: Write linear-project-create.md**

Create `commands/linear-project-create.md`:

```markdown
---
name: linear-project-create
description: "Create a new Linear project and mark it as Claude Active. Optionally attach a git repository URL as a project resource."
argument-hint: "<name> [--repo <url>] [--description <text>]"
---

# /linear-project-create — Create a New Project

Arguments:
- `<name>`: required — the project name
- `--repo <url>`: optional — git repository URL
- `--description <text>`: optional — project description

Read config per `${CLAUDE_PLUGIN_ROOT}/references/config.md`.

1. Create the project using `save_project` MCP tool:
   - `name`: the provided name
   - `addTeams`: [config team name]
   - `description`: provided description or empty
   - `labels`: ["Claude Active"]

2. If `--repo` is provided, add it as a project link:
```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/create_project_link.py" \
  --project-id "<new-project-id>" --label "Repository" --url "<repo-url>"
```

3. Update `~/.claude/linear-worker.yaml` — add the new project to the `projects` section with its ID, repo URL, and null local_path.

4. Display: "Created project '<name>' (<key>). Claude Active: yes. Repo: <url or 'none'>"
```

- [ ] **Step 2: Write linear-issue-create.md**

Create `commands/linear-issue-create.md`:

```markdown
---
name: linear-issue-create
description: "Create a new Linear issue in a Claude Active project. Sets status to Todo so it's ready for Claude to pick up."
argument-hint: "<title> --project <name> [--priority <level>] [--description <text>]"
---

# /linear-issue-create — Create a New Issue

Arguments:
- `<title>`: required — the issue title
- `--project <name>`: required — project name (must be Claude Active)
- `--priority <level>`: optional — urgent, high, normal (default), low
- `--description <text>`: optional — issue description in markdown

Read config per `${CLAUDE_PLUGIN_ROOT}/references/config.md`.

1. Validate the project exists in config (is Claude Active)
2. Map priority name to number: urgent=1, high=2, normal=3, low=4
3. Create issue using `save_issue` MCP tool:
   - `title`: provided title
   - `team`: config team name
   - `project`: project name
   - `state`: "Todo"
   - `priority`: mapped number
   - `description`: provided or empty
4. Display: "Created <issue-key>: <title> (priority: <level>, project: <name>)"
```

- [ ] **Step 3: Write linear-issues.md**

Create `commands/linear-issues.md`:

```markdown
---
name: linear-issues
description: "Show Linear issues from Claude Active projects. Defaults to showing Todo and Backlog issues. Filter by project or status."
argument-hint: "[--project <name>] [--status <status>]"
---

# /linear-issues — List Available Issues

Arguments:
- `--project <name>`: optional — filter to one project
- `--status <status>`: optional — filter to a specific status (default: shows Todo and Backlog)

Read config per `${CLAUDE_PLUGIN_ROOT}/references/config.md`.

1. For each active project in config (or just the filtered one):
   - Use `list_issues` MCP tool with:
     - `project`: project name
     - `state`: the status filter, or query both "Todo" and "Backlog" if no filter
   - Collect all matching issues

2. Sort all collected issues by priority (1=Urgent first, then 2=High, 3=Normal, 4=Low, 0=None last)

3. Display as a table:

```
| ID      | Title                    | Priority | Project              | Status  |
|---------|--------------------------|----------|----------------------|---------|
| LAN-42  | Add RSS feed to blog     | High     | Blog Pipeline        | Todo    |
| LAN-38  | Research solar panels    | High     | Overland Buildout    | Todo    |
| LAN-51  | Add sitemap              | Normal   | Blog Pipeline        | Backlog |
```

If no issues found: "No issues matching filters in Claude Active projects."
```

- [ ] **Step 4: Commit**

```bash
git add commands/linear-project-create.md commands/linear-issue-create.md commands/linear-issues.md
git commit -m "feat: CRUD commands — linear-project-create, linear-issue-create, linear-issues"
```

---

### Task 13: Commands — Orchestrators (linear-assign, work-backlog)

**Files:**
- Create: `commands/linear-assign.md`
- Create: `commands/work-backlog.md`

- [ ] **Step 1: Write linear-assign.md**

Create `commands/linear-assign.md`:

```markdown
---
name: linear-assign
description: "Assign a specific Linear issue to Claude and begin working on it. Automatically determines the next action: plan if no plan exists, work if plan exists. This is the 'point Claude at a specific issue' entry point."
argument-hint: "<issue-id>"
---

# /linear-assign — Assign and Work a Specific Issue

The `<issue-id>` argument is required (e.g., LAN-42).

This command is self-contained. It reads shared reference files but does NOT invoke other commands.

## Process

### 1. Load Config

Read config per `${CLAUDE_PLUGIN_ROOT}/references/config.md`.

### 2. Validate Issue

Use `get_issue` MCP tool to fetch the issue. Verify its project is in the config's active projects list. If not, stop: "Issue <key> is not in a Claude Active project."

### 3. Set In Progress

Use `save_issue` MCP tool:
- `id`: the issue ID
- `labels`: ["Claude"]
- `state`: "In Progress"

### 4. Check for Existing Plan

Use `list_comments` MCP tool with `issueId`.

Look for a comment whose body starts with `## Execution Plan`.

### 5. Determine Next Action

**If no plan comment exists:**
- Follow `${CLAUDE_PLUGIN_ROOT}/references/plan-flow.md` to create a plan
- If the issue was blocked during planning (review issue created), stop here
- Otherwise, continue to step 6

**If plan exists with unchecked items (`- [ ]`):**
- Continue to step 6

**If plan exists and all items are checked (`- [x]`):**
- Set status to "In Review" using `save_issue`
- Post summary comment
- Stop: "Issue <key> plan is fully complete. Set to In Review."

### 6. Execute the Plan

Follow `${CLAUDE_PLUGIN_ROOT}/references/work-flow.md` with the issue ID.
```

- [ ] **Step 2: Write work-backlog.md**

Create `commands/work-backlog.md`:

```markdown
---
name: work-backlog
description: "Process the Linear backlog autonomously. Loops through Todo issues by priority, plans each one, executes the work, and creates PRs or documents. Confirms every 3 issues."
argument-hint: "[--project <name>] [--limit <n>]"
---

# /work-backlog — Autonomous Backlog Processing

This command is self-contained. It reads shared reference files but does NOT invoke other commands.

## Arguments

- `--project <name>`: optional — restrict to one project
- `--limit <n>`: optional — max issues to process (default: unlimited)

## Process

### 1. Load & Validate Config

Read config per `${CLAUDE_PLUGIN_ROOT}/references/config.md`.

If `last_health_check` is more than 24 hours old, warn: "Config is stale. Consider running `/linear-health` first." Continue anyway.

### 2. Initialize Counters

```
completed = 0
blocked = 0
prs_created = 0
iteration = 0
```

### 3. Main Loop

Repeat:

#### 3a. Select Next Issue

Follow `${CLAUDE_PLUGIN_ROOT}/references/next-flow.md` with:
- `project_filter`: the `--project` argument if provided
- `interactive`: false (no confirmation per issue)

If no issue found → exit loop.

#### 3b. Set In Progress

Use `save_issue` MCP tool:
- `id`: the issue ID
- `labels`: ["Claude"]
- `state`: "In Progress"

#### 3c. Plan the Issue

Follow `${CLAUDE_PLUGIN_ROOT}/references/plan-flow.md` with the issue ID.

If the issue was blocked during planning (review issue created):
- Increment `blocked`
- Continue to next iteration (3a)

#### 3d. Execute the Plan

Follow `${CLAUDE_PLUGIN_ROOT}/references/work-flow.md` with the issue ID.

If the issue was blocked during execution:
- Increment `blocked`
- Continue to next iteration (3a)

If completed successfully:
- Increment `completed`
- If a PR was created, increment `prs_created`

#### 3e. Check Limits

Increment `iteration`.

If `--limit` was provided and `iteration >= limit` → exit loop.

Every 3 iterations, display progress and ask to continue:
```
Progress: <completed> completed, <blocked> blocked, <prs_created> PRs created.
Continue? (y/n)
```

### 4. Summary

On exit, display:
```
Backlog processing complete.
- Issues completed: <completed>
- Issues blocked: <blocked>
- PRs created: <prs_created>
- Total processed: <iteration>
```
```

- [ ] **Step 3: Commit**

```bash
git add commands/linear-assign.md commands/work-backlog.md
git commit -m "feat: orchestrator commands — linear-assign, work-backlog"
```

---

### Task 14: Integration Test — Run /linear-health

**Files:** None (manual verification)

- [ ] **Step 1: Register the plugin**

The plugin needs to be registered in Claude Code. Check if there's an existing plugin config:
```bash
cat ~/.claude/settings.json | jq '.plugins'
```

If the plugin system uses a different registration method, follow it. The plugin root is `~/Projects/linear-agent`.

- [ ] **Step 2: Restart Claude Code session**

Exit and restart Claude Code so the plugin is loaded.

- [ ] **Step 3: Run /linear-health**

In the new session, run:
```
/linear-health
```

Verify:
- Team "Landq" is discovered
- "Blocked" status is found or created
- "Claude Active" project label is found or created
- "Claude" and "Review" issue labels are found or created
- Active projects are listed
- Config is written to `~/.claude/linear-worker.yaml`

- [ ] **Step 4: Verify config file**

Read `~/.claude/linear-worker.yaml` and verify all fields are populated correctly.

- [ ] **Step 5: Run /linear-issues**

Test that issue listing works:
```
/linear-issues
```

- [ ] **Step 6: Push all changes**

```bash
cd ~/Projects/linear-agent && git push origin main
```

- [ ] **Step 7: Commit any fixes from integration testing**

If any adjustments were needed during testing, commit them with a descriptive message.
