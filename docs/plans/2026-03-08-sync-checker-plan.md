# Sync Checker Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a CLI tool that tracks upstream sources for forked plugins and reports when they've diverged.

**Architecture:** Standalone Python script using `uv run` inline metadata. `sources.json` at repo root stores provenance. Script uses git subprocess calls (ls-remote, shallow clone, diff) to compare upstream vs local state. Functions are modular to support future `--merge` flag.

**Tech Stack:** Python 3.12+, stdlib only (subprocess, json, argparse, pathlib, tempfile), uv for running.

---

### Task 1: Create sources.json with initial tracking data

**Files:**
- Create: `sources.json`

**Step 1: Create the manifest**

```json
{
  "plugins": {
    "ask-questions-if-underspecified": {
      "upstream_repo": "https://github.com/trailofbits/skills.git",
      "upstream_path": "plugins/ask-questions-if-underspecified",
      "upstream_ref": "main",
      "last_synced_commit": "c6097699e4553f0dda4db615330f4a5097c4ff99",
      "last_checked": null,
      "local_modifications": false
    }
  }
}
```

**Step 2: Commit**

```bash
git add sources.json
git commit -m "Add sources.json to track upstream plugin provenance"
```

---

### Task 2: Scaffold sync-check.py with argument parsing

**Files:**
- Create: `scripts/sync-check.py`

**Step 1: Create script with uv inline metadata and CLI skeleton**

```python
# /// script
# requires-python = ">=3.12"
# ///
"""Check upstream sources for plugin updates."""

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCES_FILE = REPO_ROOT / "sources.json"


def load_sources() -> dict:
    """Load sources.json from repo root."""
    if not SOURCES_FILE.exists():
        print(f"Error: {SOURCES_FILE} not found", file=sys.stderr)
        sys.exit(1)
    return json.loads(SOURCES_FILE.read_text())


def save_sources(data: dict) -> None:
    """Write sources.json back to repo root."""
    SOURCES_FILE.write_text(json.dumps(data, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Check upstream plugin sources for updates")
    parser.add_argument("--plugin", help="Check a specific plugin only")
    parser.add_argument("--add", action="store_true", help="Add a new tracked plugin")
    parser.add_argument("--mark-synced", action="store_true", help="Mark plugin as synced to current upstream")
    parser.add_argument("--name", help="Plugin name (for --add)")
    parser.add_argument("--repo", help="Upstream git repo URL (for --add)")
    parser.add_argument("--path", help="Path within upstream repo (for --add)")
    parser.add_argument("--ref", default="main", help="Upstream branch/tag (for --add, default: main)")
    args = parser.parse_args()

    if args.add:
        add_plugin(args)
    elif args.mark_synced:
        mark_synced(args)
    else:
        check_plugins(args)


if __name__ == "__main__":
    main()
```

**Step 2: Verify it runs**

Run: `uv run scripts/sync-check.py --help`
Expected: Help text with all arguments listed.

**Step 3: Commit**

```bash
git add scripts/sync-check.py
git commit -m "Scaffold sync-check.py with CLI argument parsing"
```

---

### Task 3: Implement --add command

**Files:**
- Modify: `scripts/sync-check.py`

**Step 1: Implement add_plugin function**

Add above `main()`:

```python
def get_upstream_head(repo_url: str, ref: str) -> str:
    """Get the current HEAD commit of an upstream ref via ls-remote."""
    result = subprocess.run(
        ["git", "ls-remote", repo_url, f"refs/heads/{ref}"],
        capture_output=True, text=True, check=True, timeout=30,
    )
    if not result.stdout.strip():
        print(f"Error: Could not find ref '{ref}' in {repo_url}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.split()[0]


def add_plugin(args: argparse.Namespace) -> None:
    """Add a new plugin to sources.json."""
    if not all([args.name, args.repo, args.path]):
        print("Error: --add requires --name, --repo, and --path", file=sys.stderr)
        sys.exit(1)

    data = load_sources()
    if args.name in data["plugins"]:
        print(f"Error: Plugin '{args.name}' already tracked", file=sys.stderr)
        sys.exit(1)

    head = get_upstream_head(args.repo, args.ref)
    now = datetime.now(timezone.utc).isoformat()

    data["plugins"][args.name] = {
        "upstream_repo": args.repo,
        "upstream_path": args.path,
        "upstream_ref": args.ref,
        "last_synced_commit": head,
        "last_checked": now,
        "local_modifications": False,
    }
    save_sources(data)
    print(f"Added '{args.name}' tracking {args.repo} @ {args.ref} ({head[:12]})")
```

**Step 2: Test it manually**

Run: `uv run scripts/sync-check.py --add --name test-plugin --repo https://github.com/trailofbits/skills.git --path plugins/constant-time-analysis --ref main`
Expected: "Added 'test-plugin' tracking ..." and `sources.json` updated with new entry.

Then remove the test entry from `sources.json` (revert to just the original plugin).

**Step 3: Commit**

```bash
git add scripts/sync-check.py
git commit -m "Implement --add command for tracking new upstream plugins"
```

---

### Task 4: Implement check command (core logic)

**Files:**
- Modify: `scripts/sync-check.py`

**Step 1: Implement check_plugins and check_single_plugin**

Add above `main()`:

```python
def has_local_modifications(plugin_name: str, synced_commit: str) -> bool:
    """Check if local plugin dir has modifications vs the last synced state.

    Uses git diff to compare working tree against the commit where we last synced.
    Falls back to checking git status if the synced commit predates our repo.
    """
    plugin_dir = REPO_ROOT / "plugins" / plugin_name
    if not plugin_dir.exists():
        return False
    result = subprocess.run(
        ["git", "status", "--porcelain", str(plugin_dir)],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    if result.stdout.strip():
        return True
    # Check committed changes since initial add
    result = subprocess.run(
        ["git", "log", "--oneline", "-1", "--", str(plugin_dir)],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    return bool(result.stdout.strip())


def get_upstream_diff(repo_url: str, ref: str, path: str,
                      old_commit: str, new_commit: str) -> list[str]:
    """Fetch upstream and diff between old and new commits for the plugin path."""
    changed_files = []
    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.run(
            ["git", "clone", "--bare", "--filter=blob:none", repo_url, tmpdir],
            capture_output=True, text=True, timeout=120,
        )
        result = subprocess.run(
            ["git", "diff", "--name-only", old_commit, new_commit, "--", path],
            capture_output=True, text=True, cwd=tmpdir,
        )
        if result.returncode == 0:
            changed_files = [f for f in result.stdout.strip().splitlines() if f]
    return changed_files


def determine_status(upstream_changed: bool, local_modified: bool) -> str:
    """Determine sync status from upstream/local state."""
    if upstream_changed and local_modified:
        return "both-changed"
    if upstream_changed:
        return "upstream-changed"
    if local_modified:
        return "local-modified"
    return "up-to-date"


def status_action(status: str) -> str:
    """Return recommended action for a given status."""
    actions = {
        "up-to-date": "No action needed.",
        "upstream-changed": "Safe to pull upstream changes.",
        "local-modified": "Local changes only. Upstream unchanged.",
        "both-changed": "Both sides changed. Manual merge needed.",
    }
    return actions[status]


def check_single_plugin(name: str, info: dict) -> dict:
    """Check a single plugin against its upstream. Returns status dict."""
    print(f"\n{name}:")
    print(f"  Upstream: {info['upstream_repo']} @ {info['upstream_ref']}")

    current_head = get_upstream_head(info["upstream_repo"], info["upstream_ref"])
    synced = info["last_synced_commit"]
    upstream_changed = current_head != synced

    print(f"  Last synced: {synced[:12]}")
    if upstream_changed:
        print(f"  Current upstream: {current_head[:12]}")

    local_modified = has_local_modifications(name, synced)
    print(f"  Local modifications: {'yes' if local_modified else 'no'}")

    status = determine_status(upstream_changed, local_modified)
    print(f"  Status: {status}")
    print(f"  Action: {status_action(status)}")

    if upstream_changed:
        changed = get_upstream_diff(
            info["upstream_repo"], info["upstream_ref"],
            info["upstream_path"], synced, current_head,
        )
        if changed:
            print("  Files changed upstream:")
            for f in changed:
                print(f"    M {f}")

    return {
        "status": status,
        "upstream_head": current_head,
        "local_modified": local_modified,
    }


def check_plugins(args: argparse.Namespace) -> None:
    """Check all (or one) tracked plugins for upstream changes."""
    data = load_sources()
    plugins = data["plugins"]

    if args.plugin:
        if args.plugin not in plugins:
            print(f"Error: Plugin '{args.plugin}' not tracked", file=sys.stderr)
            sys.exit(1)
        plugins = {args.plugin: plugins[args.plugin]}

    print(f"Checking {len(plugins)} tracked plugin(s)...")

    now = datetime.now(timezone.utc).isoformat()
    for name, info in plugins.items():
        result = check_single_plugin(name, info)
        data["plugins"][name]["last_checked"] = now
        data["plugins"][name]["local_modifications"] = result["local_modified"]

    save_sources(data)
```

**Step 2: Test it**

Run: `uv run scripts/sync-check.py`
Expected: Status report for `ask-questions-if-underspecified` showing `up-to-date` (since we just synced).

Run: `uv run scripts/sync-check.py --plugin ask-questions-if-underspecified`
Expected: Same report, single plugin only.

**Step 3: Commit**

```bash
git add scripts/sync-check.py
git commit -m "Implement upstream check and diff reporting"
```

---

### Task 5: Implement --mark-synced command

**Files:**
- Modify: `scripts/sync-check.py`

**Step 1: Implement mark_synced function**

Add above `main()`:

```python
def mark_synced(args: argparse.Namespace) -> None:
    """Mark a plugin as synced to current upstream HEAD."""
    if not args.plugin:
        print("Error: --mark-synced requires --plugin", file=sys.stderr)
        sys.exit(1)

    data = load_sources()
    if args.plugin not in data["plugins"]:
        print(f"Error: Plugin '{args.plugin}' not tracked", file=sys.stderr)
        sys.exit(1)

    info = data["plugins"][args.plugin]
    head = get_upstream_head(info["upstream_repo"], info["upstream_ref"])
    now = datetime.now(timezone.utc).isoformat()

    data["plugins"][args.plugin]["last_synced_commit"] = head
    data["plugins"][args.plugin]["last_checked"] = now
    data["plugins"][args.plugin]["local_modifications"] = False
    save_sources(data)
    print(f"Marked '{args.plugin}' as synced to {head[:12]}")
```

**Step 2: Test it**

Run: `uv run scripts/sync-check.py --mark-synced --plugin ask-questions-if-underspecified`
Expected: "Marked 'ask-questions-if-underspecified' as synced to ..."

**Step 3: Commit**

```bash
git add scripts/sync-check.py
git commit -m "Implement --mark-synced command"
```

---

### Task 6: Final integration test and push

**Step 1: Run full check**

Run: `uv run scripts/sync-check.py`
Expected: Clean status report.

**Step 2: Test --add with a second plugin then remove it**

Run: `uv run scripts/sync-check.py --add --name test-plugin --repo https://github.com/trailofbits/skills.git --path plugins/constant-time-analysis --ref main`
Expected: Plugin added successfully.

Run: `uv run scripts/sync-check.py`
Expected: Both plugins reported.

Then revert `sources.json` to remove the test plugin.

**Step 3: Final commit and push**

```bash
git add -A
git commit -m "Integration test cleanup"
git push origin main
```
