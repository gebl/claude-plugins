# Next Flow Reference

## Issue Selection Logic

### Inputs

- `config` — loaded per `references/config.md`
- `project_filter` — optional; limit to a specific project
- `interactive` — optional boolean, default `true`

### Steps

#### Phase 0: Process In Review Issues (PR Status Check)

Before looking for new work, check if any "In Review" issues have had their PRs merged or received review comments.

0a. **Fetch In Review issues with the Claude label:**
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_list_issues.py --status "In Review" --label Claude
   ```

0b. **Filter to active projects** (same as other phases).

0c. **For each In Review issue**, look up its project in config to get the `repo` URL. Get the issue's `branch_name` field. Then check PR status:
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/check_pr_status.py \
     --repo-url <repo-url> \
     --branch <branch-name>
   ```

0d. **Route based on PR state:**

   - **`merged`** — The PR was merged. Close the issue:
     1. Set status to Done:
        ```bash
        ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_issue.py \
          --id <issue-id> \
          --state "Done"
        ```
     2. Post a completion comment:
        ```bash
        ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_comment.py \
          --issue-id <issue-id> \
          --body "PR merged. Issue complete."
        ```
     3. Clean up the local worktree if it exists:
        ```bash
        # From the project's local_path:
        git worktree remove .worktrees/<branch-name> --force 2>/dev/null
        git branch -d <branch-name> 2>/dev/null
        ```
     4. Report: `"Closed: <issue-id> — <title> (PR merged)"`
     5. Continue to next In Review issue (do not return this as the selected issue).

   - **Has review comments** (state is `open` and `comments` is non-empty) — The PR received feedback that needs to be addressed:
     1. Set status back to In Progress:
        ```bash
        ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_issue.py \
          --id <issue-id> \
          --state "In Progress"
        ```
     2. Post the review comments on the issue:
        ```bash
        ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_comment.py \
          --issue-id <issue-id> \
          --body "PR review feedback received:\n\n<formatted comments>\n\nResuming work to address feedback."
        ```
     3. **Return this issue as the selected issue** with the review comments as context. Skip to Phase 3.

   - **`open` with no comments** — PR is still under review. Skip this issue.

   - **`closed`** (not merged) — PR was rejected:
     1. Set status to Blocked:
        ```bash
        ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_issue.py \
          --id <issue-id> \
          --state "Blocked"
        ```
     2. Post a comment explaining the PR was closed without merge.
     3. Continue to next In Review issue.

   - **`not_found`** — No PR exists for this branch. Skip this issue.

#### Phase 1: Resolve Completed Review Sub-Issues

Before looking for new work, check if any previously blocked issues can be unblocked.

1. **Fetch completed Review issues:**
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_list_issues.py --status Done --label Review
   ```

2. **For each completed review sub-issue:**
   a. Check if it has a `parent_id`. If not, skip it.
   b. Fetch the parent issue:
      ```bash
      ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_get_issue.py <parent_id>
      ```
   c. If the parent is **not** in Blocked status, skip — it was already unblocked.
   d. **Read the review response.** Fetch comments on the review sub-issue to find the human's answer:
      ```bash
      ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_list_comments.py <review-sub-issue-id>
      ```
      Also read the review sub-issue's own description and title for context on what was asked. The human may have answered via a comment, or by updating the description. Collect all of this as the `review_response`.
   e. **Unblock the parent** — set it to In Progress and reassign to the operator:
      ```bash
      ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_issue.py \
        --id <parent_id> \
        --state "In Progress" \
        --assignee <operator>
      ```
   f. **Post a summary comment on the parent** that includes the review response so the context is preserved on the parent issue:
      ```bash
      ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_comment.py \
        --issue-id <parent_id> \
        --body "Review resolved (<review-sub-issue-key>). Response:\n\n<review_response summary>\n\nResuming work with this input."
      ```
   g. **Return the parent issue as the selected issue** along with the `review_response` context. Skip to Phase 3. This parent takes priority because it was already in progress and has a plan.

   If multiple review sub-issues are resolved, process all of them (unblock all parents), but select the highest-priority parent as the issue to work on. Carry forward all review responses.

#### Phase 1.5: Resume In Progress Issues

If no resolved review sub-issues were found (or all parents were already unblocked), check for issues already claimed by Claude that need continuation.

2b. **Fetch In Progress issues with the Claude label:**
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_list_issues.py --status "In Progress" --label Claude
   ```

2c. **Filter to active projects:** Keep only issues whose project appears in the `projects` section of config.

2d. **Apply project filter:** If `project_filter` was provided, further narrow the list to that project only.

2e. **Sort by priority** (same as Phase 2 sorting: 1=Urgent first, 0=None last).

2f. **For each candidate, determine routing:**
   Fetch comments to check for a plan:
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_list_comments.py <issue-id>
   ```
   Scan for a comment whose body starts with `## Execution Plan`:
   - **No plan found** → route to plan-flow
   - **Plan found with unchecked items** (`- [ ]`) → route to work-flow
   - **Plan found, all items checked** → route to wrap-up

2g. **Return the first qualifying issue** along with its routing action (plan, work, or wrap-up). Skip to Phase 3.

#### Phase 2: Select Next Todo Issue

If no In Progress issues were found with the Claude label, fall through to normal selection.

3. **Fetch Todo issues:**
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_list_issues.py --status Todo
   ```

4. **Filter to active projects:** Keep only issues whose project appears in the `projects` section of config.

5. **Apply project filter:** If `project_filter` was provided, further narrow the list to that project only.

6. **Sort by priority:**
   - 1 = Urgent (first)
   - 2 = High
   - 3 = Normal
   - 4 = Low
   - 0 = None (last)

7. **Check blockers:** For each candidate in priority order:
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_get_issue.py <id> --relations
   ```
   Inspect `blocked_by`. Skip the issue if any blocking issue is not in a completed state.

#### Phase 3: Present Result

8. **Interactive mode** (when `interactive` is true and a qualifying issue is found):
   - If the issue came from Phase 1, indicate it was unblocked:
     ```
     Unblocked: <issue-id> — <title> (review resolved)
     ```
   - Otherwise display: ID, title, priority, project, description (first 200 characters).
   - Ask the user: `"Work on this? (y/n)"`
   - If the user says no, continue to the next candidate.

9. **Non-interactive mode** (when `interactive` is false):
   - Return the first qualifying issue immediately.

10. **No issues found:** Return `null` and inform the user nothing is available.
