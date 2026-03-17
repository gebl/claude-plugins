---
name: tm-next
description: "Pull the next highest-priority Todo issue from the backlog. Filters to active projects, skips blocked issues, and lets you choose whether to start working on it."
argument-hint: "[--project <name>]"
---

# /tm-next — Pull Next Priority Issue

Pull the next highest-priority issue from the backlog and optionally start working on it.

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

Key selection rules:
- Only consider issues in **Todo** or **Backlog** status.
- Only consider issues belonging to active projects (or the filtered project if `--project` was given).
- Skip any issues whose status is **Blocked**.
- Sort by priority ascending (1 = urgent, 4 = low), then by creation date ascending (oldest first) as a tiebreaker.
- If no eligible issues are found, report: "No eligible issues found. All issues may be blocked or the backlog is empty." and stop.

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

Apply the **"Claude"** label and set status to **"In Progress"**:

```
${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_issue.py \
  --id <issue-id> \
  --state "In Progress" \
  --label "Claude"
```

If the script returns an error, report it and stop.

---

## Step 6: Report & Suggest Next Steps

Display a confirmation:

```
Started: <issue-id> — <title>
Status:  In Progress
Label:   Claude
```

Suggest next commands:
- `/tm-plan <issue-id>` — analyze the issue and create an execution plan
- `/tm-work <issue-id>` — begin executing the plan
- `/tm-update <issue-id> blocked --comment "<reason>"` — mark blocked if needed
