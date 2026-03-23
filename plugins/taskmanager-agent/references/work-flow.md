# Work Flow Reference

## Execution Logic

### Inputs

- `config` — loaded per `references/config.md`
- `issue_id` — Linear issue ID to work on

### Steps

1. **Find the execution plan comment:**
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_list_comments.py <issue_id>
   ```
   Find the comment whose body starts with `## Execution Plan`. Note its comment ID.
   If no such comment exists, stop and tell the user:
   > "No plan found. Run /tm-plan first."

2. **Assign the issue to the current operator:**
   Use the `operator` field from the config as the assignee:
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_issue.py \
     --id <issue_id> \
     --assignee <operator>
   ```
   If the script returns an error, warn the user but continue — assignment failure should not block work.

3. **Parse the checklist:**
   - Unchecked items match: `- [ ] `
   - Checked items match: `- [x] `

4. **Determine mode:** Look up the issue's project in config (same logic as `plan-flow.md`).

---

### Code Mode

**a. Navigate to the worktree:**
```bash
cd <local_path>
git checkout main && git pull
```

**b. Resolve branch name:**
From the `tm_get_issue.py` response, use the `branch_name` field if present. Otherwise construct it as:
```
<team-key-lower>-<number>-<slug>
```
where `<slug>` is the issue title lowercased with spaces replaced by hyphens.

**c. Create a worktree:**
```bash
git worktree add .worktrees/<branch> -b <branch> main
```

**d. Post a work-start journal entry:**
```bash
${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_comment.py \
  --issue-id <issue-id> \
  --body "**[Activity]** Starting execution of plan."
```

**e. Work through each unchecked checklist item:**

Parse the plan into an ordered sequence of **steps** and **parallel groups**. A parallel group is delimited by `[parallel]` and `[end-parallel]` markers on their own lines. Everything outside these markers is a sequential step.

**Sequential steps** (items outside `[parallel]` blocks):
- Do the work for the item.
- After completing each item, update the plan comment with the item checked off:
  ```bash
  ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_comment.py \
    --id <comment-id> \
    --body "<updated body with that item changed from - [ ] to - [x]>"
  ```
- Then post a journal entry on the issue with progress tracking:
  ```bash
  ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_comment.py \
    --issue-id <issue-id> \
    --body "**[Activity]** Completed step <N>/<total>: <step description>"
  ```

**Parallel groups** (items between `[parallel]` and `[end-parallel]`):

1. Collect all unchecked items in the group.
2. If only one unchecked item remains, execute it sequentially (no parallelism overhead).
3. If multiple unchecked items exist, dispatch them as concurrent Agent tool calls — use the Agent tool with multiple invocations in a **single message**. Each subagent receives:
   - The step description
   - The worktree path (absolute path to the worktree)
   - Project context (issue title, relevant files/modules)
   - Instruction to make the changes and report what was done
4. Wait for all subagents to complete.

**Parallel group progress tracking:**

After all subagents in a parallel group return:
1. Identify which steps succeeded (subagent reported completion without errors).
2. Update the plan comment to check off **all completed items at once** in a single update:
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_comment.py \
     --id <comment-id> \
     --body "<updated body with all successful items changed from - [ ] to - [x]>"
   ```
3. Post a **single** journal entry summarizing the group:
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_comment.py \
     --issue-id <issue-id> \
     --body "**[Activity]** Completed steps <N>-<M>/<total> (parallel group): <brief summary>"
   ```

**Parallel group error handling:**

If any subagent in a parallel group fails or reports being blocked:
1. Check off only the **successful** items in the plan comment.
2. Leave failed items unchecked.
3. Post a journal entry noting partial completion:
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_comment.py \
     --issue-id <issue-id> \
     --body "**[Activity]** Parallel group partially complete (<succeeded>/<group-size>). Failed: <step description>. Falling back to sequential."
   ```
4. For each failed item, attempt it **sequentially** in the main context (not as a subagent).
5. If sequential retry also fails, follow `${CLAUDE_PLUGIN_ROOT}/references/review-issue-flow.md` to block and request human input.

**f. If blocked at any point:**
Follow `${CLAUDE_PLUGIN_ROOT}/references/review-issue-flow.md`, then stop.

**g. On completion:**
```bash
git commit -m "<key>: <summary>"
git push origin <branch>
```
Then:
1. Create PR per `${CLAUDE_PLUGIN_ROOT}/references/pr-creation.md`.
2. Link the PR on the issue:
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_issue.py \
     --id <issue-id> \
     --links '[{"url":"<pr-url>","label":"Pull Request"}]'
   ```
3. Set status to "In Review":
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_issue.py \
     --id <issue-id> \
     --state "In Review"
   ```
4. Post a completion journal entry:
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_comment.py \
     --issue-id <issue-id> \
     --body "**[Activity]** Execution complete. PR submitted: <pr-url>\n\n<summary of work done>"
   ```
5. Create a review sub-issue for PR review via `${CLAUDE_PLUGIN_ROOT}/references/review-issue-flow.md` with:
   - `parent_issue_id` = `<issue-id>`
   - `parent_issue_key` = `<issue-key>`
   - `title` = `"Review PR for <issue-key>: <issue-title>"`
   - `question` = `"PR submitted for review: <pr-url>\n\n<summary of work done>\n\nPlease review the PR and either merge it or add a comment with feedback."`
   The review-issue-flow will block the parent and assign to the human reviewer.

---

### Document Mode

**a. Work through each unchecked checklist item.**

**b. Create a Linear document:**
```bash
${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_create_document.py \
  --title "<title>" \
  --content "<content>" \
  --project <project>
```

**c. Check off items** using the same `tm_save_comment.py` update pattern as code mode.

**d. On completion:**
1. Set status to "In Review":
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_issue.py \
     --id <issue-id> \
     --state "In Review"
   ```
2. Post a completion journal entry:
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_comment.py \
     --issue-id <issue-id> \
     --body "**[Activity]** Execution complete.\n\n<summary of work done>"
   ```
3. Create a review sub-issue via `${CLAUDE_PLUGIN_ROOT}/references/review-issue-flow.md` with:
   - `parent_issue_id` = `<issue-id>`
   - `parent_issue_key` = `<issue-key>`
   - `question` = `"Work complete. Please review the output and either close the issue or add a comment with feedback."`
   The review-issue-flow will block the parent and assign to the human reviewer.
