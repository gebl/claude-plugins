---
name: tm-update
description: "Manually update an issue's status with an optional comment. Useful for re-queuing blocked issues or manual status changes."
argument-hint: "<issue-id> <status> [--comment <message>]"
allowed-tools:
  - Read
  - Bash
---

# /tm-update — Manually Update Issue Status

Manually set an issue's status and optionally post a comment explaining the change.

All script invocations use the pattern:
```
${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/<script>.py <args>
```

---

## Step 1: Validate Arguments

Both `<issue-id>` and `<status>` are required. If either is missing, stop and report:

```
Usage: /tm-update <issue-id> <status> [--comment <message>]
```

Valid status values: `backlog`, `todo`, `in_progress`, `in_review`, `done`, `blocked`

If the provided status is not one of the valid values, stop and report:

```
Invalid status: '<value>'. Must be one of: backlog, todo, in_progress, in_review, done, blocked
```

---

## Step 2: Read Config

Read `~/.claude/taskmanager.yaml` per `${CLAUDE_PLUGIN_ROOT}/references/config.md`. Extract the status ID map and team ID.

If the config does not exist or is missing required fields, stop and report: "Config not found or incomplete. Run `/tm-health` first."

---

## Step 3: Update Issue Status

Map the provided status name to its display name for the API:

| Argument     | Display Name  |
|--------------|---------------|
| backlog      | Backlog       |
| todo         | Todo          |
| in_progress  | In Progress   |
| in_review    | In Review     |
| done         | Done          |
| blocked      | Blocked       |

Run:

```
${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_issue.py \
  --id <issue-id> \
  --state <display-name>
```

If the script returns an error, report it and stop.

---

## Step 4: Post Comment (if provided)

If `--comment <message>` was given, run:

```
${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_comment.py \
  --issue-id <issue-id> \
  --body <message>
```

If the script returns an error, report it as a warning but do not fail — the status update already succeeded.

---

## Step 5: Display Confirmation

```
Updated: <issue-id>
Status:  <display-name>
Comment: <message, or "none">
```
