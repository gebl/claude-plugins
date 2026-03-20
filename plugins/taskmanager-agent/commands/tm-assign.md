---
name: tm-assign
description: "Assign a specific issue to Claude and process it. Handles all issue states: In Review (PR checks), Blocked (review resolution), Todo (planning), In Progress (execution). Delegates to process-flow for action."
argument-hint: "<issue-id>"
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
---

# /tm-assign — Assign and Process a Specific Issue

Process a specific issue through its entire lifecycle. Handles all issue states by delegating to process-flow.md.

This is a self-contained command. It reads reference files for shared logic but does NOT invoke other slash commands.

All script invocations use the pattern:
```
${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/<script>.py <args>
```

---

## Step 1: Validate Arguments

`<issue-id>` is required. If not provided, stop and report: "Usage: /tm-assign <issue-id>"

---

## Step 2: Load Config

Read `~/.claude/taskmanager.yaml` per `${CLAUDE_PLUGIN_ROOT}/references/config.md`. Extract active projects, team ID, operator info, and project `local_path` values.

If the config does not exist or is missing required fields, stop and report: "Config not found or incomplete. Run `/tm-health` first."

---

## Step 3: Validate Issue

Fetch the issue:
```
${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_get_issue.py <issue-id>
```

If the script returns an error or the issue is not found, stop and report: "Issue <issue-id> not found."

Verify the issue's project appears in the config's `projects` list. If not, stop and report: "Issue is not in an active project."

---

## Step 4: Process the Issue

Follow `${CLAUDE_PLUGIN_ROOT}/references/process-flow.md` with the issue ID.

Process-flow determines the correct action based on the issue's current state:

- **In Review** → checks PR status (merged → close, comments → address feedback, etc.)
- **Blocked** → checks for resolved review sub-issues, unblocks and resumes if found
- **Todo or In Progress without plan** → creates an execution plan, blocks for review
- **In Progress with unchecked plan items** → executes the plan
- **In Progress with all items checked** → moves to In Review

Process-flow handles all status transitions, so no additional status changes are needed here.
