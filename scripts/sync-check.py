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


def get_upstream_head(repo_url: str, ref: str) -> str:
    """Get the current HEAD commit of an upstream ref via ls-remote."""
    result = subprocess.run(
        ["git", "ls-remote", repo_url, f"refs/heads/{ref}"],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
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


def has_local_modifications(plugin_name: str, info: dict) -> tuple[bool, str]:
    """Check if local plugin dir differs from upstream at last_synced_commit.

    Returns (modified, diff_output) tuple to avoid cloning twice.
    """
    plugin_dir = REPO_ROOT / "plugins" / plugin_name
    if not plugin_dir.exists():
        return False, ""
    # Check for uncommitted changes first
    result = subprocess.run(
        ["git", "status", "--porcelain", str(plugin_dir)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    uncommitted = result.stdout.strip()
    # Compare actual content against upstream at synced commit
    diff_output = get_local_diff(plugin_name, info)
    has_diff = diff_output != "  No differences found."
    modified = bool(uncommitted) or has_diff
    return modified, diff_output


def clone_upstream_bare(repo_url: str) -> tempfile.TemporaryDirectory:
    """Clone upstream repo as bare with partial filter. Returns temp dir context."""
    tmpdir = tempfile.TemporaryDirectory()
    subprocess.run(
        ["git", "clone", "--bare", "--filter=blob:none", repo_url, tmpdir.name],
        capture_output=True,
        text=True,
        timeout=120,
    )
    return tmpdir


def get_upstream_diff(
    repo_url: str, ref: str, path: str, old_commit: str, new_commit: str
) -> list[str]:
    """Fetch upstream and diff between old and new commits for the plugin path."""
    changed_files = []
    with clone_upstream_bare(repo_url) as tmpdir:
        result = subprocess.run(
            ["git", "diff", "--name-only", old_commit, new_commit, "--", path],
            capture_output=True,
            text=True,
            cwd=tmpdir,
        )
        if result.returncode == 0:
            changed_files = [f for f in result.stdout.strip().splitlines() if f]
    return changed_files


def get_local_diff(plugin_name: str, info: dict) -> str:
    """Diff local plugin directory against upstream at last_synced_commit."""
    with clone_upstream_bare(info["upstream_repo"]) as tmpdir:
        # Extract upstream version at synced commit to a temp dir
        upstream_path = info["upstream_path"]
        commit = info["last_synced_commit"]
        with tempfile.TemporaryDirectory() as extractdir:
            # Use git archive to extract the upstream plugin at the synced commit
            result = subprocess.run(
                ["git", "archive", commit, "--", upstream_path],
                capture_output=True,
                cwd=tmpdir,
            )
            if result.returncode != 0:
                return "  Error: Could not extract upstream at synced commit."
            # Extract the archive
            subprocess.run(
                ["tar", "xf", "-"],
                input=result.stdout,
                capture_output=True,
                cwd=extractdir,
            )
            # Diff local vs extracted upstream
            local_dir = str(REPO_ROOT / "plugins" / plugin_name)
            upstream_dir = str(Path(extractdir) / upstream_path)
            result = subprocess.run(
                ["diff", "-ruN", upstream_dir, local_dir],
                capture_output=True,
                text=True,
            )
            return result.stdout if result.stdout else "  No differences found."


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


def check_single_plugin(name: str, info: dict, show_diff: bool = False) -> dict:
    """Check a single plugin against its upstream. Returns status dict."""
    print(f"\n{name}:")
    print(f"  Upstream: {info['upstream_repo']} @ {info['upstream_ref']}")

    current_head = get_upstream_head(info["upstream_repo"], info["upstream_ref"])
    synced = info["last_synced_commit"]
    upstream_changed = current_head != synced

    print(f"  Last synced: {synced[:12]}")
    if upstream_changed:
        print(f"  Current upstream: {current_head[:12]}")

    local_modified, local_diff = has_local_modifications(name, info)
    print(f"  Local modifications: {'yes' if local_modified else 'no'}")

    status = determine_status(upstream_changed, local_modified)
    print(f"  Status: {status}")
    print(f"  Action: {status_action(status)}")

    if upstream_changed:
        changed = get_upstream_diff(
            info["upstream_repo"],
            info["upstream_ref"],
            info["upstream_path"],
            synced,
            current_head,
        )
        if changed:
            print("  Files changed upstream:")
            for f in changed:
                print(f"    M {f}")

    if show_diff and local_modified:
        print("  Local diff:")
        print(local_diff)

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

    show_diff = getattr(args, "diff", False)
    now = datetime.now(timezone.utc).isoformat()
    for name, info in plugins.items():
        result = check_single_plugin(name, info, show_diff=show_diff)
        data["plugins"][name]["last_checked"] = now
        data["plugins"][name]["local_modifications"] = result["local_modified"]

    save_sources(data)


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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check upstream plugin sources for updates"
    )
    parser.add_argument("--plugin", help="Check a specific plugin only")
    parser.add_argument(
        "--diff", action="store_true", help="Show full diff for local/upstream changes"
    )
    parser.add_argument("--add", action="store_true", help="Add a new tracked plugin")
    parser.add_argument(
        "--mark-synced",
        action="store_true",
        help="Mark plugin as synced to current upstream",
    )
    parser.add_argument("--name", help="Plugin name (for --add)")
    parser.add_argument("--repo", help="Upstream git repo URL (for --add)")
    parser.add_argument("--path", help="Path within upstream repo (for --add)")
    parser.add_argument(
        "--ref", default="main", help="Upstream branch/tag (for --add, default: main)"
    )
    args = parser.parse_args()

    if args.add:
        add_plugin(args)
    elif args.mark_synced:
        mark_synced(args)
    else:
        check_plugins(args)


if __name__ == "__main__":
    main()
