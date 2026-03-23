# Process Flow Reference

## Issue Processing Logic

Given an issue ID, determine the current state and execute the appropriate action. This is the single source of truth for "what to do with this issue."

### Inputs

- `config` — loaded per `references/config.md`
- `issue_id` — Linear issue ID to process
- `review_response` — optional; context from a resolved review sub-issue

### General Principle: Human Input Requires a Review Sub-Issue

Any time human input is needed — plan approval, PR review, clarification, or feedback — a review sub-issue **MUST** be created via `${CLAUDE_PLUGIN_ROOT}/references/review-issue-flow.md`. Do not post "action needed" comments without a corresponding trackable sub-issue. The human responds with a comment on the sub-issue and marks it as Done to unblock work.

### Steps

1. **Fetch full issue details:**
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_get_issue.py <issue_id> --relations
   ```

2. **Fetch comments:**
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_list_comments.py <issue_id>
   ```

2b. **Check for human comments on this issue.** From the comments fetched in step 2, look for comments NOT from the operator (config `operator.id`) and NOT starting with `**[Activity]**`. If found:
   1. Create a review sub-issue via `${CLAUDE_PLUGIN_ROOT}/references/review-issue-flow.md` with:
      - `parent_issue_id` = `<issue-id>`
      - `parent_issue_key` = `<issue-key>`
      - `question` = "Direct feedback received on this issue:\n\n<formatted human comments>\n\nPlease review and advise how to proceed."
   2. The review-issue-flow will block the parent and assign to the human reviewer. **Stop** — do not proceed further.

3. **Route based on issue status:**

---

### Route A: In Review — PR Status Check

If the issue status is **In Review**:

1. Look up the issue's project in config to get the `repo` URL. Get the issue's `branch_name` field.
2. Check PR status:
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/check_pr_status.py \
     --repo-url <repo-url> \
     --branch <branch-name>
   ```
3. Route based on PR state:

   - **`merged`** — Close the issue:
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
          --body "**[Activity]** PR merged. Issue complete."
        ```
     3. Close all sub-issues:
        ```bash
        ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_list_issues.py --parent <issue-id>
        ```
        For each sub-issue not already in a completed or canceled state:
        ```bash
        ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_issue.py \
          --id <sub-issue-id> \
          --state "Done"
        ```
     4. Clean up the local worktree if it exists:
        ```bash
        # From the project's local_path:
        git worktree remove .worktrees/<branch-name> --force 2>/dev/null
        git branch -d <branch-name> 2>/dev/null
        ```
     5. Report: `"Closed: <issue-id> — <title> (PR merged)"`

   - **Has review comments** (state is `open` and `comments` is non-empty) — Create review sub-issue for human to triage:
     1. Post the PR feedback on the issue:
        ```bash
        ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_comment.py \
          --issue-id <issue-id> \
          --body "**[Activity]** PR review feedback received:\n\n<formatted comments>"
        ```
     2. Create a review sub-issue via `${CLAUDE_PLUGIN_ROOT}/references/review-issue-flow.md` with:
        - `parent_issue_id` = `<issue-id>`
        - `parent_issue_key` = `<issue-key>`
        - `question` = "PR review feedback received — please review the comments and advise how to proceed:\n\n<formatted PR comments>"
     3. The review-issue-flow will block the parent and assign to the human reviewer. **Stop** — do not proceed to Route D until the review sub-issue is resolved via Route B.

   - **`open` with no comments** — PR is still under review. Report: `"<issue-id> — PR still under review. No action needed."` and stop.

   - **`closed`** (not merged) — PR was rejected:
     1. Set status to Blocked:
        ```bash
        ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_issue.py \
          --id <issue-id> \
          --state "Blocked"
        ```
     2. Post a comment explaining the PR was closed without merge.
     3. Report: `"<issue-id> — PR closed without merge. Issue blocked."` and stop.

   - **`not_found`** — No PR exists for this branch. Report: `"<issue-id> — No PR found. Issue remains In Review."` and stop.

---

### Route B: Blocked — Check for Resolved Reviews

If the issue status is **Blocked**:

1. Fetch sub-issues to check for resolved reviews:
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_list_issues.py --parent <issue-id>
   ```
2. Look for sub-issues with the **Review** label that are in **Done** status.
3. If no resolved review sub-issues found, report: `"<issue-id> — still blocked. No resolved reviews found."` and stop.
4. If a resolved review sub-issue is found:
   a. Read the review response — fetch comments on the review sub-issue:
      ```bash
      ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_list_comments.py <review-sub-issue-id>
      ```
      Collect the description, title, and comments as the `review_response`.
   b. Unblock the parent — set to In Progress:
      ```bash
      ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_issue.py \
        --id <issue-id> \
        --state "In Progress" \
        --assignee <operator>
      ```
   c. Post a summary comment on the parent:
      ```bash
      ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_comment.py \
        --issue-id <issue-id> \
        --body "**[Activity]** Review resolved (<review-sub-issue-key>). Response:\n\n<review_response summary>\n\nResuming work with this input."
      ```
   d. **Check for decomposition request:** Examine the review response (description + comments on the review sub-issue). If the reviewer requested decomposition (e.g., commented "decompose", "break this up", "split into smaller issues", or similar), route to **Route F** instead of continuing below.
   e. Continue processing — check for a plan comment (from step 2 above) and route to **Route C** or **Route D** accordingly, carrying the `review_response` as context.

---

### Route C: Plan Required

If the issue status is **Todo**, or **In Progress** with no plan comment (no comment starting with `## Execution Plan`):

1. Set status to In Progress, assign to operator, and apply the Claude label (if not already):
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_issue.py \
     --id <issue-id> \
     --state "In Progress" \
     --assignee <operator> \
     --label "Claude"
   ```
2. Follow `${CLAUDE_PLUGIN_ROOT}/references/plan-flow.md` to create an execution plan.
3. The plan-flow will post the plan, create a review sub-issue, block the issue, and **stop**. Do not proceed to execution.
4. Report: `"Plan posted for <issue-id>. Blocked — waiting for review."`

---

### Route D: Execute Plan

If the issue status is **In Progress** and a plan comment exists with unchecked items (`- [ ]`):

1. Set status to In Progress, assign to operator, and apply the Claude label (if not already):
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_issue.py \
     --id <issue-id> \
     --state "In Progress" \
     --assignee <operator> \
     --label "Claude"
   ```
2. Follow `${CLAUDE_PLUGIN_ROOT}/references/work-flow.md` with `<issue-id>`.
3. If a `review_response` is available, incorporate it as context when resuming work. Read the response carefully — it may confirm an approach, change direction, or provide missing details.
4. On successful completion, work-flow will set the status to "In Review" and post a summary comment. Stop.

---

### Route E: Wrap Up

If the issue status is **In Progress** and a plan comment exists with all items checked (`- [x]`, no `- [ ]` remaining):

1. Set status to "In Review":
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_issue.py \
     --id <issue-id> \
     --state "In Review"
   ```
2. Post a summary comment:
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_comment.py \
     --issue-id <issue-id> \
     --body "**[Activity]** All plan items complete. Issue moved to In Review."
   ```
3. Report: `"<issue-id> — all plan items complete. Moved to In Review."`

---

### Route F: Decompose Plan

If the review response contains a decomposition request (detected in Route B step 4d):

1. Find the plan comment (comment starting with `## Execution Plan`) from the comments fetched in step 2.
2. Follow `${CLAUDE_PLUGIN_ROOT}/references/decompose-flow.md` with the issue ID and plan comment.
3. Decompose-flow will create sub-issues, set up dependency chains, and move the parent to In Review.
4. Report: `"Decomposed <issue-key> into sub-issues per reviewer request."` and **stop**.

---

### Using Review Response Context

If a `review_response` was provided (from Route B or passed in by the caller):

- **Read the review response carefully** before taking action. It may answer a design question, clarify requirements, approve/reject an approach, or provide missing information.
- **When entering Route C or Route D**, incorporate the review response as context. The response may mean:
  - **Continue with the current approach** — the answer confirms the direction.
  - **Modify the plan** — the answer changes requirements.
  - **Ask further clarification** — the answer is incomplete. Create another review sub-issue via `${CLAUDE_PLUGIN_ROOT}/references/review-issue-flow.md` and stop.
- **Do not ignore the response.** It is the reason the issue was unblocked.
