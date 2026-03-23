# Review Issue Flow Reference

## Creating a Review Sub-Issue When Human Input Is Needed

### Inputs

- `config` — loaded per `references/config.md`
- `parent_issue_id` — ID of the issue that needs human input
- `parent_issue_key` — Display key of the parent issue (e.g. `ENG-42`)
- `question` — The specific question or blocker requiring human review
- `title` — (optional) Custom title for the review sub-issue. Defaults to `"[Review] <parent_key>: <short summary of question>"`
- `parent_project_id` — (optional) Project ID of the parent issue. Sub-issue will inherit this project.
- `parent_priority` — (optional) Priority of the parent issue. Sub-issue will inherit this priority.

### Steps

1. **Create a review sub-issue:**
   Determine the review assignee: use `issue_defaults.assignee_id` from config if set, otherwise fall back to the parent issue's `creator_id`.
   Use `title` if provided, otherwise default to `"[Review] <parent_key>: <short summary of question>"`.
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_issue.py \
     --title "<title>" \
     --team <team> \
     --parent-id <parent_id> \
     --assignee <review_assignee_id> \
     --labels Review \
     --state Todo \
     --description "<question>" \
     --project <parent_project_id> \
     --priority <parent_priority>
   ```
   Note the returned issue key (e.g. `ENG-43`) as `<review_key>`.

2. **Block the parent issue:**
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_issue.py \
     --id <parent_id> \
     --state Blocked
   ```
   The parent stays assigned to the operator (agent). Only the review sub-issue is assigned to the human reviewer.

3. **Post a comment on the parent issue:**
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_comment.py \
     --issue-id <parent_id> \
     --body "Blocked — waiting for human input on <review_key>: <question>\n\n**Action needed:** Please answer the question on the review sub-issue (<review_key>), then mark it as Done to unblock this issue."
   ```

4. **Stop execution** and return to the caller. Do not continue working on the parent issue until the review issue is resolved.
