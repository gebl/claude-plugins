---
name: tm-work-backlog
description: "Process the backlog autonomously. Loops through issues by priority, processes each one (plan, execute, or handle state transitions), and creates PRs or documents."
argument-hint: "[--project <name>] [--limit <n>]"
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
---

# /tm-work-backlog — Autonomous Backlog Processing

Process the backlog autonomously. Selects issues by priority, processes each one via process-flow, and loops until the backlog is empty or a limit is reached.

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

Follow `${CLAUDE_PLUGIN_ROOT}/references/next-flow.md` with the project filter if provided.

If no qualifying issue is found, exit the loop and go to Step 5.

### 4b. Process Issue

Follow `${CLAUDE_PLUGIN_ROOT}/references/process-flow.md` with the selected issue ID.

Track the outcome:
- If the issue was **blocked** during processing (vague requirements, review needed, PR rejected), increment `blocked`.
- If the issue was **completed** (moved to In Review or Done), increment `completed`.
- If a **pull request was created** during processing, also increment `prs_created`.

### 4c. Check Limits

Increment `iteration` by 1.

If `--limit` was provided and `iteration >= limit`, exit the loop and go to Step 5.

### 4d. Progress Report

If `iteration` is a nonzero multiple of 3, display a progress summary:

```
Progress after <iteration> issues:
  Completed:   <completed>
  Blocked:     <blocked>
  PRs created: <prs_created>
```

Continue to the next iteration.

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
