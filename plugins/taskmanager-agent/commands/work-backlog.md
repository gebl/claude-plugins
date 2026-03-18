---
name: work-backlog
description: "Process the backlog autonomously. Loops through Todo issues by priority, plans each one, executes the work, and creates PRs or documents. Confirms every 3 issues."
argument-hint: "[--project <name>] [--limit <n>]"
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
---

# /work-backlog — Autonomous Backlog Processing

Process the backlog autonomously. Selects Todo issues by priority, plans each one, executes the work, and loops until the backlog is empty, a limit is reached, or confirmation is declined.

This is a self-contained command. It reads reference files for shared logic but does NOT invoke other slash commands.

All script invocations use the pattern:
```
${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/<script>.py <args>
```

---

## Step 1: Load & Validate Config

Read `~/.claude/taskmanager.yaml` per `${CLAUDE_PLUGIN_ROOT}/references/config.md`. Extract active projects, team ID, operator info, and project `local_path` values.

If the config does not exist or is missing required fields, stop and report: "Config not found or incomplete. Run `/tm-health` first."

If `last_health_check` is more than 24 hours old, warn: "Config is stale. Consider running `/tm-health` before proceeding." — but continue.

---

## Step 2: Parse Arguments

- `--project <name>` — optional. If provided, validate that the named project appears in the active projects list. If not found, stop and report: "Project '<name>' is not in the active projects list. Check your config or run `/tm-health`."
- `--limit <n>` — optional. If provided, parse as an integer. If not a valid positive integer, stop and report: "Invalid limit '<n>'. Must be a positive integer."

---

## Step 3: Initialize Counters

Set the following counters before entering the loop:

```
completed  = 0
blocked    = 0
prs_created = 0
iteration  = 0
```

---

## Step 4: Main Loop

Repeat the following sub-steps continuously until an exit condition is met.

### 4a. Select Next Issue

Follow `${CLAUDE_PLUGIN_ROOT}/references/next-flow.md` with:
- `interactive: false`
- `project_filter`: the value of `--project` if provided, otherwise none

If no qualifying issue is found, exit the loop and go to Step 5.

### 4b. Claim Issue

Apply the Claude label and set status to In Progress:
```
${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_issue.py \
  --id <issue-id> \
  --state "In Progress" \
  --label "Claude"
```

If the script returns an error, report it, increment `blocked`, and continue to the next iteration.

### 4c. Plan

Follow `${CLAUDE_PLUGIN_ROOT}/references/plan-flow.md` for this issue.

- If the issue is vague or a blocker is discovered during planning, increment `blocked` and continue to the next iteration (do not execute work on this issue).
- If planning succeeds, proceed to step 4d.

### 4d. Execute

Follow `${CLAUDE_PLUGIN_ROOT}/references/work-flow.md` for this issue.

- If blocked during execution, increment `blocked` and continue to the next iteration.
- If execution completes successfully:
  - Increment `completed`.
  - If a pull request was created during the work-flow (code mode), also increment `prs_created`.

### 4e. Check Limits

Increment `iteration` by 1.

If `--limit` was provided and `iteration >= limit`, exit the loop and go to Step 5.

### 4f. Checkpoint

If `iteration` is a nonzero multiple of 3, display a progress summary:

```
Progress after <iteration> issues:
  Completed:   <completed>
  Blocked:     <blocked>
  PRs created: <prs_created>
```

Ask the user: "Continue? (y/n)"

- **y** — continue the loop.
- **n** — exit the loop and go to Step 5.
- Any other input — treat as **n**, exit the loop.

---

## Step 5: Final Summary

Display the final summary after the loop exits for any reason:

```
Backlog run complete.
─────────────────────────────
  Issues processed: <iteration>
  Completed:        <completed>
  Blocked:          <blocked>
  PRs created:      <prs_created>
─────────────────────────────
```

If `completed` is 0 and `blocked` is 0, add: "No issues were available to process."

If `blocked` > 0, add: "Blocked issues may need clarification. Review them in Linear."
