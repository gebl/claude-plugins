# Next Flow Reference

## Issue Selection Logic

### Inputs

- `config` — loaded per `references/config.md`
- `project_filter` — optional; limit to a specific project
- `interactive` — optional boolean, default `true`

### Steps

1. **Fetch Todo issues:**
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_list_issues.py --status Todo
   ```

2. **Filter to active projects:** Keep only issues whose project appears in the `projects` section of config.

3. **Apply project filter:** If `project_filter` was provided, further narrow the list to that project only.

4. **Sort by priority:**
   - 1 = Urgent (first)
   - 2 = High
   - 3 = Normal
   - 4 = Low
   - 0 = None (last)

5. **Check blockers:** For each candidate in priority order:
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_get_issue.py <id> --relations
   ```
   Inspect `blocked_by`. Skip the issue if any blocking issue is not in a completed state.

6. **Interactive mode** (when `interactive` is true and a qualifying issue is found):
   - Display: ID, title, priority, project, description (first 200 characters).
   - Ask the user: `"Work on this? (y/n)"`
   - If the user says no, continue to the next candidate.

7. **Non-interactive mode** (when `interactive` is false):
   - Return the first qualifying issue immediately.

8. **No issues found:** Return `null` and inform the user nothing is available.
