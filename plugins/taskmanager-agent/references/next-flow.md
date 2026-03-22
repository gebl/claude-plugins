# Next Flow Reference

## Issue Selection Logic

Selects the next issue to work on. Returns an issue ID (with optional context like review_response) or null. Does NOT take action on the issue — the caller delegates action to `process-flow.md`.

### Inputs

- `config` — loaded per `references/config.md`
- `project_filter` — optional; limit to a specific project

### Steps

#### Phase 1: Find In Review Issues Needing Attention

1a. **Fetch In Review issues with the Claude label:**
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_list_issues.py --status "In Review" --label Claude
   ```

1b. **Filter to active projects** (issues whose project appears in config's `projects` list).

1c. **Apply project filter** if provided.

1c2. **Check for human comments on the Linear issue.** Fetch comments:
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_list_comments.py <issue-id>
   ```
   If any comment exists from a user other than the operator (config `operator.id`) AND does not start with `**[Activity]**` AND is newer than the last-seen timestamp for this issue → select this issue.

   This check runs before the PR check so that direct Linear feedback is detected even when the PR has no comments.

1d. **For each In Review issue**, look up its project in config to get the `repo` URL. Get the issue's `branch_name` field. Check PR status:
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/check_pr_status.py \
     --repo-url <repo-url> \
     --branch <branch-name>
   ```

1e. **Select if actionable:**
   - **`merged`** → select this issue (process-flow will close it)
   - **Has review comments** (state is `open` and `comments` is non-empty) → select this issue (process-flow will address feedback)
   - **`closed`** (not merged) → select this issue (process-flow will handle)
   - **`open` with no comments** → skip (still under review)
   - **`not_found`** → skip

   Return the first actionable In Review issue found.

#### Phase 2: Find Blocked Issues with Resolved Reviews

2a. **Fetch completed Review issues:**
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_list_issues.py --status Done --label Review
   ```

2b. **For each completed review sub-issue:**
   - Check if it has a `parent_id`. If not, skip.
   - Fetch the parent issue:
     ```bash
     ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_get_issue.py <parent_id>
     ```
   - If the parent is in a completed or canceled state, skip (orphaned review).
   - If the parent is NOT in Blocked status, skip (already unblocked).
   - **Filter to active projects.**
   - **Apply project filter** if provided.
   - Return the parent issue ID. Process-flow will handle unblocking and resuming.

   If multiple review sub-issues are resolved, select the highest-priority parent.

#### Phase 3: Find In Progress Issues

3a. **Fetch In Progress issues with the Claude label:**
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_list_issues.py --status "In Progress" --label Claude
   ```

3b. **Filter to active projects.**

3c. **Apply project filter** if provided.

3d. **Sort by priority** (1=Urgent first, 0=None last).

3e. Return the first qualifying issue. Process-flow will determine whether to plan, execute, or wrap up.

#### Phase 4: Select Next Todo Issue

4a. **Fetch Todo issues:**
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_list_issues.py --status Todo
   ```

4b. **Filter to active projects.**

4c. **Apply project filter** if provided.

4d. **Sort by priority** (1=Urgent first, 2=High, 3=Normal, 4=Low, 0=None last).

4e. **Check blockers** for each candidate in priority order:
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_get_issue.py <id> --relations
   ```
   Skip the issue if any blocking issue is not in a completed state.

4f. Return the first unblocked issue.

#### No Issues Found

If no eligible issues are found in any phase, return `null` and inform the caller nothing is available.
