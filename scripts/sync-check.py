# /// script
# requires-python = ">=3.12"
# ///
"""Check upstream sources for plugin updates, import skills, and track verification."""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCES_FILE = REPO_ROOT / "sources.json"
MARKETPLACE_FILE = REPO_ROOT / ".claude-plugin" / "marketplace.json"

EXECUTABLE_EXTENSIONS = {".sh", ".bash", ".zsh", ".py", ".js", ".ts", ".rb", ".pl"}


def load_sources() -> dict:
    """Load sources.json from repo root."""
    if not SOURCES_FILE.exists():
        print(f"Error: {SOURCES_FILE} not found", file=sys.stderr)
        sys.exit(1)
    return json.loads(SOURCES_FILE.read_text())


def save_sources(data: dict) -> None:
    """Write sources.json back to repo root."""
    SOURCES_FILE.write_text(json.dumps(data, indent=2) + "\n")


def load_marketplace() -> dict:
    """Load marketplace.json."""
    if not MARKETPLACE_FILE.exists():
        print(f"Error: {MARKETPLACE_FILE} not found", file=sys.stderr)
        sys.exit(1)
    return json.loads(MARKETPLACE_FILE.read_text())


def save_marketplace(data: dict) -> None:
    """Write marketplace.json back."""
    MARKETPLACE_FILE.write_text(json.dumps(data, indent=2) + "\n")


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


def detect_executable_code(directory: Path) -> list[str]:
    """Scan a directory for files containing executable code.

    Checks file extensions, shebang lines, and executable permissions.
    Returns list of paths relative to the directory.
    """
    executables = []
    if not directory.exists():
        return executables

    for path in directory.rglob("*"):
        if not path.is_file():
            continue
        rel = str(path.relative_to(directory))

        # Check extension
        if path.suffix.lower() in EXECUTABLE_EXTENSIONS:
            executables.append(rel)
            continue

        # Check executable permission
        if os.access(path, os.X_OK):
            executables.append(rel)
            continue

        # Check shebang
        try:
            with open(path, "rb") as f:
                first_bytes = f.read(64)
                if first_bytes.startswith(b"#!"):
                    executables.append(rel)
        except (OSError, UnicodeDecodeError):
            pass

    return sorted(executables)


def parse_skill_frontmatter(skill_md_path: Path) -> dict | None:
    """Parse YAML frontmatter from a SKILL.md file.

    Returns dict with name, description, version (if present), or None on failure.
    """
    text = skill_md_path.read_text()
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not match:
        return None

    frontmatter = {}
    for line in match.group(1).splitlines():
        line = line.strip()
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip().lower()
            value = value.strip().strip("\"'")
            if key in ("name", "description", "version"):
                frontmatter[key] = value

    if "name" not in frontmatter or "description" not in frontmatter:
        return None

    return frontmatter


def detect_dependencies(directory: Path) -> list[str]:
    """Detect dependency files that may need installation."""
    dep_files = []
    patterns = [
        "requirements.txt",
        "pyproject.toml",
        "package.json",
        "Gemfile",
        "go.mod",
        "Cargo.toml",
    ]
    for path in directory.rglob("*"):
        if path.name in patterns:
            dep_files.append(str(path.relative_to(directory)))
    return sorted(dep_files)


# --- Import skill ---


def import_skill(args: argparse.Namespace) -> None:
    """Import a raw skill from an upstream repo, wrapping it as a plugin."""
    if not all([args.name, args.repo, args.path]):
        print(
            "Error: --import-skill requires --name, --repo, and --path",
            file=sys.stderr,
        )
        sys.exit(1)

    data = load_sources()
    if args.name in data["plugins"]:
        print(f"Error: Plugin '{args.name}' already tracked", file=sys.stderr)
        sys.exit(1)

    head = get_upstream_head(args.repo, args.ref)

    # Clone and extract the skill
    with clone_upstream_bare(args.repo) as bare_dir:
        with tempfile.TemporaryDirectory() as extractdir:
            result = subprocess.run(
                ["git", "archive", head, "--", args.path],
                capture_output=True,
                cwd=bare_dir,
            )
            if result.returncode != 0:
                print(
                    f"Error: Could not extract '{args.path}' from {args.repo}",
                    file=sys.stderr,
                )
                sys.exit(1)
            subprocess.run(
                ["tar", "xf", "-"],
                input=result.stdout,
                capture_output=True,
                cwd=extractdir,
            )

            source_dir = Path(extractdir) / args.path

            # Find SKILL.md
            skill_md = source_dir / "SKILL.md"
            if not skill_md.exists():
                # Check one level down
                for candidate in source_dir.rglob("SKILL.md"):
                    skill_md = candidate
                    break

            if not skill_md.exists():
                print(
                    f"Error: No SKILL.md found in '{args.path}'",
                    file=sys.stderr,
                )
                sys.exit(1)

            # Parse frontmatter
            frontmatter = parse_skill_frontmatter(skill_md)
            if not frontmatter and not args.force:
                print(
                    "Error: SKILL.md has malformed or missing frontmatter "
                    "(requires 'name' and 'description').\n"
                    "Use --force to import anyway with manual metadata.",
                    file=sys.stderr,
                )
                sys.exit(1)

            if not frontmatter:
                frontmatter = {
                    "name": args.name,
                    "description": f"Imported skill: {args.name}",
                }
                print("Warning: Using fallback metadata due to --force")

            description = frontmatter.get("description", "")
            version = frontmatter.get("version", "0.1.0")

            # Check for dependencies
            deps = detect_dependencies(source_dir)
            if deps:
                print("Warning: Dependency files detected (may need installation):")
                for d in deps:
                    print(f"  {d}")

            # Detect executable code
            executables = detect_executable_code(source_dir)

            # Build plugin structure
            plugin_dir = REPO_ROOT / "plugins" / args.name
            if plugin_dir.exists():
                print(
                    f"Error: Directory plugins/{args.name} already exists",
                    file=sys.stderr,
                )
                sys.exit(1)

            # Create plugin wrapper
            plugin_meta_dir = plugin_dir / ".claude-plugin"
            plugin_meta_dir.mkdir(parents=True)

            plugin_json = {
                "name": args.name,
                "version": version,
                "description": description,
            }
            (plugin_meta_dir / "plugin.json").write_text(
                json.dumps(plugin_json, indent=2) + "\n"
            )

            # Copy skill files into skills/<name>/
            skill_dest = plugin_dir / "skills" / args.name
            skill_dest.mkdir(parents=True)
            for item in source_dir.iterdir():
                dest = skill_dest / item.name
                if item.is_dir():
                    shutil.copytree(item, dest)
                else:
                    shutil.copy2(item, dest)

    # Register in sources.json
    now = datetime.now(timezone.utc).isoformat()
    data["plugins"][args.name] = {
        "upstream_repo": args.repo,
        "upstream_path": args.path,
        "upstream_ref": args.ref,
        "upstream_type": "raw-skill",
        "last_synced_commit": head,
        "last_checked": now,
        "local_modifications": False,
        "has_executable_code": bool(executables),
        "verified": False,
    }
    save_sources(data)

    # Register in marketplace.json
    marketplace = load_marketplace()
    marketplace["plugins"].append(
        {
            "name": args.name,
            "version": version,
            "description": description,
            "source": f"./plugins/{args.name}",
        }
    )
    save_marketplace(marketplace)

    print(f"Imported '{args.name}' as plugin from {args.repo} @ {args.ref}")
    if executables:
        print(f"  Contains executable code ({len(executables)} file(s)):")
        for e in executables[:10]:
            print(f"    {e}")
        if len(executables) > 10:
            print(f"    ... and {len(executables) - 10} more")
    print("  Verified: no (use --mark-verified to approve after review)")


# --- Add plugin (existing, updated with new fields) ---


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

    # Detect executable code in the local plugin directory
    plugin_dir = REPO_ROOT / "plugins" / args.name
    executables = detect_executable_code(plugin_dir) if plugin_dir.exists() else []

    data["plugins"][args.name] = {
        "upstream_repo": args.repo,
        "upstream_path": args.path,
        "upstream_ref": args.ref,
        "upstream_type": "plugin",
        "last_synced_commit": head,
        "last_checked": now,
        "local_modifications": False,
        "has_executable_code": bool(executables),
        "verified": False,
    }
    save_sources(data)
    print(f"Added '{args.name}' tracking {args.repo} @ {args.ref} ({head[:12]})")
    if executables:
        print(f"  Contains executable code ({len(executables)} file(s))")
    print("  Verified: no")


# --- Diff and check ---


def get_local_diff(plugin_name: str, info: dict) -> str:
    """Diff local plugin directory against upstream at last_synced_commit.

    For raw-skill imports, compares only the skills/<name>/ subtree against upstream.
    For plugin imports, compares the full plugin directory.
    """
    upstream_type = info.get("upstream_type", "plugin")

    with clone_upstream_bare(info["upstream_repo"]) as bare_dir:
        upstream_path = info["upstream_path"]
        commit = info["last_synced_commit"]
        with tempfile.TemporaryDirectory() as extractdir:
            result = subprocess.run(
                ["git", "archive", commit, "--", upstream_path],
                capture_output=True,
                cwd=bare_dir,
            )
            if result.returncode != 0:
                return "  Error: Could not extract upstream at synced commit."
            subprocess.run(
                ["tar", "xf", "-"],
                input=result.stdout,
                capture_output=True,
                cwd=extractdir,
            )

            upstream_dir = str(Path(extractdir) / upstream_path)

            if upstream_type == "raw-skill":
                # Compare only the skill content, not the generated wrapper
                local_dir = str(
                    REPO_ROOT / "plugins" / plugin_name / "skills" / plugin_name
                )
            else:
                local_dir = str(REPO_ROOT / "plugins" / plugin_name)

            result = subprocess.run(
                ["diff", "-ruN", upstream_dir, local_dir],
                capture_output=True,
                text=True,
            )
            return result.stdout if result.stdout else "  No differences found."


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
    upstream_type = info.get("upstream_type", "plugin")
    print(f"\n{name}:")
    print(f"  Upstream: {info['upstream_repo']} @ {info['upstream_ref']}")
    if upstream_type == "raw-skill":
        print("  Type: raw-skill (wrapped)")

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

    if info.get("has_executable_code"):
        verified = info.get("verified", False)
        print(f"  Executable code: yes (verified: {'yes' if verified else 'no'})")

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


# --- Mark synced / verified ---


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


def mark_verified(args: argparse.Namespace) -> None:
    """Mark a plugin as reviewed and verified."""
    if not args.plugin:
        print("Error: --mark-verified requires --plugin", file=sys.stderr)
        sys.exit(1)

    data = load_sources()
    if args.plugin not in data["plugins"]:
        print(f"Error: Plugin '{args.plugin}' not tracked", file=sys.stderr)
        sys.exit(1)

    data["plugins"][args.plugin]["verified"] = True
    save_sources(data)
    print(f"Marked '{args.plugin}' as verified")


# --- Pending verification ---


def list_pending(args: argparse.Namespace) -> None:
    """List all plugins pending verification. Always rescans for executable code."""
    data = load_sources()
    pending = []
    changed = False

    for name, info in data["plugins"].items():
        # Rescan executable code on every --pending run
        plugin_dir = REPO_ROOT / "plugins" / name
        executables = detect_executable_code(plugin_dir)
        has_exec = bool(executables)
        if info.get("has_executable_code") != has_exec:
            data["plugins"][name]["has_executable_code"] = has_exec
            changed = True

        if not info.get("verified", False):
            pending.append((name, info, executables))

    if changed:
        save_sources(data)

    if not pending:
        print("All plugins have been verified.")
        return

    print(f"Plugins pending verification ({len(pending)}):\n")
    for name, info, executables in pending:
        upstream_type = info.get("upstream_type", "plugin")
        repo = info["upstream_repo"]
        short_repo = repo.replace("https://github.com/", "").replace(".git", "")

        print(f"  {name}")
        print(f"    Source: {short_repo}")
        print(f"    Type: {upstream_type}")
        if executables:
            print(f"    !! Contains executable code ({len(executables)} file(s)):")
            for e in executables[:5]:
                print(f"       {e}")
            if len(executables) > 5:
                print(f"       ... and {len(executables) - 5} more")
        else:
            print("    Executable code: none detected")
        print()


# --- Main ---


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manage upstream plugin sources: check, import, verify"
    )
    parser.add_argument("--plugin", help="Target a specific plugin")
    parser.add_argument(
        "--diff", action="store_true", help="Show full diff for local/upstream changes"
    )

    group = parser.add_mutually_exclusive_group()
    group.add_argument("--add", action="store_true", help="Add a new tracked plugin")
    group.add_argument(
        "--import-skill",
        action="store_true",
        help="Import a raw skill and wrap it as a plugin",
    )
    group.add_argument(
        "--mark-synced",
        action="store_true",
        help="Mark plugin as synced to current upstream",
    )
    group.add_argument(
        "--mark-verified",
        action="store_true",
        help="Mark plugin as reviewed and verified",
    )
    group.add_argument(
        "--pending",
        action="store_true",
        help="List plugins pending verification",
    )

    parser.add_argument("--name", help="Plugin name (for --add/--import-skill)")
    parser.add_argument(
        "--repo", help="Upstream git repo URL (for --add/--import-skill)"
    )
    parser.add_argument(
        "--path", help="Path within upstream repo (for --add/--import-skill)"
    )
    parser.add_argument(
        "--ref",
        default="main",
        help="Upstream branch/tag (for --add/--import-skill, default: main)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force import even with malformed SKILL.md frontmatter",
    )
    args = parser.parse_args()

    if args.add:
        add_plugin(args)
    elif args.import_skill:
        import_skill(args)
    elif args.mark_synced:
        mark_synced(args)
    elif args.mark_verified:
        mark_verified(args)
    elif args.pending:
        list_pending(args)
    else:
        check_plugins(args)


if __name__ == "__main__":
    main()
