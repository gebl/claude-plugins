# taskmanager-agent

A Claude Code plugin for autonomous task management. Pulls issues from your task tracker (currently Linear), creates execution plans, works through them via git worktrees and PRs, and updates statuses as work progresses.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (for dependency management)
- A Linear account with an API token

## Setup

1. **Set your Linear API token:**
   ```bash
   export LINEAR_TOKEN="lin_api_..."
   ```

2. **Install the plugin** (add to your Claude Code plugins or clone locally).

3. **Run the health check:**
   ```
   /tm-health
   ```
   This will:
   - Create the plugin's `.venv` and install dependencies
   - Verify Linear API connectivity
   - Discover/create required statuses and labels
   - Discover active projects
   - Validate git access
   - Write config to `~/.claude/taskmanager.yaml`

## Commands

| Command | Description |
|---------|-------------|
| `/tm-health` | Setup and validate the environment (run first) |
| `/tm-next` | Pull the next highest-priority issue |
| `/tm-assign <id>` | Assign a specific issue and work it to completion |
| `/tm-plan <id>` | Create an execution plan for an issue |
| `/tm-work <id>` | Execute the plan for an issue |
| `/tm-update <id> <status>` | Manually update an issue's status |
| `/tm-issues` | List issues from active projects |
| `/tm-issue-create <title>` | Create a new issue |
| `/tm-project-create <name>` | Create a new project |
| `/work-backlog` | Process the backlog autonomously |

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `LINEAR_TOKEN` | Yes | Linear API token |
| `FORGEJO_TOKEN` | For PRs | Forgejo/Gitea token for creating pull requests |

## Architecture

```
commands/     Claude Code slash commands (markdown + YAML frontmatter)
references/   Shared flow logic referenced by commands
scripts/      Python CLI scripts (thin wrappers over backend)
taskmanager/  Core Python package
  config.py     Config file management (~/.claude/taskmanager.yaml)
  models.py     Data classes (Issue, Project, Status, etc.)
  backends/
    base.py     TaskBackend protocol (interface for all backends)
    linear.py   Linear GraphQL implementation
tests/        pytest suite
```

The plugin is backend-agnostic. To add a new backend (e.g., Jira, GitHub Issues), implement the `TaskBackend` protocol in `taskmanager/backends/`.

## License

MIT
