# Plan Flow Reference

## Planning Logic

### Inputs

- `config` — loaded per `references/config.md`
- `issue_id` — Linear issue ID to plan

### Steps

1. **Fetch full issue details:**
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_get_issue.py <issue_id> --relations
   ```

2. **Check for existing plan:**
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_list_comments.py <issue_id>
   ```
   If any comment body starts with `## Execution Plan`, a plan already exists — skip planning and return.

3. **Determine mode:** Look up the issue's project in config.
   - If the project has a `repo` field that is not null → **code mode**
   - Otherwise → **document mode**

4. **Code mode:**
   - Navigate to `local_path` for the project.
   - If `local_path` is not set or the directory does not exist, inform the user:
     > "Project '<name>' has a repo but no `local_path` configured. Clone the repo and set `local_path` in `~/.claude/taskmanager.yaml`, then re-run."
   - Pull latest: `git pull`
   - Explore the codebase to understand relevant structure.
   - Create a checklist-style execution plan.

5. **Document mode:**
   - Analyze the issue requirements.
   - Create a plan for research and/or writing work.

6. **Post the plan:**
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_comment.py \
     --issue-id <id> \
     --body "<plan>"
   ```
   The body **MUST** begin with `## Execution Plan` as the first line, followed by checklist items in the format:
   ```
   - [ ] Step 1: <description>
   - [ ] Step 2: <description>
   ```

7. **Vague issue:** If the issue lacks sufficient detail to plan, follow:
   ```
   ${CLAUDE_PLUGIN_ROOT}/references/review-issue-flow.md
   ```

8. **Out-of-scope work discovered:** Create sub-issues for anything found during planning that is out of scope. Max depth is 1 level (no sub-sub-issues).
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_issue.py \
     --title "<title>" \
     --team <team> \
     --parent-id <issue-id> \
     --state Backlog
   ```
