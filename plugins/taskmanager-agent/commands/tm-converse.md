---
name: tm-converse
description: "Process a conversation issue — read comments, determine action, and respond. Used for projectless issues that follow a comment-based workflow instead of plan/execute/PR."
argument-hint: "<issue-id>"
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
---

# /tm-converse — Process a Conversation Issue

Handle a conversation issue through its comment-based workflow. Reads the issue + comments, determines the appropriate action, and responds.

This is a self-contained command. It reads reference files for shared logic but does NOT invoke other slash commands.

All script invocations use the pattern:
```
${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/<script>.py <args>
```

---

## Step 1: Validate Arguments

`<issue-id>` is required. If not provided, stop and report: "Usage: /tm-converse <issue-id>"

---

## Step 2: Load Config

Read `~/.claude/taskmanager.yaml` per `${CLAUDE_PLUGIN_ROOT}/references/config.md`. Extract operator info, team ID, and active projects.

If the config does not exist or is missing required fields, stop and report: "Config not found or incomplete. Run `/tm-health` first."

---

## Step 3: Fetch Issue and Comments

Fetch the issue:
```
${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_get_issue.py <issue-id>
```

If the issue is not found, stop and report: "Issue <issue-id> not found."

Fetch comments:
```
${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_list_comments.py <issue-id>
```

---

## Step 4: Set Status

If the issue is in Todo status, move it to In Progress:
```
${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_issue.py \
  --id <issue-id> \
  --state "In Progress"
```

---

## Step 5: Process Conversation

Follow `${CLAUDE_PLUGIN_ROOT}/references/conversation-flow.md` with the issue ID.

The conversation flow will:
1. Identify unprocessed comments
2. Determine which ability to use
3. Execute the ability
4. Post a response comment tagged with `**[Conversation]**`

---

## Step 6: Report

After processing, report the action taken:

```
Conversation processed: <issue-id> — <title>
Action: <ability-name>
Status: <current status>
```
