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

**d. Work through each unchecked checklist item:**
- Do the work for the item.
- After completing each item, update the plan comment with the item checked off:
  ```bash
  ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_comment.py \
    --id <comment-id> \
    --body "<updated body with that item changed from - [ ] to - [x]>"
  ```

**e. If blocked at any point:**
Follow `${CLAUDE_PLUGIN_ROOT}/references/review-issue-flow.md`, then stop.

**f. On completion:**
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
     --links '[{"url":"<pr-url>","title":"Pull Request"}]'
   ```
3. Set status to "In Review":
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_issue.py \
     --id <issue-id> \
     --state "In Review"
   ```
4. Post a summary comment:
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_comment.py \
     --issue-id <issue-id> \
     --body "<summary of work done>"
   ```

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
2. Post a summary comment:
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_comment.py \
     --issue-id <issue-id> \
     --body "<summary of work done>"
   ```
