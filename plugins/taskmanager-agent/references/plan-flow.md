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

   **Parallel groups:** When multiple steps are independent and touch different files/modules, wrap them in `[parallel]` / `[end-parallel]` markers:
   ```
   - [ ] Step 1: <sequential step>
   [parallel]
   - [ ] Step 2: <independent step A — modifies module X>
   - [ ] Step 3: <independent step B — modifies module Y>
   - [ ] Step 4: <independent step C — modifies module Z>
   [end-parallel]
   - [ ] Step 5: <sequential step that depends on 2-4>
   ```

   **When to use parallel groups:**
   - Steps modify **different files or modules** with no shared-file edits
   - Steps have **no data dependencies** on each other (step N does not need output from step M)
   - All steps in the group share the same worktree, so file-level isolation is the planner's responsibility

   **When NOT to use parallel groups:**
   - Steps modify the same file (even different sections)
   - Step N depends on code or output produced by step M
   - Steps are trivially small — parallelism overhead outweighs the benefit
   - When in doubt, **default to sequential**. Only mark parallel when clearly independent.

7. **Wait for creator review:** After posting the plan, **do not auto-execute**. Instead:
   a. **Evaluate plan size:** Count the number of checklist items (`- [ ]` lines) in the plan.
   b. **Build the question for review-issue-flow:** Construct the question text as:
      ```
      Please review the execution plan posted on <issue-key>.

      <full plan text copied from the plan comment>

      <if 8+ items: "This plan has N steps and may benefit from decomposition into smaller sub-issues. To request decomposition, comment 'decompose' on this review sub-issue.">

      Mark this sub-issue as Done to approve the plan, or add a comment with changes needed.
      ```
   c. **Delegate to review-issue-flow:** Follow `${CLAUDE_PLUGIN_ROOT}/references/review-issue-flow.md` with:
      - `parent_issue_id` = `<issue-id>`
      - `parent_issue_key` = `<issue-key>`
      - `title` = `"Review plan for <issue-key>: <issue-title>"`
      - `question` = the text constructed above
      The review-issue-flow will create the review sub-issue, block the parent, and post a comment.
   d. Report to the user: `"Plan posted for <issue-key>. Blocked — waiting for creator to review and approve."` then **stop**.

8. **Vague issue:** If the issue lacks sufficient detail to plan, follow:
   ```
   ${CLAUDE_PLUGIN_ROOT}/references/review-issue-flow.md
   ```

9. **Out-of-scope work discovered:** Create sub-issues for anything found during planning that is out of scope. Max depth is 1 level (no sub-sub-issues).
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_issue.py \
     --title "<title>" \
     --team <team> \
     --parent-id <issue-id> \
     --state Backlog
   ```
