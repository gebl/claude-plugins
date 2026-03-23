# Decompose Flow Reference

## Decomposition Logic

Breaks a large execution plan into ordered sub-issues, each with its own mini execution plan. The parent issue becomes a tracking umbrella.

### Inputs

- `config` — loaded per `references/config.md`
- `issue_id` — parent issue ID whose plan should be decomposed
- `plan_comment` — the existing execution plan comment (body and ID)

### Steps

1. **Parse the plan into logical phases:**
   Read the existing plan comment. Group the checklist items into logical phases — each phase should be a coherent, independently executable unit of work. Consider:
   - Items that modify the same file or module belong together
   - Items with hard dependencies on prior items form a chain
   - Items that can be done independently can be separate phases

2. **For each phase, create a sub-issue:**
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_issue.py \
     --title "Phase <N>: <phase title>" \
     --team <team-id> \
     --parent-id <parent-issue-id> \
     --project <project-id> \
     --state Todo \
     --labels Claude \
     --priority <priority> \
     --description "<phase description with context from parent issue>\n\nParent issue: <parent-issue-key>"
   ```

   **Priority mapping:** Assign priority based on execution order:
   - Phase 1 → `1` (Urgent)
   - Phase 2 → `2` (High)
   - Phase 3 → `3` (Normal)
   - Phase 4+ → `4` (Low)

   Note each sub-issue's returned ID for the next step.

3. **Create blocked_by chains for hard dependencies:**
   For phases that have true sequential dependencies (e.g., Phase 2 depends on code from Phase 1), create a `blocks` relation:
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_create_relation.py \
     --issue-id <earlier-phase-id> \
     --blocks <later-phase-id>
   ```

   Only create relations for **hard** dependencies. If two phases can technically be done in any order but one is preferred first, priority alone is sufficient — no `blocked_by` relation needed.

4. **Update the parent plan comment:**
   Mark all checklist items as checked (work has moved to sub-issues):
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_comment.py \
     --id <plan-comment-id> \
     --body "<updated plan body with all items marked [x] and a note: 'Decomposed into sub-issues — see below.'>"
   ```

5. **Post a summary comment on the parent:**
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_comment.py \
     --issue-id <parent-issue-id> \
     --body "**[Activity]** Plan decomposed into <N> sub-issues:\n\n<for each sub-issue:>\n- <sub-issue-key>: <title> (Priority: <priority>, Blocked by: <blocker-key or 'none'>)\n\nThis issue is now a tracking umbrella. Sub-issues will be picked up in priority/dependency order by the issue picker."
   ```

6. **Set parent to In Review:**
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_save_issue.py \
     --id <parent-issue-id> \
     --state "In Review"
   ```

7. **Report:** `"Decomposed <parent-key> into <N> sub-issues. Parent moved to In Review as tracking umbrella."`

---

### Parallel Groups vs. Decomposition

Prefer **parallel groups** (`[parallel]`/`[end-parallel]` in the plan) over decomposition into many tiny sub-issues when:
- The steps are small and independent enough to run in one session
- They touch different files but share the same conceptual change
- The overhead of separate plan/execute/PR cycles per sub-issue outweighs the benefit

Decomposition is better when:
- Steps are large enough to warrant their own PR and review cycle
- Steps have complex dependencies that benefit from explicit `blocked_by` tracking
- The total work exceeds what fits in a single Claude session

When decomposing a plan that already contains `[parallel]` markers, preserve the parallel grouping within each sub-issue's mini plan where applicable.

### How Sub-Issues Get Processed

- `next-flow.md` Phase 4 fetches Todo issues sorted by priority and checks `blocked_by` relations
- Blocked sub-issues are skipped until their blocker is completed (Done status)
- When a blocking sub-issue's PR is merged and it moves to Done, the blocked sub-issue becomes eligible in the next round
- Each sub-issue goes through the normal plan → execute → PR cycle independently

### Parent Issue Lifecycle

- Parent stays in In Review while sub-issues are being worked
- When all sub-issues are Done, the parent can be closed manually or by a future automation
