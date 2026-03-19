---
name: tm-next
description: "Pull the next work item. First unblocks issues whose review sub-issues are resolved, then resumes In Progress issues with the Claude label, then falls back to the highest-priority Todo issue. Filters to active projects, skips blocked issues."
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

Pull the next work item. Priority order:
1. Unblock issues whose review sub-issues have been resolved
2. Resume In Progress issues already claimed by Claude (plan or work as needed)
3. Pick the highest-priority Todo issue from the backlog

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

Follow the issue selection flow in `${CLAUDE_PLUGIN_ROOT}/references/next-flow.md` with `interactive: true`.

The flow has three phases:
1. **Resolve completed reviews first:** Find Review-labeled sub-issues that are Done. For each, unblock the parent issue, reassign it to the operator, and prioritize it as the next work item.
2. **Resume In Progress issues:** Find issues with the Claude label that are In Progress. These are issues Claude previously started but didn't finish. Route to plan or work based on whether a plan exists.
3. **Fall back to Todo backlog:** If nothing from phases 1–2, select the highest-priority Todo issue from active projects (or the filtered project if `--project` was given). Skip blocked issues.

If no eligible issues are found in any phase, report: "No eligible issues found. All issues may be blocked or the backlog is empty." and stop.

---

## Step 4: Present Issue to User

Display the selected issue clearly:

```
Next issue: <issue-id> — <title>
Project:    <project-name>
Priority:   <urgent | high | normal | low>
Status:     <current status>

Description:
<issue description, truncated to ~300 chars if long>
```

Ask the user: "Start working on this issue? (yes / no / skip)"

- **yes** — proceed to Step 5.
- **no** — stop. Do not modify the issue.
- **skip** — move to the next candidate in the sorted list and repeat Step 4. If no more candidates, report: "No more eligible issues." and stop.

---

## Step 5: Claim the Issue

If the issue is not already In Progress with the Claude label, claim it:

```
${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_issue.py \
  --id <issue-id> \
  --state "In Progress" \
  --label "Claude"
```

If the issue came from Phase 1.5 (already In Progress + Claude label), skip the save — it's already claimed.

If the script returns an error, report it and stop.

---

## Step 6: Determine Next Action

Check if a plan already exists for the issue by fetching comments:

```
${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_list_comments.py <issue-id>
```

Scan for a comment whose body starts with `## Execution Plan`:

- **No plan found** → Display: `"Starting: <issue-id> — <title> (creating plan...)"` then follow `${CLAUDE_PLUGIN_ROOT}/references/plan-flow.md` to create a plan. After the plan is posted, continue to execute it.
- **Plan found with unchecked items** (`- [ ]`) → Display: `"Resuming: <issue-id> — <title> (executing plan...)"` then follow `${CLAUDE_PLUGIN_ROOT}/references/work-flow.md` with `<issue-id>`.
- **Plan found, all items checked** (`- [x]`, no `- [ ]` remaining) → Set status to "In Review" and post a summary comment:
  ```
  ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_issue.py \
    --id <issue-id> \
    --state "In Review"
  ```
  Report: `"Issue <issue-id> — all plan items complete. Moved to In Review."`

### Using Review Response Context

If the issue was selected from Phase 1 (review resolution), a `review_response` is available. This contains the human's answer to the question that blocked the issue. Use it to inform the next action:

- **Read the review response carefully** before resuming work. It may answer a design question, clarify requirements, approve/reject an approach, or provide missing information.
- **When resuming plan-flow or work-flow**, incorporate the review response as context. The response may mean:
  - **Continue with the current plan step** — the answer confirms the approach or provides the missing detail needed to proceed.
  - **Modify the plan** — the answer changes direction, requiring plan updates before continuing.
  - **Ask further clarification** — the answer is incomplete or raises new questions. Create another review sub-issue via `${CLAUDE_PLUGIN_ROOT}/references/review-issue-flow.md` and stop.
- **Do not ignore the response.** It is the reason the issue was unblocked — treat it as the primary input for deciding what to do next.
