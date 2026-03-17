---
name: tm-assign
description: "Assign a specific issue to Claude and begin working on it. Automatically determines the next action: plan if no plan exists, execute if plan exists. This is the 'point Claude at a specific issue' entry point."
argument-hint: "<issue-id>"
---

# /tm-assign — Assign and Work a Specific Issue

Assign a specific issue to Claude and drive it to completion. This command handles the full lifecycle: claiming the issue, planning if needed, and executing the plan.

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

## Step 4: Set In Progress

Claim the issue by setting it to In Progress and applying the Claude label:
```
${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_issue.py \
  --id <issue-id> \
  --state "In Progress" \
  --label "Claude"
```

If the script returns an error, report it and stop.

---

## Step 5: Check for Existing Plan

Fetch all comments on the issue:
```
${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_list_comments.py <issue-id>
```

Scan the results for any comment whose body starts with `## Execution Plan`. Note the outcome:

- **No plan comment found** → go to Step 6 (Create Plan).
- **Plan comment found with at least one unchecked item** (`- [ ]`) → go to Step 7 (Execute Plan).
- **Plan comment found, all items checked** (`- [x]`, no `- [ ]` remaining) → go to Step 8 (Wrap Up).

---

## Step 6: Create Plan

Follow `${CLAUDE_PLUGIN_ROOT}/references/plan-flow.md` to create an execution plan for this issue.

- If the issue is vague or missing detail, follow the review-issue-flow as directed by plan-flow.md and **stop** — do not proceed to execution until the issue is clarified.
- If planning succeeds and a plan comment is posted, continue to Step 7.

---

## Step 7: Execute the Plan

Follow `${CLAUDE_PLUGIN_ROOT}/references/work-flow.md` with `<issue-id>`.

- If blocked at any point during execution, follow the review-issue-flow as directed by work-flow.md and **stop**.
- On successful completion, work-flow.md will set the status to "In Review" and post a summary comment. Once that is done, stop — the issue is complete.

---

## Step 8: Wrap Up (All Items Already Checked)

If the plan exists and all checklist items are already checked, the work is done. Finalize the issue:

1. Set status to "In Review":
   ```
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_issue.py \
     --id <issue-id> \
     --state "In Review"
   ```

2. Post a summary comment:
   ```
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_comment.py \
     --issue-id <issue-id> \
     --body "All plan items were already complete. Issue moved to In Review."
   ```

Report to the user: "Issue <issue-id> — all plan items were already completed. Moved to In Review."
