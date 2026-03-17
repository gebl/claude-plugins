---
name: tm-plan
description: "Analyze an issue and create an execution plan. Posts the plan as a checklist comment on the issue. Creates review sub-issues if clarification is needed."
argument-hint: "<issue-id>"
---

# /tm-plan — Analyze Issue and Create Execution Plan

Analyze an issue and produce a structured execution plan posted as a checklist comment on the Linear issue.

All script invocations use the pattern:
```
${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/<script>.py <args>
```

---

## Step 1: Validate Arguments

`<issue-id>` is required. If not provided, stop and report: "Usage: /tm-plan <issue-id>"

---

## Step 2: Read Config

Read `~/.claude/taskmanager.yaml` per `${CLAUDE_PLUGIN_ROOT}/references/config.md`. Extract active projects, team ID, and operator info.

If the config does not exist or is missing required fields, stop and report: "Config not found or incomplete. Run `/tm-health` first."

---

## Step 3: Execute Plan Flow

Follow `${CLAUDE_PLUGIN_ROOT}/references/plan-flow.md` for the full planning procedure.

The plan flow covers:
- Fetching the issue details and any existing comments
- Analyzing the scope and type of work (code, document, research, etc.)
- Identifying unknowns or blockers that require clarification
- Creating review sub-issues if clarification is needed before work can begin
- Producing a numbered checklist of concrete, actionable steps
- Posting the plan as a comment on the issue via `tm_save_comment.py`

Refer to the plan-flow reference for exact script invocations, comment formatting, and sub-issue creation rules.
