---
name: tm-issue-create
description: "Create a new issue in an active project. Sets status to Todo so it's ready to be picked up."
argument-hint: "<title> --project <name> [--priority <level>] [--description <text>]"
allowed-tools:
  - Read
  - Bash
---

# /tm-issue-create — Create a New Issue

Create a new Linear issue in an active project with status set to Todo.

All script invocations use the pattern:
```
${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/<script>.py <args>
```

---

## Step 1: Validate Arguments

`<title>` and `--project <name>` are both required. If either is missing, stop and report:

```
Usage: /tm-issue-create <title> --project <name> [--priority <level>] [--description <text>]
```

Valid priority levels: `urgent`, `high`, `normal` (default), `low`

If `--priority` is provided and is not one of the valid values, stop and report:

```
Invalid priority: '<value>'. Must be one of: urgent, high, normal, low
```

---

## Step 2: Read Config

Read `~/.claude/taskmanager.yaml` per `${CLAUDE_PLUGIN_ROOT}/references/config.md`. Extract the active projects list and team ID.

If the config does not exist or is missing required fields, stop and report: "Config not found or incomplete. Run `/tm-health` first."

---

## Step 3: Validate Project

Check that the provided project name matches an entry in the active projects list (case-insensitive comparison). If not found, stop and report:

```
Project '<name>' is not in the active projects list.
Active projects: <comma-separated list of project names>
```

---

## Step 4: Map Priority

Map the priority name to its numeric value:

| Name    | Value |
|---------|-------|
| urgent  | 1     |
| high    | 2     |
| normal  | 3     |
| low     | 4     |

If `--priority` was not provided, default to `normal` (3).

---

## Step 5: Create the Issue

Run:

```
${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_issue.py \
  --title <title> \
  --team <team-id> \
  --project <project-name> \
  --state Todo \
  --priority <n> \
  [--description <text>]
```

Include `--description <text>` only if it was provided. If the script returns an error, report it and stop.

Capture the returned issue ID from the script output.

---

## Step 6: Display Created Issue

```
Created: <issue-id> — <title>
Project: <project-name>
Status:  Todo
Priority: <urgent | high | normal | low>

Next steps:
  /tm-next --project "<project-name>"   — pick up the next issue from this project
  /tm-plan <issue-id>                   — create an execution plan for this issue
```
