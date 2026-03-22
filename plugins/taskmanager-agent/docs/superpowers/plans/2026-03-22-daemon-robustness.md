# Daemon Robustness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix daemon stuck states, infinite loops, and communication gaps so issues move through the full workflow reliably.

**Architecture:** Seven focused changes across the daemon selector, runner, state, session, forgejo backend, and the reference flow documents. Each task is independent and produces a working commit. The changes fix: comment deduplication via timestamp tracking in daemon state, process-flow awareness of Linear comments, valid-transition enforcement in the runner, correct assignee on error sub-issues, force-stop wiring for child processes, and a variable rename for clarity.

**Tech Stack:** Python 3.12, pytest, YAML state file, Linear GraphQL API, Forgejo REST API

---

## File Map

| File | Role | Tasks |
|------|------|-------|
| `taskmanager/daemon/state.py` | Daemon state persistence | 1 |
| `tests/test_daemon_state.py` | State tests | 1 |
| `taskmanager/daemon/selector.py` | Issue selection logic | 1, 4 |
| `tests/test_daemon_selector.py` | Selector tests | 1, 4 |
| `references/process-flow.md` | Agent workflow reference | 2 |
| `references/next-flow.md` | Agent selection reference | 2 |
| `taskmanager/daemon/runner.py` | Main daemon loop | 3, 5, 6 |
| `tests/test_daemon_integration.py` | Runner integration tests | 3, 5, 6 |
| `taskmanager/daemon/session.py` | Claude session spawner | 5 |
| `tests/test_daemon_session.py` | Session tests | 5 |
| `taskmanager/githost/forgejo.py` | Forgejo backend | 7 |
| `tests/test_githost.py` | Forgejo tests | 7 |

---

### Task 1: Track seen-comment timestamps to prevent infinite re-selection

**Problem:** `_has_human_comments` fires on every poll because it checks if *any* human comment exists. Once a comment is there, it triggers every 10-30 seconds forever, spawning repeated sessions.

**Solution:** Add a `seen_comments` dict to `DaemonState` mapping `issue_id → latest_seen_comment_created_at`. The selector only returns true if there's a human comment *newer* than the last-seen timestamp. After a session completes, the runner records the current timestamp.

**Files:**
- Modify: `taskmanager/daemon/state.py` — add `seen_comments` field, persistence, and update method
- Modify: `tests/test_daemon_state.py` — test seen_comments save/load
- Modify: `taskmanager/daemon/selector.py` — pass `seen_comments` to `_has_human_comments`, filter by timestamp
- Modify: `tests/test_daemon_selector.py` — test timestamp filtering
- Modify: `taskmanager/daemon/runner.py` — after session, update `seen_comments` timestamp

- [ ] **Step 1: Write test for seen_comments state persistence**

```python
# tests/test_daemon_state.py
def test_seen_comments_save_and_load(self, tmp_path, monkeypatch):
    state_file = tmp_path / "daemon-state.yaml"
    monkeypatch.setattr("taskmanager.daemon.state.STATE_FILE", state_file)
    monkeypatch.setattr("taskmanager.daemon.state.STATE_DIR", tmp_path)

    s = DaemonState()
    s.mark_comments_seen("issue-1", "2026-03-22T01:00:00Z")
    s.save()

    loaded = DaemonState.load()
    assert loaded.last_seen_comment_at("issue-1") == "2026-03-22T01:00:00Z"
    assert loaded.last_seen_comment_at("issue-2") is None
```

- [ ] **Step 2: Run test — expect FAIL (methods don't exist)**

Run: `uv run pytest tests/test_daemon_state.py::TestDaemonState::test_seen_comments_save_and_load -v`

- [ ] **Step 3: Implement seen_comments in DaemonState**

In `taskmanager/daemon/state.py`, add to `DaemonState`:
```python
seen_comments: dict[str, str] = field(default_factory=dict)
```

Add methods:
```python
def mark_comments_seen(self, issue_id: str, timestamp: str) -> None:
    self.seen_comments[issue_id] = timestamp

def last_seen_comment_at(self, issue_id: str) -> str | None:
    return self.seen_comments.get(issue_id)
```

Update `load()` to read `seen_comments` from raw dict:
```python
seen_comments=raw.get("seen_comments", {}),
```

Update `save()` to write `seen_comments`:
```python
"seen_comments": self.seen_comments,
```

- [ ] **Step 4: Run test — expect PASS**

Run: `uv run pytest tests/test_daemon_state.py -v`

- [ ] **Step 5: Write test for timestamp-filtered comment detection**

```python
# tests/test_daemon_selector.py
def test_ignores_comments_already_seen(self, monkeypatch):
    monkeypatch.setattr(
        "taskmanager.daemon.selector._run_list_script",
        lambda *a: [
            {
                "user_id": "human-id",
                "user_name": "Gabe",
                "body": "Fix this",
                "created_at": "2026-03-21T10:00:00Z",
            },
        ],
    )
    issue = {"id": "i1", "identifier": "LAN-1"}
    # Comment is older than last-seen — should be ignored
    assert _has_human_comments(issue, "operator-id", "2026-03-22T00:00:00Z") is False

def test_detects_comments_newer_than_seen(self, monkeypatch):
    monkeypatch.setattr(
        "taskmanager.daemon.selector._run_list_script",
        lambda *a: [
            {
                "user_id": "human-id",
                "user_name": "Gabe",
                "body": "New feedback",
                "created_at": "2026-03-22T12:00:00Z",
            },
        ],
    )
    issue = {"id": "i1", "identifier": "LAN-1"}
    # Comment is newer than last-seen — should be detected
    assert _has_human_comments(issue, "operator-id", "2026-03-22T00:00:00Z") is True
```

- [ ] **Step 6: Run test — expect FAIL (signature changed)**

Run: `uv run pytest tests/test_daemon_selector.py::TestHasHumanComments -v`

- [ ] **Step 7: Update `_has_human_comments` signature and logic**

Add `last_seen_at: str | None = None` parameter. Filter comments by `created_at > last_seen_at` when set:

```python
def _has_human_comments(issue: dict, operator_id: str, last_seen_at: str | None = None) -> bool:
    issue_id = issue.get("id", "")
    comments = _run_list_script("tm_list_comments.py", issue_id)
    if not comments:
        return False

    for comment in comments:
        user_id = comment.get("user_id", "")
        body = comment.get("body", "")

        if user_id == operator_id:
            continue
        if body.startswith("**[Activity]**"):
            continue
        # Skip already-seen comments
        if last_seen_at and comment.get("created_at", "") <= last_seen_at:
            continue

        log.info(
            "  → %s has human comment from %s",
            issue.get("identifier", issue_id),
            comment.get("user_name", user_id),
        )
        return True

    return False
```

- [ ] **Step 8: Update `_phase_in_review` to pass seen_comments**

The selector needs access to the daemon state's `seen_comments`. Add `seen_comments` parameter to `select_next_issue` and `_phase_in_review`:

```python
def select_next_issue(
    quarantined_ids: set[str],
    project_filter: str | None = None,
    seen_comments: dict[str, str] | None = None,
) -> SelectedIssue | None:
```

Also update the call to `_phase_in_review` inside `select_next_issue` (line 44) to forward the parameter:
```python
result = _phase_in_review(cfg, active_project_ids, quarantined_ids, project_filter, seen_comments=seen_comments)
```

Add `seen_comments: dict[str, str] | None = None` parameter to `_phase_in_review` signature.

In `_phase_in_review`, pass to `_has_human_comments`:
```python
last_seen_at = (seen_comments or {}).get(issue.get("id", ""))
if _has_human_comments(issue, operator_id, last_seen_at):
```

- [ ] **Step 9: Update runner to pass seen_comments and record timestamps**

In `runner.py:_main_loop`, pass seen_comments when calling selector:
```python
selected = selector.select_next_issue(
    quarantined_ids,
    seen_comments=self._state.seen_comments,
)
```

In `runner.py:_process_issue`, after the session completes (both success and unchanged), mark comments as seen:
```python
self._state.mark_comments_seen(selected.issue_id, _now_iso())
```

- [ ] **Step 10: Update existing `_has_human_comments` tests for new signature**

The existing 4 tests pass `None` implicitly for the new parameter (default value), so they should still pass. Verify.

- [ ] **Step 11: Run all tests**

Run: `uv run pytest tests/ -v`

- [ ] **Step 12: Lint and format**

Run: `uv run ruff check --fix taskmanager/daemon/state.py taskmanager/daemon/selector.py taskmanager/daemon/runner.py tests/test_daemon_state.py tests/test_daemon_selector.py && uv run ruff format taskmanager/daemon/state.py taskmanager/daemon/selector.py taskmanager/daemon/runner.py tests/test_daemon_state.py tests/test_daemon_selector.py`

- [ ] **Step 13: Commit**

```bash
git add taskmanager/daemon/state.py taskmanager/daemon/selector.py taskmanager/daemon/runner.py tests/test_daemon_state.py tests/test_daemon_selector.py
git commit -m "Track seen-comment timestamps to prevent infinite re-selection"
```

---

### Task 2: Add Linear comment handling to process-flow and next-flow

**Problem:** `process-flow.md` Route A only handles PR comments. If the selector fires because of a Linear issue comment, the Claude session enters Route A, finds "open with no comments" on the PR, reports "no action needed," and the status doesn't change — quarantine. The reference docs also don't mention checking Linear comments for selection.

**Solution:** Update `process-flow.md` Route A to check for human Linear comments before checking PR status. If found, create a review sub-issue with the comment content. Update `next-flow.md` Phase 1 to document the Linear comment check.

**Files:**
- Modify: `references/process-flow.md` — add Linear comment check to Route A
- Modify: `references/next-flow.md` — add step 1d-alt for Linear comments

- [ ] **Step 1: Update next-flow.md Phase 1**

After step 1c and before step 1d, add:

```markdown
1c2. **Check for human comments on the Linear issue.** Fetch comments:
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_list_comments.py <issue-id>
   ```
   If any comment exists from a user other than the operator (config `operator.id`) AND does not start with `**[Activity]**` AND is newer than the last-seen timestamp for this issue → select this issue.

   This check runs before the PR check so that direct Linear feedback is detected even when the PR has no comments.
```

- [ ] **Step 2: Update process-flow.md Route A**

After step 2 ("Fetch comments") and before step 3 ("Route based on PR state"), insert a new check:

```markdown
2b. **Check for human comments on this issue.** From the comments fetched in step 2, look for comments NOT from the operator (config `operator.id`) and NOT starting with `**[Activity]**`. If found:
   1. Create a review sub-issue via `${CLAUDE_PLUGIN_ROOT}/references/review-issue-flow.md` with:
      - `parent_issue_id` = `<issue-id>`
      - `parent_issue_key` = `<issue-key>`
      - `question` = "Direct feedback received on this issue:\n\n<formatted human comments>\n\nPlease review and advise how to proceed."
   2. The review-issue-flow will block the parent and assign to the human reviewer. **Stop** — do not proceed further.
```

- [ ] **Step 3: Review changes for consistency**

Read both files end-to-end to ensure step numbering is correct and cross-references still work.

- [ ] **Step 4: Commit**

```bash
git add references/process-flow.md references/next-flow.md
git commit -m "Add Linear comment detection to process-flow and next-flow"
```

---

### Task 3: Validate post-session status transitions

**Problem:** `runner.py:_process_issue` only checks `post_status == pre_status`. Any status change is treated as success — even Todo → Done (skipping the entire workflow). This is how LAN-88 went straight to Done without a PR review.

**Solution:** Define valid transition pairs per starting status. If the post-session status isn't in the valid set, quarantine with a descriptive reason.

**Files:**
- Modify: `taskmanager/daemon/runner.py:122-193` — replace simple equality check with transition validation
- Modify: `tests/test_daemon_integration.py` — add tests for valid/invalid transitions

- [ ] **Step 1: Write test for valid transitions**

```python
# tests/test_daemon_integration.py
class TestTransitionValidation:
    def test_todo_to_in_progress_is_valid(self):
        from taskmanager.daemon.runner import _is_valid_transition
        assert _is_valid_transition("Todo", "In Progress") is True

    def test_todo_to_blocked_is_valid(self):
        from taskmanager.daemon.runner import _is_valid_transition
        assert _is_valid_transition("Todo", "Blocked") is True

    def test_todo_to_done_is_invalid(self):
        from taskmanager.daemon.runner import _is_valid_transition
        assert _is_valid_transition("Todo", "Done") is False

    def test_in_progress_to_in_review_is_valid(self):
        from taskmanager.daemon.runner import _is_valid_transition
        assert _is_valid_transition("In Progress", "In Review") is True

    def test_in_progress_to_blocked_is_valid(self):
        from taskmanager.daemon.runner import _is_valid_transition
        assert _is_valid_transition("In Progress", "Blocked") is True

    def test_in_progress_to_done_is_invalid(self):
        # Must go through In Review first
        from taskmanager.daemon.runner import _is_valid_transition
        assert _is_valid_transition("In Progress", "Done") is False

    def test_in_review_to_done_is_valid(self):
        from taskmanager.daemon.runner import _is_valid_transition
        assert _is_valid_transition("In Review", "Done") is True

    def test_in_review_to_blocked_is_valid(self):
        from taskmanager.daemon.runner import _is_valid_transition
        assert _is_valid_transition("In Review", "Blocked") is True

    def test_in_review_to_in_progress_is_valid(self):
        from taskmanager.daemon.runner import _is_valid_transition
        assert _is_valid_transition("In Review", "In Progress") is True

    def test_blocked_to_in_progress_is_valid(self):
        from taskmanager.daemon.runner import _is_valid_transition
        assert _is_valid_transition("Blocked", "In Progress") is True

    def test_in_review_to_in_review_is_valid(self):
        # No-op is valid for In Review (PR still open)
        from taskmanager.daemon.runner import _is_valid_transition
        assert _is_valid_transition("In Review", "In Review") is True
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `uv run pytest tests/test_daemon_integration.py::TestTransitionValidation -v`

- [ ] **Step 3: Implement `_is_valid_transition`**

Add to `runner.py` before `_now_iso()`:

```python
# Valid status transitions the daemon should accept from Claude sessions.
# Any transition not in this map is treated as a workflow violation.
_VALID_TRANSITIONS: dict[str, set[str]] = {
    "Todo": {"In Progress", "Blocked"},
    "In Progress": {"In Review", "Blocked"},
    "In Review": {"In Review", "Done", "Blocked", "In Progress"},
    "Blocked": {"In Progress", "Todo", "In Review"},
}


def _is_valid_transition(pre: str, post: str) -> bool:
    """Check whether a status transition follows the expected workflow."""
    valid = _VALID_TRANSITIONS.get(pre)
    if valid is None:
        return True  # Unknown pre-status — don't block
    return post in valid
```

Note: `In Progress → Done` is NOT valid — it skips PR review. The correct path is `In Progress → In Review → Done`. `In Review → Done` is valid because that's Route A (PR merged). `Todo → Done` is also invalid — skips the entire plan/review workflow.

- [ ] **Step 4: Run tests — expect PASS**

Run: `uv run pytest tests/test_daemon_integration.py::TestTransitionValidation -v`

- [ ] **Step 5: Update `_process_issue` to use transition validation**

Replace the simple equality check in `runner.py:_process_issue` (lines 172-193):

```python
        if post_status == pre_status and pre_status != "In Review":
            log.warning(
                "Issue %s state unchanged after session (still %s)",
                selected.identifier,
                pre_status,
            )
            self._quarantine_issue(
                selected, f"State unchanged after session (remained {pre_status})"
            )
            self._state.add_to_history(
                selected.issue_id, "unchanged", result.duration_seconds
            )
        elif not _is_valid_transition(pre_status, post_status):
            log.warning(
                "Issue %s made invalid transition: %s → %s",
                selected.identifier,
                pre_status,
                post_status,
            )
            self._quarantine_issue(
                selected,
                f"Invalid workflow transition: {pre_status} → {post_status}",
            )
            self._state.add_to_history(
                selected.issue_id, "invalid_transition", result.duration_seconds
            )
        else:
            log.info(
                "Issue %s transitioned: %s → %s",
                selected.identifier,
                pre_status,
                post_status,
            )
            self._state.add_to_history(
                selected.issue_id, "completed", result.duration_seconds
            )
```

Key change: `In Review → In Review` is no longer quarantined — it's a valid no-op (PR still open, no action needed).

- [ ] **Step 6: Run all tests**

Run: `uv run pytest tests/ -v`

- [ ] **Step 7: Lint and commit**

```bash
uv run ruff check --fix taskmanager/daemon/runner.py tests/test_daemon_integration.py && uv run ruff format taskmanager/daemon/runner.py tests/test_daemon_integration.py
git add taskmanager/daemon/runner.py tests/test_daemon_integration.py
git commit -m "Validate post-session status transitions to prevent workflow skips"
```

---

### Task 4: Move Linear comment check after PR check (reduce API calls)

**Problem:** `_has_human_comments` calls the Linear API on every In Review issue every poll cycle. With N issues polling every 10-30 seconds, this creates unnecessary API load.

**Solution:** Reorder the checks in `_phase_in_review`: check PR status first, and only fall back to Linear comment check when the PR is `open` with no PR comments (the "still under review" case that currently returns None).

**Files:**
- Modify: `taskmanager/daemon/selector.py:70-123` — reorder checks

- [ ] **Step 1: Restructure `_phase_in_review`**

```python
def _phase_in_review(
    cfg: dict,
    active_project_ids: set[str],
    quarantined_ids: set[str],
    project_filter: str | None,
    seen_comments: dict[str, str] | None = None,
) -> SelectedIssue | None:
    """Phase 1: Find In Review issues with actionable PR or Linear comments."""
    log.info("Phase 1: checking In Review issues")
    issues = _run_list_script(
        "tm_list_issues.py", "--status", "In Review", "--label", "Claude"
    )
    if not issues:
        log.info("  → no In Review issues found")
        return None
    log.info("  → found %d In Review issue(s)", len(issues))

    operator_id = cfg.get("operator", {}).get("id", "")
    projects_by_id = {p["id"]: p for p in cfg.get("projects", [])}

    for issue in issues:
        if not _passes_filters(
            issue, active_project_ids, quarantined_ids, project_filter
        ):
            continue

        project = projects_by_id.get(issue.get("project_id", ""))
        branch = issue.get("branch_name")

        # Check PR status first (cheap — single HTTP call)
        if project and project.get("repo") and branch:
            pr_status = _run_dict_script(
                "check_pr_status.py",
                "--repo-url",
                project["repo"],
                "--branch",
                branch,
            )
            if pr_status:
                state = pr_status.get("state", "")
                comments = pr_status.get("comments", [])

                if state == "merged" or state == "closed" or (state == "open" and comments):
                    return _to_selected(issue)

        # Fallback: check Linear issue comments (only if PR had no actionable state)
        last_seen_at = (seen_comments or {}).get(issue.get("id", ""))
        if _has_human_comments(issue, operator_id, last_seen_at):
            return _to_selected(issue)

    return None
```

- [ ] **Step 2: Run all tests**

Run: `uv run pytest tests/ -v`

- [ ] **Step 3: Lint and commit**

```bash
uv run ruff check --fix taskmanager/daemon/selector.py && uv run ruff format taskmanager/daemon/selector.py
git add taskmanager/daemon/selector.py
git commit -m "Move Linear comment check after PR check to reduce API calls"
```

---

### Task 5: Wire up force-stop to kill child process

**Problem:** `_active_proc` is declared but never assigned. Force-stop (second SIGINT/SIGTERM) sets `self._force_stop = True` but can't kill the Claude child process. The daemon waits up to 2.5 hours for the session to finish naturally.

**Solution:** Store the `Popen` handle in `session.py` via a callback, and kill it on force-stop.

**Files:**
- Modify: `taskmanager/daemon/session.py` — accept an optional `proc_callback` to expose the Popen handle
- Modify: `taskmanager/daemon/runner.py` — pass callback, kill proc on force-stop
- Modify: `tests/test_daemon_session.py` — test callback invocation
- Modify: `tests/test_daemon_integration.py` — test force-stop kills proc

- [ ] **Step 1: Write test for proc_callback**

```python
# tests/test_daemon_session.py
def test_calls_proc_callback(self, tmp_path):
    mock_proc = MagicMock()
    mock_proc.stdout = io.StringIO("")
    mock_proc.stderr = io.StringIO("")
    mock_proc.wait.return_value = None
    mock_proc.returncode = 0

    captured = {}
    def on_proc(p):
        captured["proc"] = p

    with patch("subprocess.Popen", return_value=mock_proc):
        run_session(
            issue_identifier="LAN-99",
            working_dir=tmp_path,
            log_file=None,
            timeout=10,
            proc_callback=on_proc,
        )

    assert captured["proc"] is mock_proc
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `uv run pytest tests/test_daemon_session.py::TestRunSession::test_calls_proc_callback -v`

- [ ] **Step 3: Add `proc_callback` parameter to `run_session`**

In `session.py`, add `proc_callback: Callable[[subprocess.Popen], None] | None = None` parameter. After `Popen` is created, call it:

```python
proc = subprocess.Popen(...)

if proc_callback:
    proc_callback(proc)
```

Add import: `from collections.abc import Callable`

- [ ] **Step 4: Run test — expect PASS**

Run: `uv run pytest tests/test_daemon_session.py -v`

- [ ] **Step 5: Wire up in runner**

In `runner.py:_process_issue`, pass a callback that stores the proc:

```python
def _on_proc(proc: subprocess.Popen) -> None:
    self._active_proc = proc

result = session.run_session(
    issue_identifier=selected.identifier,
    working_dir=working_dir,
    log_file=log_file,
    timeout=self._timeout,
    issue_id=selected.issue_id,
    proc_callback=_on_proc,
)

self._active_proc = None
```

Update `_handle_signal` to kill the proc on force-stop:

```python
def _handle_signal(self, signum: int, _frame: object) -> None:
    if self._draining:
        log.info("Second signal received — force stopping")
        self._force_stop = True
        if self._active_proc:
            log.info("Killing active session process (pid=%d)", self._active_proc.pid)
            self._active_proc.kill()
    else:
        log.info(
            "Signal %d received — draining (finish current session, then exit)",
            signum,
        )
        self._draining = True
```

- [ ] **Step 6: Write test for force-stop killing proc**

```python
# tests/test_daemon_integration.py
class TestForceStop:
    def test_second_signal_kills_active_proc(self):
        runner = DaemonRunner()
        mock_proc = MagicMock()
        runner._active_proc = mock_proc

        runner._handle_signal(signal.SIGINT, None)  # first — drain
        runner._handle_signal(signal.SIGINT, None)  # second — force stop

        mock_proc.kill.assert_called_once()
```

- [ ] **Step 7: Run all tests**

Run: `uv run pytest tests/ -v`

- [ ] **Step 8: Lint and commit**

```bash
uv run ruff check --fix taskmanager/daemon/runner.py taskmanager/daemon/session.py tests/test_daemon_session.py tests/test_daemon_integration.py && uv run ruff format taskmanager/daemon/runner.py taskmanager/daemon/session.py tests/test_daemon_session.py tests/test_daemon_integration.py
git add taskmanager/daemon/runner.py taskmanager/daemon/session.py tests/test_daemon_session.py tests/test_daemon_integration.py
git commit -m "Wire force-stop signal to kill active Claude session process"
```

---

### Task 6: Fix quarantine error sub-issue assignee

**Problem:** `_quarantine_issue` (line 268) assigns error sub-issues to `operator_id` (the Claude agent). The human should be assigned since they need to investigate and un-quarantine.

**Solution:** Use `issue_defaults.assignee_id` from config (the human reviewer) instead of `operator_id`.

**Files:**
- Modify: `taskmanager/daemon/runner.py:238-297` — use correct assignee
- Modify: `tests/test_daemon_integration.py` — verify assignee in quarantine test

- [ ] **Step 1: Write test verifying assignee**

```python
# tests/test_daemon_integration.py — update TestQuarantine
def test_quarantine_assigns_to_human(self, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "taskmanager.daemon.state.STATE_FILE", tmp_path / "state.yaml"
    )
    monkeypatch.setattr("taskmanager.daemon.state.STATE_DIR", tmp_path)

    runner = DaemonRunner()
    runner._state = DaemonState()

    from taskmanager.daemon.selector import SelectedIssue

    selected = SelectedIssue(
        issue_id="id-123",
        identifier="LAN-99",
        title="Test Issue",
        status="In Progress",
        priority=3,
        project_id="p1",
        project_name="My Project",
    )

    mock_config = {
        "team": {"id": "team-1"},
        "operator": {"id": "op-1"},
        "issue_defaults": {"assignee_id": "human-1"},
    }

    calls = []
    def capture_run(*args, **kwargs):
        calls.append(args[0] if args else kwargs.get("args", []))
        return MagicMock(returncode=0)

    with (
        patch("taskmanager.daemon.runner.config.load_config", return_value=mock_config),
        patch("taskmanager.daemon.runner.selector._find_scripts_dir", return_value=tmp_path),
        patch("taskmanager.daemon.runner.selector._find_venv_python", return_value="python"),
        patch("subprocess.run", side_effect=capture_run),
    ):
        runner._quarantine_issue(selected, "timed out")

    # The first subprocess.run call creates the error sub-issue
    create_call = calls[0]
    assignee_idx = create_call.index("--assignee") + 1
    assert create_call[assignee_idx] == "human-1"
```

- [ ] **Step 2: Run test — expect FAIL (still using operator_id)**

Run: `uv run pytest tests/test_daemon_integration.py::TestQuarantine::test_quarantine_assigns_to_human -v`

- [ ] **Step 3: Fix the assignee in `_quarantine_issue`**

In `runner.py:_quarantine_issue`, change:
```python
operator_id = cfg.get("operator", {}).get("id", "")
```
to:
```python
human_id = cfg.get("issue_defaults", {}).get("assignee_id", "")
```

And update the subprocess args:
```python
*(["--assignee", human_id] if human_id else []),
```

- [ ] **Step 4: Run all tests**

Run: `uv run pytest tests/ -v`

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check --fix taskmanager/daemon/runner.py tests/test_daemon_integration.py && uv run ruff format taskmanager/daemon/runner.py tests/test_daemon_integration.py
git add taskmanager/daemon/runner.py tests/test_daemon_integration.py
git commit -m "Assign quarantine error sub-issues to human reviewer, not operator"
```

---

### Task 7: Rename shadowed `state` variable in forgejo.py

**Problem:** Line 71 uses `state` as a local variable name, shadowing the Python builtin. Minor code smell.

**Files:**
- Modify: `taskmanager/githost/forgejo.py` — rename to `pr_state`
- Modify: `tests/test_githost.py` — no changes needed (tests don't reference the variable)

- [ ] **Step 1: Rename in forgejo.py**

Change line 71 and the reference on line 113 (in the return dict):

```python
pr_state = "merged" if pr.get("merged") else pr["state"]
```

And in the return dict:
```python
return {
    "state": pr_state,
    ...
}
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/test_githost.py -v`

- [ ] **Step 3: Lint and commit**

```bash
uv run ruff check --fix taskmanager/githost/forgejo.py && uv run ruff format taskmanager/githost/forgejo.py
git add taskmanager/githost/forgejo.py
git commit -m "Rename shadowed state variable to pr_state in forgejo backend"
```

---

## Dependency Order

Tasks 1 and 4 are coupled (Task 4 restructures code Task 1 modifies). Execute Task 1 first, then Task 4.

All other tasks are independent and can be parallelized:
- Tasks 2, 3, 5, 6, 7 can run concurrently
- Task 1 → Task 4 must be sequential

## Version Bump

After all tasks complete, bump version in both files:
- `.claude-plugin/plugin.json` — increment version
- `pyproject.toml` — match version

---
