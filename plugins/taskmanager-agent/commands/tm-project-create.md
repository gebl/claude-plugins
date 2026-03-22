---
name: tm-project-create
description: "Create a new project with Linear project, Forgejo repo, local clone, and config update. Supports both full setup and Linear-only modes."
argument-hint: "<name> [--repo <url>] [--description <text>] [--full] [--org <name>] [--public]"
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
---

# /tm-project-create — Create a New Active Project

Create a new project. Two modes:

- **Default**: Create a Linear project and optionally attach an existing repo URL.
- **Full setup** (`--full`): Create Linear project + Forgejo repository + local clone + config update — follows `references/project-setup-flow.md` end-to-end.

All script invocations use the pattern:
```
${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/<script>.py <args>
```

---

## Step 1: Validate Arguments

`<name>` is required. If not provided, stop and report:

```
Usage: /tm-project-create <name> [--repo <url>] [--description <text>] [--full] [--org <name>] [--public]
```

---

## Step 2: Read Config

Read `~/.claude/taskmanager.yaml` per `${CLAUDE_PLUGIN_ROOT}/references/config.md`. Extract the team ID and the `claude_active` project label ID.

If the config does not exist or is missing required fields, stop and report: "Config not found or incomplete. Run `/tm-health` first."

---

## Step 3: Route by Mode

### If `--full` is provided:

Follow `${CLAUDE_PLUGIN_ROOT}/references/project-setup-flow.md` with:
- `name` = the provided name
- `description` = `--description` value if given
- `visibility` = "public" if `--public`, otherwise "private"
- `org` = `--org` value if given, otherwise from config or environment

Display the full summary from the setup flow and stop.

### If `--full` is NOT provided (default):

Continue with the legacy steps below.

---

## Step 4: Create the Project (legacy mode)

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

## Step 5: Attach Repository Link (if provided)

If `--repo <url>` was given, run:

```
${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_create_project_link.py \
  --project-id <project-id> \
  --label Repository \
  --url <url>
```

If the script returns an error, report it as a warning but do not fail — the project was already created.

---

## Step 6: Update Config

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

## Step 7: Display Summary

```
Created project: <name> (<project-id>)
Label:           Claude Active
Repo:            <url, or "none">
Config:          ~/.claude/taskmanager.yaml updated

Next steps:
  /tm-project-create "<name>" --full   — set up repo and local clone
  /tm-issue-create "<title>" --project "<name>"   — add issues to this project
  /tm-health                                       — refresh config and validate git access
```
