---
name: tm-health
description: "Validate and set up the task manager environment. Creates missing statuses and labels, caches workspace config. Run this first before using other tm-* commands."
allowed-tools:
  - Read
  - Write
  - Bash
  - Glob
---

# /tm-health — Setup & Validate Task Manager

This command bootstraps and validates the entire task manager environment. It must be run before any other `tm-*` command. It is safe to re-run at any time — all steps are idempotent.

All script invocations use the pattern:
```
${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/<script>.py <args>
```

> **Note:** The `.venv` is created and validated in Step 0 below. If any script invocation fails with a `ModuleNotFoundError`, re-run Step 0 to repair the environment.

---

## Step 0: Ensure Python Environment

**Goal:** Make sure the plugin's virtual environment and dependencies are installed so scripts can run.

> **Note:** A SessionStart hook runs `uv sync --frozen` automatically when a session begins. This step repairs the environment if something went wrong.

1. Verify `uv` is available:
   ```bash
   command -v uv
   ```
   If this fails (no output / non-zero exit), stop and report:
   > "`uv` (Python package manager) is required but not installed. Install it with: `curl -LsSf https://astral.sh/uv/install.sh | sh` — then restart your shell and re-run `/tm-health`."

2. Run from the plugin root:
   ```bash
   cd ${CLAUDE_PLUGIN_ROOT} && uv sync
   ```
   This creates the `.venv` (if missing), installs all dependencies, and installs the `taskmanager` package — all in one command. Unlike the SessionStart hook (which uses `--frozen` for speed), the health check omits `--frozen` so it can self-heal if dependencies changed.

   If this fails, stop and report:
   > "Failed to sync Python environment. Check that `uv.lock` exists in the plugin root."

3. Verify by running an actual script (not `python -c`, which can pass falsely due to CWD on `sys.path`):
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_get_user.py --help
   ```
   If this fails after `uv sync` succeeded, the `taskmanager` package was not installed — check that `uv.lock` contains `source = { editable = "." }` for the taskmanager-agent entry.

---

## Step 1: Discover Team

**Goal:** Confirm Linear connectivity and resolve the team to operate against.

1. Run `tm_get_user.py --query me` to verify API connectivity and retrieve the operator's user info (id, name, email). If this fails, stop and report: "Cannot connect to Linear. Check your LINEAR_TOKEN environment variable."

2. Auto-discover the team by running:
   ```
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_list_teams.py
   ```
   This returns all teams in the workspace as a JSON array of `{id, name, key}` objects.

   - **If exactly one team is returned:** use it automatically. Display: "Auto-discovered team: <team.name> (<team.key>)".
   - **If multiple teams are returned:** check if `~/.claude/taskmanager.yaml` already has a `team.id` that matches one of the returned teams. If so, use that team. Otherwise, present the list and ask the user to choose:
     > "Multiple teams found. Which team should Claude operate against?"
     > 1. <team.name> (<team.key>)
     > 2. <team.name> (<team.key>)
   - **If no teams are returned:** stop and report: "No teams found in your Linear workspace."

3. Once a team ID is confirmed, store it in memory as `<team-id>` for use in subsequent steps.

---

## Step 2: Discover & Create Statuses

**Goal:** Ensure all required workflow statuses exist for the team.

1. Run:
   ```
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_list_statuses.py --team-id <team-id>
   ```
   Collect the returned statuses. Index them by name (case-insensitive).

2. The required statuses and their expected types are:

   | Name        | Type      | Notes                        |
   |-------------|-----------|------------------------------|
   | Backlog     | backlog   | Standard Linear status       |
   | Todo        | unstarted | Standard Linear status       |
   | In Progress | started   | Standard Linear status       |
   | In Review   | started   | May need to be created       |
   | Done        | completed | Standard Linear status       |
   | Blocked     | started   | Likely needs to be created   |

3. For each required status that is **missing** by name (case-insensitive match):
   - **"In Review"** (if missing):
     ```
     ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_create_status.py \
       --team-id <team-id> \
       --name "In Review" \
       --type started \
       --color "#F59E0B"
     ```
   - **"Blocked"** (if missing):
     ```
     ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_create_status.py \
       --team-id <team-id> \
       --name "Blocked" \
       --type started \
       --color "#95a2b3"
     ```

4. If any statuses were created, re-run `tm_list_statuses.py --team-id <team-id>` to get the final authoritative list.

5. Build a status map: `{ "backlog": <id>, "todo": <id>, "in_progress": <id>, "in_review": <id>, "done": <id>, "blocked": <id> }`. This will be written to config in Step 9.

---

## Step 3: Discover & Create Labels

**Goal:** Ensure all required issue and project labels exist.

### Issue Labels

1. Run:
   ```
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_list_labels.py --scope issue
   ```
   Index by name (case-insensitive).

2. If **"Claude"** is missing:
   ```
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_create_label.py \
     --name "Claude" \
     --color "#6366F1" \
     --scope issue
   ```

3. If **"Review"** is missing:
   ```
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_create_label.py \
     --name "Review" \
     --color "#F59E0B" \
     --scope issue
   ```

### Project Labels

4. Run:
   ```
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_list_labels.py --scope project
   ```
   Index by name (case-insensitive).

5. If **"Claude Active"** is missing:
   ```
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_create_label.py \
     --name "Claude Active" \
     --color "#6366F1" \
     --scope project \
     --description "Projects that Claude agent is allowed to work on"
   ```

6. After any creations, re-run the respective `tm_list_labels.py` calls to get final IDs. Record all label IDs for the config.

---

## Step 4: Get Operator Info

**Goal:** Record the authenticated user's identity in config.

1. Run (this was already done in Step 1, reuse the result):
   ```
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_get_user.py --query me
   ```

2. Extract `id` and `name` from the response. These become `operator.id` and `operator.name` in the config.

---

## Step 5: Discover Active Projects

**Goal:** Build the list of projects Claude is authorized to work on.

1. Run:
   ```
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_list_projects.py --label "Claude Active"
   ```
   This returns all projects tagged with the "Claude Active" label.

2. For each project returned, run:
   ```
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_get_project_links.py --project-id <project-id>
   ```
   Scan the returned links for one with `label` equal to `"Repository"` (case-insensitive). Extract its `url` as the repo URL.

3. Build a project entry for each project:
   ```yaml
   - id: <project-id>
     name: <project-name>
     repo: <repo-url>        # null if no "Repository" link found
     local_path: null        # filled in manually or by worktree setup
   ```

4. If an existing config already has `local_path` values for a project (matched by `id`), **preserve** those values — do not overwrite with `null`.

5. Projects without a "Repository" link are treated as **document-only projects** and will be skipped in Steps 6 and 7.

---

## Step 6: Validate Git Access

**Goal:** Confirm Claude can reach each project's repository.

1. For each project with a non-null `repo` URL, run:
   ```
   git ls-remote <repo-url> HEAD
   ```

2. If the command exits 0: mark the project `git_accessible: true`.

3. If the command fails (non-zero exit or timeout): mark `git_accessible: false` and record the error output. Report this as a **warning** — do not stop the health check. Example warning:
   > "WARNING: Cannot access repo for project '<project-name>': <error>. Check SSH keys or repo URL."

---

## Step 7: Clean Up Merged Worktrees

**Goal:** Remove git worktrees for branches that have already been merged.

1. For each project where `local_path` is set and exists on disk, run:
   ```
   git -C <local_path> worktree list --porcelain
   ```

2. Parse the output to get each worktree's path and branch. Skip the **main worktree** (the first entry, which has no `branch` line or is the primary checkout).

3. For each non-main worktree with a branch name `<branch>`:
   ```
   git -C <local_path> branch --merged main
   ```
   Check if `<branch>` appears in the output.

4. If the branch has been merged:
   ```
   git -C <local_path> worktree remove <worktree-path>
   ```
   Record the removed path.

5. If the branch has **not** been merged, skip it — do not remove.

6. If `local_path` does not exist on disk, skip with a note: "local_path set but directory not found for project '<project-name>'."

---

## Step 8: Detect Stale Issues

**Goal:** Surface in-progress issues that have gone quiet.

1. Run:
   ```
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_list_issues.py --status "In Progress"
   ```
   Collect all issues currently in the "In Progress" status.

2. For each issue, run:
   ```
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_list_comments.py <issue-id>
   ```
   Find the most recent comment's `createdAt` timestamp.

3. If the issue has no comments at all, use the issue's own `updatedAt` timestamp as the last activity time.

4. Compare last activity time against `now - stale_threshold_hours`. Read `stale_threshold_hours` from the existing config if present; default to `72` hours (3 days) if not set.

5. If the last activity is older than the threshold, add the issue to the stale list with its id, title, assignee, and last activity timestamp.

6. Report stale issues as **warnings** — they are informational and do not block the health check.

---

## Step 9: Write Config

**Goal:** Persist all discovered data to `~/.claude/taskmanager.yaml`.

Write (or overwrite) `~/.claude/taskmanager.yaml` with the following structure. Preserve any existing fields not mentioned here (e.g., `stale_threshold_hours` set by the user).

```yaml
backend: linear

last_health_check: <ISO 8601 timestamp, e.g. 2026-03-17T14:30:00Z>

operator:
  id: <user-id>
  name: <user-name>

team:
  id: <team-id>
  name: <team-name>

statuses:
  backlog: <status-id>
  todo: <status-id>
  in_progress: <status-id>
  in_review: <status-id>
  done: <status-id>
  blocked: <status-id>

labels:
  issue:
    claude: <label-id>
    review: <label-id>
  project:
    claude_active: <label-id>

projects:
  - id: <project-id>
    name: <project-name>
    repo: <repo-url-or-null>
    local_path: <local-path-or-null>
    git_accessible: <true-or-false>

stale_threshold_hours: 72  # preserve existing value if set

issue_defaults:              # preserve existing values if set
  assignee_id: <user-id>    # optional: default assignee for new issues
  assignee_name: <name>     # optional: display name (informational)
```

When merging with an existing config:
- Always update: `last_health_check`, `operator`, `team`, `statuses`, `labels`, `projects` (repo, git_accessible).
- Preserve: `stale_threshold_hours`, `issue_defaults`, `local_path` per project, any user-added fields.

---

## Step 10: Report Summary

**Goal:** Give the operator a clear, scannable summary of health check results.

Display a report in this format:

```
/tm-health complete
==================

Team:          <team-name> (<team-id>)
Operator:      <operator-name> (<operator-id>)
Config:        ~/.claude/taskmanager.yaml

Statuses
  Found:       <comma-separated list of found status names>
  Created:     <comma-separated list, or "none">

Labels
  Issue:       <found/created summary>
  Project:     <found/created summary>

Active Projects (<N> total)
  <project-name>   repo: <url-or-none>   git: OK / FAILED
  ...

Worktrees Cleaned
  <path> (branch: <branch>)   or   "none"

Stale Issues (<N> found)
  <issue-id>: <title> — last activity <timestamp>   or   "none"

Warnings
  <any warnings from Steps 6–8, or "none">
```

If there are any failures (git access failures, worktree errors), list them clearly under "Warnings". The health check itself should never hard-fail unless Step 1 (connectivity) fails — all other problems are surfaced as warnings.
