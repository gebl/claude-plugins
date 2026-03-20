# Review Issue Flow Reference

## Creating a Review Sub-Issue When Human Input Is Needed

### Inputs

- `config` — loaded per `references/config.md`
- `parent_issue_id` — ID of the issue that needs human input
- `parent_issue_key` — Display key of the parent issue (e.g. `ENG-42`)
- `question` — The specific question or blocker requiring human review

### Steps

1. **Create a review sub-issue:**
   Determine the review assignee: use `issue_defaults.assignee_id` from config if set, otherwise fall back to the parent issue's `creator_id`.
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_issue.py \
     --title "[Review] <parent_key>: <question>" \
     --team <team> \
     --parent-id <parent_id> \
     --assignee <review_assignee_id> \
     --labels Review \
     --state Todo \
     --description "<context and questions>"
   ```
   Note the returned issue key (e.g. `ENG-43`) as `<review_key>`.

2. **Block and reassign the parent issue to the human reviewer:**
   Use `issue_defaults.assignee_id` from config if set, otherwise fall back to the parent issue's `creator_id`.
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_issue.py \
     --id <parent_id> \
     --state Blocked \
     --assignee <review_assignee_id>
   ```
   This ensures the human reviewer is notified that their input is needed. If neither `issue_defaults.assignee_id` nor `creator_id` is available, skip the `--assignee` flag.

3. **Post a comment on the parent issue:**
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_comment.py \
     --issue-id <parent_id> \
     --body "Blocked — waiting for human input on <review_key>: <question>\n\n**Action needed:** Please answer the question on the review sub-issue (<review_key>), then mark it as Done to unblock this issue."
   ```

4. **Stop execution** and return to the caller. Do not continue working on the parent issue until the review issue is resolved.
