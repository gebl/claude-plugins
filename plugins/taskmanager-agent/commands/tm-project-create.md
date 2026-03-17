---
name: tm-project-create
description: "Create a new project and mark it as active for the task manager. Optionally attach a git repository URL."
argument-hint: "<name> [--repo <url>] [--description <text>]"
---

# /tm-project-create — Create a New Active Project

Create a new Linear project, tag it as Claude-active, and optionally attach a git repository URL.

All script invocations use the pattern:
```
${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/<script>.py <args>
```

---

## Step 1: Validate Arguments

`<name>` is required. If not provided, stop and report:

```
Usage: /tm-project-create <name> [--repo <url>] [--description <text>]
```

---

## Step 2: Read Config

Read `~/.claude/taskmanager.yaml` per `${CLAUDE_PLUGIN_ROOT}/references/config.md`. Extract the team ID and the `claude_active` project label ID.

If the config does not exist or is missing required fields, stop and report: "Config not found or incomplete. Run `/tm-health` first."

---

## Step 3: Create the Project

Run:

```
${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_project.py \
  --name <name> \
  --team <team-id> \
  --labels "Claude Active" \
  [--description <text>]
```

Include `--description <text>` only if it was provided. If the script returns an error, report it and stop.

Capture the returned `project-id` from the script output.

---

## Step 4: Attach Repository Link (if provided)

If `--repo <url>` was given, run:

```
${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_create_project_link.py \
  --project-id <project-id> \
  --label Repository \
  --url <url>
```

If the script returns an error, report it as a warning but do not fail — the project was already created.

---

## Step 5: Update Config

Add the new project to the `projects` list in `~/.claude/taskmanager.yaml`:

```yaml
- id: <project-id>
  name: <name>
  repo: <url-or-null>
  local_path: null
  git_accessible: null
```

Write the updated config back to disk, preserving all existing fields.

---

## Step 6: Display Summary

```
Created project: <name> (<project-id>)
Label:           Claude Active
Repo:            <url, or "none">
Config:          ~/.claude/taskmanager.yaml updated

Next steps:
  /tm-issue-create "<title>" --project "<name>"   — add issues to this project
  /tm-health                                       — refresh config and validate git access
```
