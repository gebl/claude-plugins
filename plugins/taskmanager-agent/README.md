# taskmanager-agent

A Claude Code plugin for autonomous task management. Integrates with Linear to pull issues, create execution plans with human-in-the-loop review, execute work via git worktrees and pull requests (or documents), and keep issue statuses in sync throughout.

## How It Works

Issues flow through a structured lifecycle:

```
Todo → In Progress → [Plan created] → Blocked (waiting for review)
  → In Progress (plan approved) → [Work executed] → In Review (PR/document submitted)
  → Done (PR merged or work accepted)
```

Claude handles the automation. Humans review plans before execution and review results before closing.

### The Three Phases

**1. Planning** — Claude analyzes the issue, explores the codebase (for code tasks), and posts a checklist-style execution plan as a comment. A review sub-issue is created and assigned to the issue creator. The parent issue is blocked until the plan is approved.

**2. Execution** — Once the plan is approved, Claude works through each checklist item. For code tasks, work happens in an isolated git worktree. Each completed item is checked off in the plan comment. On completion, a PR is created and the issue moves to In Review.

**3. Review** — The creator reviews the PR or document. If changes are needed, comments on the PR move the issue back to In Progress for Claude to address. When the PR is merged, the next `/tm-next` run detects it and closes the issue automatically.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) for dependency management
- A [Linear](https://linear.app) account with an API token
- Git (for code tasks)

## Setup

1. **Set your Linear API token:**
   ```bash
   export LINEAR_TOKEN="lin_api_..."
   ```

2. **Install the plugin** — add it to your Claude Code plugins or clone locally.

3. **Run the health check:**
   ```
   /tm-health
   ```

This bootstraps everything:
- Creates the Python virtual environment and installs dependencies
- Verifies Linear API connectivity
- Discovers your team (or asks you to choose if multiple exist)
- Creates required workflow statuses: Backlog, Todo, In Progress, In Review, Done, Blocked
- Creates required labels: **Claude** (marks issues claimed by Claude), **Review** (marks human-review sub-issues), **Claude Active** (marks projects Claude is allowed to work on)
- Discovers projects tagged with "Claude Active" and validates git repo access
- Cleans up merged worktrees
- Detects stale issues (no activity in 72+ hours by default)
- Writes config to `~/.claude/taskmanager.yaml`

> Run `/tm-health` again any time to repair or refresh the environment. It is idempotent.

4. **Tag your projects** — In Linear, add the "Claude Active" label to any project you want Claude to work on. Only tagged projects are visible to the plugin.

5. **Set local paths** — For code projects, ensure `local_path` is set in `~/.claude/taskmanager.yaml` to point at your local clone. `/tm-health` will auto-detect repos in common locations, but you may need to set this manually.

## Picking Up Work

### Smart Selection (`/tm-next`)

`/tm-next` selects the next issue to work on using a 4-phase priority system:

| Phase | What it checks | Action |
|-------|---------------|--------|
| 1. In Review | PRs for issues Claude submitted | Merged → close issue. Has comments → resume work. Closed → mark blocked. |
| 2. Resolved Reviews | Review sub-issues marked Done | Unblock the parent issue, resume work with reviewer's feedback. |
| 3. In Progress | Issues Claude already started | Resume where it left off (plan or execute). |
| 4. Todo Backlog | Unblocked Todo issues by priority | Urgent → High → Normal → Low. Skips blocked issues. |

In interactive mode (default), you confirm before work begins. Use `/tm-next --project "My Project"` to filter to a specific project.

### Direct Assignment (`/tm-assign <id>`)

Point Claude at a specific issue. It determines the next action automatically: plan if no plan exists, execute if a plan is ready.

### Autonomous Processing (`/tm-work-backlog`)

Loops through the entire Todo backlog: select → plan → execute → repeat. Pauses for confirmation every 3 issues.

```
/tm-work-backlog                        # process all active projects
/tm-work-backlog --project "My App"     # limit to one project
/tm-work-backlog --limit 5              # stop after 5 issues
```

## Commands

| Command | Description |
|---------|-------------|
| `/tm-health` | Setup and validate the environment. Run first, re-run to repair. |
| `/tm-next` | Pull the next work item using smart 4-phase selection. |
| `/tm-assign <id>` | Assign a specific issue to Claude and begin working on it. |
| `/tm-plan <id>` | Create an execution plan for an issue (posts checklist, creates review sub-issue, blocks until approved). |
| `/tm-work <id>` | Execute the approved plan (git worktree + PR for code, documents for non-code). |
| `/tm-update <id> <status>` | Manually update an issue's status with an optional comment. |
| `/tm-issues` | List issues from active projects. Defaults to Todo and Backlog. Filter with `--project` or `--status`. |
| `/tm-issue-create` | Create a new issue in an active project. Supports `--assignee` to set the owner. |
| `/tm-project-create` | Create a new project and mark it as active. Optionally attach a git repo URL. |
| `/tm-work-backlog` | Process the backlog autonomously with checkpoints every 3 issues. |

## Code Mode vs Document Mode

The plugin automatically determines the mode based on the project configuration:

- **Code mode** — Project has a `repo` URL. Work happens in a git worktree (`git worktree add`). On completion, changes are committed, pushed, and a PR is created and linked on the issue.
- **Document mode** — Project has no repo. Work produces Linear documents. On completion, documents are linked and the issue moves to In Review.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `LINEAR_TOKEN` | Yes | Linear API token for reading/writing issues, comments, and projects |
| `FORGEJO_TOKEN` | For Forgejo PRs | Forgejo/Gitea API token for creating pull requests |

## Config File

`/tm-health` writes and maintains `~/.claude/taskmanager.yaml`:

```yaml
backend: linear
last_health_check: "2026-03-19T14:30:00Z"

operator:
  id: <user-id>
  name: <user-name>

team:
  id: <team-id>
  name: <team-name>

statuses:
  backlog: <id>
  todo: <id>
  in_progress: <id>
  in_review: <id>
  done: <id>
  blocked: <id>

labels:
  issue:
    claude: <id>
    review: <id>
  project:
    claude_active: <id>

projects:
  - id: <project-id>
    name: My Code Project
    repo: https://github.com/user/repo.git
    local_path: /home/user/code/repo      # set this for code projects
    git_accessible: true
  - id: <project-id>
    name: Documentation Project
    repo: null                             # document-only project
    local_path: null

stale_threshold_hours: 72

issue_defaults:                          # optional
  assignee_id: <user-id>                 # default assignee for new issues
  assignee_name: Gabriel Lawrence        # display name (informational)
```

### Default Assignee

By default, issues created by `/tm-issue-create` and review sub-issues from `/tm-plan` are assigned to the issue creator (the Linear API token owner). To assign them to a different user:

- **Per-issue:** Use `--assignee "Display Name"` or `--assignee <uuid>` with `/tm-issue-create`.
- **Globally:** Add `issue_defaults.assignee_id` and `issue_defaults.assignee_name` to the config file. All new issues and review sub-issues will use this default unless overridden with `--assignee`.

## Architecture

```
commands/        Slash commands (markdown with YAML frontmatter)
references/      Shared workflow logic referenced by commands
scripts/         Python CLI scripts (thin wrappers over the backend)
taskmanager/     Core Python package
  config.py        Config file management
  models.py        Data classes (Issue, Project, Status, Label, etc.)
  backends/
    base.py        TaskBackend protocol (interface)
    linear.py      Linear GraphQL implementation
tests/           pytest test suite
```

The plugin is backend-agnostic. All task operations go through the `TaskBackend` protocol. To add support for Jira, GitHub Issues, or another tracker, implement the protocol in `taskmanager/backends/`.

## License

MIT
