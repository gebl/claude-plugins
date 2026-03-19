# Next Flow Reference

## Issue Selection Logic

### Inputs

- `config` — loaded per `references/config.md`
- `project_filter` — optional; limit to a specific project
- `interactive` — optional boolean, default `true`

### Steps

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
   d. **Unblock the parent** — set it to Todo and reassign to the operator:
      ```bash
      ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_issue.py \
        --id <parent_id> \
        --state Todo \
        --assignee <operator>
      ```
   e. **Post a comment on the parent:**
      ```bash
      ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_comment.py \
        --issue-id <parent_id> \
        --body "Review sub-issue resolved — unblocked and ready to resume."
      ```
   f. **Return the parent issue as the selected issue** and skip Phase 2. This parent takes priority because it was already in progress and has a plan.

   If multiple review sub-issues are resolved, process all of them (unblock all parents), but select the highest-priority parent as the issue to work on.

#### Phase 2: Select Next Todo Issue

If no resolved review sub-issues were found (or all parents were already unblocked), fall through to normal selection.

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
