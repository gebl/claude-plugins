# Review Issue Reconciler

## Problem

Review sub-issues created for PR review sit in an open state until a human manually marks them Done. When the PR is merged or closed on the git host, the Review sub-issue becomes stale — the parent issue stays Blocked even though the review is effectively complete. Similarly, PR comments go unnoticed because they live on the git host rather than Linear where the daemon watches for feedback.

## Solution

A reconciler module (`taskmanager/daemon/reconciler.py`) that runs as a pre-pass before issue selection on each daemon poll cycle. It synchronizes Review sub-issue state with the actual PR state on the git host.

## Behavior

### Input

- All open Review-labeled sub-issues (status not Done/Canceled)
- PR URL extracted from each issue's `description` field

### PR URL Extraction

The description follows the pattern set by `work-flow.md` step g.5:

```
PR submitted for review: <pr-url>

<summary>

Please review the PR and either merge it or add a comment with feedback.
```

Extract the first `https://` URL from the description. If no URL is found, skip the issue (it's a general review question, not a PR review).

### Actions by PR State

| PR State | Action |
|----------|--------|
| `merged` | Post `**[Activity]** Auto-closed: PR was merged.` on the Review sub-issue, then mark it Done |
| `closed` | Post `**[Activity]** Auto-closed: PR was closed.` on the Review sub-issue, then mark it Done |
| `open` + has comments | Mirror new PR comments to the Review sub-issue (see below) |
| `open` + no comments | No action — still awaiting review |
| `not_found` | No action — PR may not exist yet |

### Comment Mirroring

PR comments (reviews and issue comments from the git host) are posted to the Review sub-issue with the prefix:

```
**[PR Comment]** @author: <body>
```

**Deduplication**: Before posting, fetch existing comments on the Review sub-issue. A PR comment is considered already-mirrored if any existing comment starts with `**[PR Comment]** @{author}:` and contains the same body text. This is stateless and self-healing across daemon restarts.

## Architecture

### New File: `taskmanager/daemon/reconciler.py`

Functions:
- `reconcile_review_issues()` — main entry point, fetches open Review issues and processes each
- `_extract_pr_url(description: str) -> str | None` — regex extraction of first HTTPS URL
- `_check_and_reconcile(issue: dict) -> None` — checks PR status and takes appropriate action
- `_auto_close_review(issue: dict, reason: str) -> None` — posts Activity comment and marks Done
- `_mirror_pr_comments(issue: dict, pr_comments: list[dict]) -> None` — dedup-aware comment posting

Uses the same `_run_script` / `_run_list_script` subprocess pattern as `selector.py` (shared via import or duplicated as private helpers).

### Githost Changes

**`githost/base.py`**:
- Add `parse_pr_url(url: str) -> tuple[str, str, str, int]` utility — returns `(base_url, owner, repo, pr_number)`
- Add `check_pr_status_by_url(pr_url: str) -> dict` to the `GitHostBackend` protocol

**`githost/forgejo.py`**:
- Implement `check_pr_status_by_url(pr_url)` — parses URL, hits Forgejo API by PR number directly
- Returns same dict shape as `check_pr_status`: `{state, comments, pr_url, pr_number}`

### Integration

In `runner.py` `_main_loop()`, call `reconciler.reconcile_review_issues()` before `selector.select_next_issue()`. The reconciler mutates issue state (closes issues, posts comments) so that the subsequent selection phase sees the updated state.

```
runner._main_loop()
    ├── reconciler.reconcile_review_issues()   # pre-pass: sync Review issues with PR state
    └── selector.select_next_issue()           # read-only selection (unchanged)
```

### Script Changes

**`scripts/check_pr_status.py`**: Add optional `--pr-url` flag as alternative to `--repo-url`/`--branch`. When provided, uses `check_pr_status_by_url()` instead of `check_pr_status()`.

## Design Decisions

- **Description-only URL extraction**: The PR URL is placed in the description by `work-flow.md`. No need to scan comments.
- **`**[PR Comment]**` prefix**: Follows existing `**[Activity]**` pattern. The `_has_human_comments` filter in `selector.py` should be updated to also skip `**[PR Comment]**` prefixed comments (they are mirrored, not human-authored on Linear).
- **Stateless dedup**: Comparing against existing Linear comments rather than tracking in daemon state. Review sub-issues have low comment volume, and this approach survives daemon restarts.
- **Separate module**: The reconciler mutates state; the selector is read-only. Keeping them separate preserves the selector's contract.
