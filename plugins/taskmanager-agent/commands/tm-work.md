---
name: tm-work
description: "Execute the plan for an issue. For code tasks: creates a git worktree, works through the checklist, creates a PR. For non-code tasks: creates documents. Updates plan comment as items complete."
argument-hint: "<issue-id>"
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
---

# /tm-work — Execute Issue Plan

Execute the plan for an issue, working through each checklist item and updating the plan comment as items complete.

All script invocations use the pattern:
```
${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/<script>.py <args>
```

---

## Step 1: Validate Arguments

`<issue-id>` is required. If not provided, stop and report: "Usage: /tm-work <issue-id>"

---

## Step 2: Read Config

Read `~/.claude/taskmanager.yaml` per `${CLAUDE_PLUGIN_ROOT}/references/config.md`. Extract active projects, team ID, operator info, and project `local_path` values.

If the config does not exist or is missing required fields, stop and report: "Config not found or incomplete. Run `/tm-health` first."

---

## Step 3: Execute Work Flow

Follow `${CLAUDE_PLUGIN_ROOT}/references/work-flow.md` for the full execution procedure.

The work flow covers:
- Fetching the issue and locating the plan comment (a checklist comment posted by `/tm-plan`)
- Determining the task type: **code task** (project has a repo) or **non-code task** (document-only project)
- **Code tasks:** creating a git worktree for the issue branch, working through each checklist item in the plan, committing changes, and opening a pull request when complete
- **Non-code tasks:** creating Linear documents or other artifacts per the checklist items
- Marking each checklist item complete by updating the plan comment via `tm_save_comment.py` as work progresses
- Setting issue status to **"In Review"** and applying the **"Review"** label when all items are complete

Refer to the work-flow reference for exact script invocations, worktree setup, PR creation rules, and comment update formatting.
