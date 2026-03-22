# Project Setup Flow Reference

## End-to-End Project Creation

Creates a complete project setup: Linear project, Forgejo repository, local clone, and config update.

### Inputs

- `config` — loaded per `references/config.md`
- `name` — project name
- `description` — project description (optional)
- `visibility` — "private" (default) or "public"
- `org` — Forgejo organization name (from config or environment)

### Steps

#### 1. Create Linear Project

```bash
${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_project.py \
  --name "<name>" \
  --team <team-id> \
  --labels "Claude Active" \
  --description "<description>"
```

Capture the returned `project-id`.

#### 2. Create Forgejo Repository

```bash
${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/create_forgejo_repo.py \
  --name "<name-slug>" \
  --description "<description>" \
  --org "<org>" \
  --auto-init \
  --default-branch main \
  [--public | (default: private)]
```

Where `<name-slug>` is the project name lowercased with spaces replaced by hyphens.

Capture the returned `ssh_url` and `html_url`.

If this step fails, warn but continue — the Linear project was already created.

#### 3. Attach Repository Link to Linear Project

```bash
${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_create_project_link.py \
  --project-id <project-id> \
  --label Repository \
  --url <html_url>
```

#### 4. Clone Repository Locally

```bash
git clone <ssh_url> ~/Projects/<name-slug>
```

If clone fails, warn but continue — the user can clone manually.

#### 5. Initialize Project Structure

In the cloned repo, create initial files if they don't exist:
- `CLAUDE.md` — with project name and basic structure
- `.gitignore` — appropriate for the project type

Commit and push:
```bash
git add -A
git commit -m "Initial project setup"
git push origin main
```

#### 6. Update Config

Add the new project to `~/.claude/taskmanager.yaml`:

```yaml
- id: <project-id>
  name: <name>
  repo: <ssh_url>
  local_path: ~/Projects/<name-slug>
  git_accessible: true
```

Write the updated config, preserving all existing fields.

#### 7. Verify

Run a basic health check:
- Confirm the project directory exists
- Confirm git operations work (git status)
- Confirm the project appears in config

### Error Handling

- If Linear project creation fails, stop and report the error.
- If Forgejo repo creation fails, report a warning. The project can still be used for non-code work.
- If clone fails, report a warning. Set `local_path: null` and `git_accessible: false` in config.
- If config update fails, report the error — this is critical for the daemon to recognize the project.

### Environment Variables Required

- `LINEAR_TOKEN` — Linear API token
- `FORGEJO_TOKEN` — Forgejo API token
- `FORGEJO_URL` — Forgejo base URL (e.g., `https://forgejo.bishop.landq.net`)
