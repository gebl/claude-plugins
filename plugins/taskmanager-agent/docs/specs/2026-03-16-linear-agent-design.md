# Linear Agent for Claude Code

**Date:** 2026-03-16
**Status:** Approved (rev 2 — post spec review)

## Overview

A Claude Code plugin that pulls tasks from Linear, plans and executes work, and updates Linear with progress. Supports both code tasks (worktree + PR) and non-code tasks (research, planning → Linear documents). Designed as a composable command suite where each command is independently useful and an orchestrator loops through the backlog.

## Goals

- Pull the next highest-priority "Todo" issue from Linear
- Create a plan, post it as a comment, check off items as work progresses
- For code tasks: create a git worktree, do the work, submit a PR
- For non-code tasks: produce Linear documents or comments
- Create sub-issues for discovered out-of-scope work (max 1 level deep)
- Create review issues assigned to the user when human input is needed
- Update Linear statuses throughout the lifecycle
- Validate setup via `/linear-health`

## Linear Conventions

### Status Flow

```
Backlog → Todo → In Progress → In Review → Done
                           ↘ Blocked
```

- **Backlog**: Unrefined work, not yet ready for Claude
- **Todo**: Available for Claude to pick up
- **In Progress**: Claude is actively working on it
- **In Review**: PR created or document produced, waiting for human review
- **Blocked**: Claude can't proceed — comment explains why, often linked to a Review issue
- **Done**: Completed (set by human after merging PR or accepting output)

### Labels & Statuses (all auto-created by `/linear-health`)

All required Linear structures are created automatically. No manual setup needed:

- **"Blocked" status** (type: started) — created via `scripts/create_workflow_state.py`
- **"Claude Active" project label** — created via `scripts/create_project_label.py`
- **Review** (issue label): Applied to issues needing human input. Created via MCP `create_issue_label`.
- **Claude** (issue label): Applied to issues Claude has worked on. Created via MCP `create_issue_label`.

### Project Repo Convention

Each Linear project that involves code should have a link resource pointing to its git repo URL. This is the source of truth — the config file caches it.

Repo links are stored as Linear entity external links on the project (via `scripts/create_project_link.py`), with the label "Repository". `/linear-health` reads project resources and identifies repo links by this label.

Projects without a "Repository" link are treated as non-code projects (document mode).

Setting a repo link:
- Via `/linear-project-create --repo <url>` (creates the link in Linear)
- Manually in Linear UI (add a link resource labeled "Repository" to the project)

### Issue Pull Logic

1. Query all issues with status "Todo", ordered by priority (Urgent > High > Normal > Low)
2. Filter to projects listed in config (those labeled "Claude Active" in Linear)
3. Skip issues where `blockedBy` relations point to unfinished issues
4. Optionally filter by project name (passed as argument)
5. Take the top one

## Plugin Architecture: Shared References

Claude Code commands cannot invoke other commands programmatically. To avoid duplicating logic between standalone commands and the orchestrators (`/work-backlog`, `/linear-assign`), the plugin uses a **shared references** pattern:

```
linear-agent/
├── plugin.json
├── commands/
│   ├── linear-health.md        # standalone command
│   ├── linear-next.md          # standalone command
│   ├── linear-plan.md          # standalone command
│   ├── linear-work.md          # standalone command
│   ├── linear-assign.md        # orchestrator (uses references)
│   ├── linear-update.md        # standalone command
│   ├── linear-project-create.md
│   ├── linear-issue-create.md
│   ├── linear-issues.md
│   └── work-backlog.md         # orchestrator (uses references)
├── references/
│   ├── config.md               # how to read/write ~/.claude/linear-worker.yaml
│   ├── next-flow.md            # issue selection logic
│   ├── plan-flow.md            # planning logic
│   ├── work-flow.md            # execution logic (code + document modes)
│   ├── pr-creation.md          # Forgejo/GitHub PR creation details
│   └── review-issue-flow.md    # creating review sub-issues
├── scripts/                    # Python scripts for API operations not in MCP
│   ├── create_workflow_state.py    # Create a workflow state (status) on a team
│   ├── create_project_label.py     # Create a project-level label
│   ├── create_project_link.py      # Add a link resource to a project
│   ├── get_project_links.py        # Read link resources from a project
│   └── create_forgejo_pr.py        # Create a pull request on Forgejo
└── docs/
    └── specs/
        └── 2026-03-16-linear-agent-design.md
```

**How it works:**
- Each reference file (e.g., `references/plan-flow.md`) contains the full implementation instructions for one flow
- Standalone commands (e.g., `commands/linear-plan.md`) say: "Read and follow `${CLAUDE_PLUGIN_ROOT}/references/plan-flow.md`"
- Orchestrators (e.g., `commands/work-backlog.md`) say: "For each issue, follow `${CLAUDE_PLUGIN_ROOT}/references/next-flow.md`, then `plan-flow.md`, then `work-flow.md`"
- Both standalone and orchestrator invoke the exact same logic — zero duplication

## Command Suite

### `/linear-health`

**Purpose:** Setup validation, cache refresh, and full self-healing.

**Actions:**
- Queries team, statuses, labels, projects
- **Auto-creates all missing structures:**
  - "Blocked" status → `scripts/create_workflow_state.py --name Blocked --type started --team <id> --color "#95a2b3"`
  - "Claude Active" project label → `scripts/create_project_label.py --name "Claude Active" --color "#6366F1"`
  - "Claude" issue label → MCP `create_issue_label`
  - "Review" issue label → MCP `create_issue_label`
- Queries projects labeled "Claude Active", reads their link resources via `scripts/get_project_links.py`, identifies repo URLs by label "Repository"
- Validates git access to each active project's repo URL (`git ls-remote`)
- Cleans up worktrees for merged PRs
- Detects stale "In Progress" issues (configurable threshold, default >4 hours with no recent comment) and reports them
- Writes everything to `~/.claude/linear-worker.yaml`
- Reports what it found, created, validated, and any warnings

**Config file (`~/.claude/linear-worker.yaml`):**
```yaml
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

# Human operator — used as assignee for review issues
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
    repo: null  # non-code project

clone_base: ~/Projects
stale_threshold_hours: 4
last_health_check: 2026-03-16T10:00:00Z
```

### `/linear-project-create <name> [--repo <url>] [--description <text>]`

**Purpose:** Create a new Linear project and mark it active for Claude.

**Flow:**
1. Creates a new project in the Landq team (via MCP `save_project`)
2. Applies the "Claude Active" project label
3. If `--repo` is provided, adds it as a link resource on the project via `scripts/create_project_link.py --project <id> --label "Repository" --url <repo-url>`
4. Updates `~/.claude/linear-worker.yaml` with the new project entry (including repo URL)
5. Displays the created project summary

### `/linear-issue-create <title> --project <name> [--priority <level>] [--description <text>]`

**Purpose:** Create a new issue in a project.

**Flow:**
1. Validates the project exists in config and is Claude Active
2. Creates the issue with the given title, priority (default: Normal), and description
3. Sets status to "Todo" (ready for Claude to pick up)
4. Displays the created issue ID and summary

### `/linear-issues [--project <name>] [--status <status>]`

**Purpose:** Show issues that could be assigned to Claude or are currently in flight.

**Flow:**
1. Queries issues from Claude Active projects (listed in config)
2. Default filter: status "Todo" or "Backlog" (i.e., available work)
3. Optional `--project` and `--status` filters
4. Displays a table: ID, title, priority, project, status
5. Useful for reviewing what's in the queue before running `/work-backlog`

### `/linear-assign <issue-id>`

**Purpose:** Assign an issue to Claude and begin the next action. This is the "point Claude at a specific issue" entry point.

**Implementation:** Self-contained skill that reads shared reference files. Does NOT call other commands.

**Flow:**
1. Read config per `${CLAUDE_PLUGIN_ROOT}/references/config.md`
2. Fetch the issue, validate it's in a Claude Active project
3. Apply "Claude" label, set status → "In Progress"
4. List comments on the issue, look for an existing plan comment (identified by `## Execution Plan` heading)
5. Determine next action:
   - **No plan comment** → follow `${CLAUDE_PLUGIN_ROOT}/references/plan-flow.md`, then `work-flow.md`
   - **Plan exists with unchecked items** → follow `${CLAUDE_PLUGIN_ROOT}/references/work-flow.md`
   - **Plan exists, all items checked** → set status → "In Review", post summary

### `/linear-next [--project <name>]`

**Purpose:** Pull the next issue to work on (interactive, standalone).

**Flow:**
1. Read config per `${CLAUDE_PLUGIN_ROOT}/references/config.md`
2. Follow `${CLAUDE_PLUGIN_ROOT}/references/next-flow.md`
3. Display the issue summary: title, priority, project, description preview
4. Ask: "Work on this? (y/n)"
5. On yes: apply "Claude" label, set status → "In Progress"
6. Display the issue ID for manual use with `/linear-plan` or `/linear-assign`

### `/linear-plan <issue-id>`

**Purpose:** Analyze an issue and create an execution plan (standalone).

**Flow:** Follows `${CLAUDE_PLUGIN_ROOT}/references/plan-flow.md`

### `/linear-work <issue-id>`

**Purpose:** Execute the plan for an issue (standalone).

**Flow:** Follows `${CLAUDE_PLUGIN_ROOT}/references/work-flow.md`

### `/linear-update <issue-id> <status> [--comment <message>]`

**Purpose:** Manual status update with optional comment.

**Flow:**
1. Read config, validate status name against cached statuses
2. Update the issue status via `save_issue`
3. Optionally post a comment via `save_comment`

### `/work-backlog [--project <name>] [--limit <n>]`

**Purpose:** Orchestrator loop. Processes the backlog autonomously.

**Implementation:** Self-contained skill that reads shared reference files. Does NOT call other commands.

**Flow:**
1. Read config per `${CLAUDE_PLUGIN_ROOT}/references/config.md`
2. Validate config is fresh (warn if last health check >24 hours ago)
3. Loop:
   a. Follow `${CLAUDE_PLUGIN_ROOT}/references/next-flow.md` (skip the interactive prompt — auto-select)
   b. If no issues found → exit loop
   c. Apply "Claude" label, set status → "In Progress"
   d. Follow `${CLAUDE_PLUGIN_ROOT}/references/plan-flow.md`
   e. If issue was blocked during planning → continue to next
   f. Follow `${CLAUDE_PLUGIN_ROOT}/references/work-flow.md`
   g. Increment counter
   h. If counter hits `--limit` → exit loop
   i. Every 3 issues: display summary of progress, confirm to continue
4. On exit: display final summary (issues completed, PRs created, issues blocked)

**Default limit:** None (runs until backlog is empty), but confirms every 3 issues.

## Reference File Details

### `references/config.md`

Instructions for reading `~/.claude/linear-worker.yaml`:
- Read the file using the Read tool
- Parse the YAML content
- If file is missing or `last_health_check` is >24 hours old, warn and suggest running `/linear-health`
- Extract team, statuses, labels, projects, operator info

### `references/next-flow.md`

Issue selection logic:
1. Query `list_issues` with state "Todo", ordered by priority
2. For each candidate issue, check its project is in the config's active projects list
3. For each candidate, call `get_issue` with `includeRelations: true` to check `blockedBy`
4. Skip issues blocked by non-completed issues
5. Apply optional project filter if provided
6. Return the first qualifying issue (or null if none found)

### `references/plan-flow.md`

Planning logic:
1. Fetch the full issue via `get_issue` (include relations)
2. Read all comments via `list_comments`
3. Look up the project in config to determine code vs. document mode
4. **Code mode** (repo exists):
   - Navigate to the local repo path (clone via `git clone <repo> <clone_base>/<name>` if no `local_path`)
   - Explore the codebase to understand what's needed
   - Create a markdown checklist plan
5. **Document mode** (no repo):
   - Analyze the issue requirements
   - Create a plan focused on research/writing/planning outputs
6. Post the plan as a comment with heading `## Execution Plan` followed by checklist items
7. If the issue is vague or needs clarification:
   - Follow `${CLAUDE_PLUGIN_ROOT}/references/review-issue-flow.md`
8. Create sub-issues (via `save_issue` with `parentId`) for any discovered out-of-scope work (max 1 level — never create children of children)

### `references/work-flow.md`

Execution logic:
1. List comments on the issue, find the one starting with `## Execution Plan`
2. Parse the checklist items (lines matching `- [ ]` or `- [x]`)
3. Determine mode from project config (repo exists → code mode, else → document mode)

**Code mode:**
4. Navigate to the project's local repo path
5. Use Linear's suggested branch name from `get_issue` response, or construct as `<team-key-lower>-<number>-<slug>` (e.g., `lan-42-add-rss-feed`)
6. Create a git worktree: `git worktree add .worktrees/<branch> -b <branch>`
7. Work through each unchecked item:
   - Do the work in the worktree
   - Edit the plan comment via `save_comment` (with `id`) to check off the item (`- [x]`)
   - If blocked: follow `review-issue-flow.md`, set status → "Blocked", stop
8. On completion:
   - Commit changes with a descriptive message
   - Push: `git push origin <branch>` (using token auth if needed)
   - Create PR per `${CLAUDE_PLUGIN_ROOT}/references/pr-creation.md`
   - Link the PR URL on the Linear issue via `save_issue` with `links` field
   - Set status → "In Review"
   - Post a summary comment

**Document mode:**
4. Work through each unchecked item:
   - Research, analyze, write as needed
   - Create a Linear document via `create_document` attached to the project
   - Edit the plan comment to check off items
   - If blocked: follow `review-issue-flow.md`, set status → "Blocked", stop
5. On completion:
   - Post final summary comment
   - Set status → "In Review"

### `references/pr-creation.md`

PR creation for Forgejo and GitHub:

**Determining the git host:**
- Parse the repo URL from config
- If host contains "forgejo" or matches a known Forgejo instance → `scripts/create_forgejo_pr.py`
- If host contains "github.com" → GitHub CLI (`gh`)
- Default base branch: `main`

**Forgejo PR creation:**
```
python scripts/create_forgejo_pr.py \
  --repo-url <repo-url> \
  --branch <branch-name> \
  --title "<issue-key>: <issue-title>" \
  --body "Resolves <issue-url>\n\n<summary>" \
  [--base main]
```

**GitHub PR creation:**
```bash
gh pr create --title "<issue-key>: <issue-title>" \
  --body "Resolves <issue-url>\n\n<summary>" \
  --head "<branch-name>" --base "main"
```

**Prerequisites:** `$FORGEJO_TOKEN` env var for Forgejo repos. `gh` CLI authenticated for GitHub repos. `/linear-health` validates these are available for each active project's host.

### `references/review-issue-flow.md`

Creating review sub-issues when human input is needed:

1. Create a new issue via `save_issue`:
   - Title: `[Review] <parent-key>: <specific question>`
   - Team: from config
   - Parent: the current issue ID (`parentId`)
   - Assignee: operator ID from config
   - Labels: ["Review"]
   - Status: "Todo"
   - Description: context about what Claude found and the specific questions needing answers
2. Set the parent issue status → "Blocked"
3. Post a comment on the parent issue: "Blocked — waiting for human input on <review-issue-key>: <question summary>"

## Edge Cases & Guardrails

### Stale In-Progress Detection
`/linear-health` and `/work-backlog` detect issues stuck in "In Progress" for longer than `stale_threshold_hours` (default: 4, configurable in YAML) with no recent comment. Reports them so you can reset to "Todo" or investigate.

### Dependency Awareness
Issue selection (in `next-flow.md`) checks `blockedBy` relations via `get_issue` with `includeRelations: true`. Issues blocked by unfinished work are skipped.

### Sub-Issue Depth
Maximum 1 level of sub-issue creation. Claude does not create children of sub-issues to prevent runaway decomposition.

### Plan Comment Convention
Plan comments are identified by the `## Execution Plan` heading. This heading must be the first line of the comment body. Checklist items follow as `- [ ] item` or `- [x] item`. This convention is used by `work-flow.md` to discover and update the plan.

### Worktree Cleanup
`/linear-health` lists worktrees, checks if their branches have been merged into the default branch, and removes merged worktrees via `git worktree remove`.

### Repo Cloning
If a project has a `repo` URL but no `local_path`, Claude clones it to `<clone_base>/<repo-name>` and updates `local_path` in the config file.

### Error Recovery
- Linear API unreachable: stop and report
- Git push fails: set issue to "Blocked" with error details in comment
- PR creation fails: leave branch pushed, set "Blocked", report error
- Config file missing: error with "Run /linear-health first"

### Concurrency
If two sessions run `/work-backlog` simultaneously, both could pick the same "Todo" issue. The status update to "In Progress" serves as a loose lock — the second session would see the issue is no longer "Todo" on its next query. A small race window exists but is acceptable for single-user use.

## v2 Considerations (Not in Scope)

- `/linear-revise <issue-id>`: Read PR review comments and make fixes in existing worktree
- Smart resume: pick up mid-checklist instead of restarting
- Configurable sub-issue depth
- Token/cost budget tracking
- Cron-based autonomous mode (layer on top of `/work-backlog`)
- Multiple team support
- Branch name conflict detection and resolution

## Python Scripts (Linear GraphQL API)

The Linear MCP plugin covers most operations, but 4 actions require direct GraphQL API calls. These are implemented as focused Python scripts under `scripts/`, each doing exactly one thing.

**Environment:** `$LINEAR_TOKEN` env var (set in `~/.zshrc`). All scripts use `httpx` for HTTP and output JSON to stdout.

### `scripts/create_workflow_state.py`

Creates a workflow state (status) on a team.

```
Usage: python scripts/create_workflow_state.py --team-id <uuid> --name <name> --type <type> --color <hex>
Output: {"id": "<uuid>", "name": "Blocked", "type": "started"}
```

GraphQL mutation: `workflowStateCreate(input: {teamId, name, type, color})`

Types: `backlog`, `unstarted`, `started`, `completed`, `canceled`

### `scripts/create_project_label.py`

Creates a project-level label.

```
Usage: python scripts/create_project_label.py --name <name> [--color <hex>] [--description <text>]
Output: {"id": "<uuid>", "name": "Claude Active"}
```

GraphQL mutation: `projectLabelCreate(input: {name, color, description})`

### `scripts/create_project_link.py`

Adds a link resource (entity external link) to a project.

```
Usage: python scripts/create_project_link.py --project-id <uuid> --label <label> --url <url>
Output: {"id": "<uuid>", "label": "Repository", "url": "https://..."}
```

GraphQL mutation: `entityExternalLinkCreate(input: {projectId, label, url})`

### `scripts/get_project_links.py`

Reads link resources from a project.

```
Usage: python scripts/get_project_links.py --project-id <uuid>
Output: [{"id": "<uuid>", "label": "Repository", "url": "https://..."}]
```

GraphQL query: `project(id: ...) { externalLinks { nodes { id label url } } }`

### `scripts/create_forgejo_pr.py`

Creates a pull request on a Forgejo instance.

```
Usage: python scripts/create_forgejo_pr.py --repo-url <url> --branch <branch> --title <title> --body <body> [--base main]
Output: {"number": 42, "html_url": "https://forgejo.bishop.landq.net/Anvil/blog/pulls/42"}
```

Parses `<owner>` and `<repo>` from the repo URL path segments. Uses `$FORGEJO_TOKEN` for auth. Calls `POST /api/v1/repos/{owner}/{repo}/pulls`.

### Script conventions

- Linear scripts read `$LINEAR_TOKEN` from environment; Forgejo scripts read `$FORGEJO_TOKEN`
- All scripts exit 0 on success, non-zero on error
- All scripts output JSON to stdout, errors to stderr
- No interactive prompts — fully scriptable
- Minimal dependencies: `httpx` only (installed in plugin's venv)

## Implementation Notes

This will be built as a Claude Code plugin with:
- Commands in `commands/` directory (one `.md` file per command)
- Shared logic in `references/` directory (one `.md` file per flow)
- Python scripts in `scripts/` for Linear API operations not covered by the MCP
- `plugin.json` manifest registering all commands
- Linear MCP tools for most Linear interactions
- Git operations via Bash tool
- PR creation via `scripts/` (Forgejo) or `gh` CLI (GitHub)
- Config persisted to `~/.claude/linear-worker.yaml`

**Environment variables required:**
- `$LINEAR_TOKEN` — Linear API key (for Python scripts)
- `$FORGEJO_TOKEN` — Forgejo API key (for PR creation on Forgejo repos)

The plugin lives at `~/Projects/linear-agent` and is registered in Claude Code's plugin config.
