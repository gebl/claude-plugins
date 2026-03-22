---
name: tm-next
description: "Pull the next work item. First processes In Review issues (checks PR merge/comments), then unblocks resolved review sub-issues, resumes In Progress issues, then falls back to the highest-priority Todo issue. Filters to active projects, skips blocked issues."
argument-hint: "[--project <name>]"
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
---

# /tm-next — Pull Next Work Item

Select the next work item and process it. Priority order:
0. In Review issues needing attention (PR merged, has comments, or closed)
1. Blocked issues with resolved review sub-issues
2. In Progress issues already claimed by Claude
3. Highest-priority Todo issue from the backlog
4. Conversation issues (projectless, assigned to operator) — only if `conversation_issues: true` in config

This is a self-contained command. It reads reference files for shared logic but does NOT invoke other slash commands.

All script invocations use the pattern:
```
${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/<script>.py <args>
```

---

## Step 1: Read Config

Read `~/.claude/taskmanager.yaml` per `${CLAUDE_PLUGIN_ROOT}/references/config.md`. Extract the list of active projects, the team ID, and the status/label IDs.

If the config does not exist or is missing required fields, stop and report: "Config not found or incomplete. Run `/tm-health` first."

---

## Step 2: Parse Arguments

If `--project <name>` was provided, validate that the named project appears in the active projects list from config. If the project is not found, stop and report: "Project '<name>' is not in the active projects list. Check your config or run `/tm-health`."

---

## Step 3: Select Next Issue

Follow `${CLAUDE_PLUGIN_ROOT}/references/next-flow.md` with the project filter if provided.

If no eligible issues are found, report: "No eligible issues found. All issues may be blocked or the backlog is empty." and stop.

---

## Step 4: Display and Process

Display the selected issue:

```
Next issue: <issue-id> — <title>
Project:    <project-name>
Priority:   <urgent | high | normal | low>
Status:     <current status>

Description:
<issue description, truncated to ~300 chars if long>
```

Then follow `${CLAUDE_PLUGIN_ROOT}/references/process-flow.md` with the selected issue ID.

Process-flow handles all status transitions and actions based on the issue's current state.
