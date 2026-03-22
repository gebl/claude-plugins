---
name: tm-issues
description: "Show issues from active projects. Defaults to Todo and Backlog status. Filter by project or status. Use --conversation to show projectless conversation issues."
argument-hint: "[--project <name>] [--status <status>] [--conversation]"
allowed-tools:
  - Read
  - Bash
---

# /tm-issues — List Issues from Active Projects

Display issues from active projects, sorted by priority. Defaults to showing Todo and Backlog issues. Use `--conversation` to show projectless conversation issues assigned to the operator.

All script invocations use the pattern:
```
${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/<script>.py <args>
```

---

## Step 1: Read Config

Read `~/.claude/taskmanager.yaml` per `${CLAUDE_PLUGIN_ROOT}/references/config.md`. Extract the active projects list and team ID.

If the config does not exist or is missing required fields, stop and report: "Config not found or incomplete. Run `/tm-health` first."

---

## Step 2: Parse Arguments

- If `--conversation` is provided, switch to conversation mode (see Step 3b).
- If `--project <name>` is provided, validate it against the active projects list (case-insensitive). If not found, stop and report:
  ```
  Project '<name>' is not in the active projects list.
  Active projects: <comma-separated list of project names>
  ```
- If `--status <status>` is provided, validate it is one of: `backlog`, `todo`, `in_progress`, `in_review`, `done`, `blocked`. If invalid, stop and report:
  ```
  Invalid status: '<value>'. Must be one of: backlog, todo, in_progress, in_review, done, blocked
  ```
- If neither flag is provided, default to fetching both **Todo** and **Backlog** issues.

---

## Step 3: Fetch Issues

Determine the set of projects to query: all active projects, or just the filtered one if `--project` was given.

For each project in the set, run `tm_list_issues.py` once per status to fetch:

**If a specific `--status` was given**, run once per project:
```
${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_list_issues.py \
  --project <project-name> \
  --status <status>
```

**If no `--status` was given (default: Todo + Backlog)**, run twice per project:
```
${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_list_issues.py \
  --project <project-name> \
  --status todo

${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_list_issues.py \
  --project <project-name> \
  --status backlog
```

Collect and deduplicate all returned issues (by issue ID) across all calls.

### Step 3b: Fetch Conversation Issues (if `--conversation`)

If `--conversation` was provided, fetch issues assigned to the operator that have no project:

```
${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_list_issues.py \
  --assignee <operator-id> \
  [--status <status>]
```

If no `--status` was given, run for both Todo and In Progress statuses.

Filter the results to only include issues where `project_id` is null (no project assigned). Skip Step 3 entirely when in conversation mode.

---

## Step 4: Sort Issues

Sort the collected issues by:
1. Priority ascending (1 = urgent first, 4 = low last, null/no priority last)
2. Creation date ascending (oldest first) as a tiebreaker

---

## Step 5: Display Results

If no issues were found, report: "No issues found matching the given filters."

Otherwise, display results as a markdown table:

```
| ID | Title | Priority | Project | Status |
|----|-------|----------|---------|--------|
| <issue-id> | <title> | <urgent/high/normal/low> | <project-name> | <status> |
...
```

Map numeric priority values to labels: 1 = urgent, 2 = high, 3 = normal, 4 = low. If priority is unset, display as `—`.

Include a summary line after the table:
```
Showing <N> issue(s) across <M> project(s).
```
