---
name: tm-issue-create
description: "Create a new issue in an active project. Sets status to Todo so it's ready to be picked up."
argument-hint: "<title> --project <name> [--priority <level>] [--description <text>] [--assignee <name-or-id>]"
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
Usage: /tm-issue-create <title> --project <name> [--priority <level>] [--description <text>] [--assignee <name-or-id>]
```

Valid priority levels: `urgent`, `high`, `normal` (default), `low`

If `--priority` is provided and is not one of the valid values, stop and report:

```
Invalid priority: '<value>'. Must be one of: urgent, high, normal, low
```

`--assignee <name-or-id>` is optional. Accepts a display name (e.g. `"Gabriel Lawrence"`) or a Linear user UUID.

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

## Step 5: Resolve Assignee

Determine the assignee user ID to use:

1. If `--assignee` was provided:
   - If the value looks like a UUID (contains hyphens, 36 chars), use it directly as the assignee ID.
   - Otherwise, resolve the display name to a user ID:
     ```
     ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_get_user.py --query <assignee-value>
     ```
     Extract the `id` from the response. If the script returns an error (user not found), stop and report:
     ```
     User not found: '<assignee-value>'. Check the display name or use a UUID.
     ```

2. If `--assignee` was NOT provided, check the config for `issue_defaults.assignee_id`. If present, use that as the assignee ID.

3. If neither `--assignee` nor `issue_defaults.assignee_id` is set, do not pass `--assignee` to the script.

---

## Step 6: Create the Issue

Run:

```
${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_issue.py \
  --title <title> \
  --team <team-id> \
  --project <project-name> \
  --state Todo \
  --priority <n> \
  [--description <text>] \
  [--assignee <resolved-user-id>]
```

Include `--description <text>` only if it was provided. Include `--assignee <resolved-user-id>` only if an assignee was resolved in Step 5. If the script returns an error, report it and stop.

Capture the returned issue ID from the script output.

---

## Step 7: Display Created Issue

```
Created: <issue-id> — <title>
Project:  <project-name>
Status:   Todo
Priority: <urgent | high | normal | low>
Assignee: <assignee-name or "none">
```

Show `Assignee:` only if an assignee was set. If the assignee was resolved from a display name, show the name. If from config default, show the `issue_defaults.assignee_name` value. If from a UUID, show the UUID.

```
Next steps:
  /tm-next --project "<project-name>"   — pick up the next issue from this project
  /tm-plan <issue-id>                   — create an execution plan for this issue
```
