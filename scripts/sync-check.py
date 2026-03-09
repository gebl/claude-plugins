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
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCES_FILE = REPO_ROOT / "sources.json"
MARKETPLACE_FILE = REPO_ROOT / ".claude-plugin" / "marketplace.json"

EXECUTABLE_EXTENSIONS = {".sh", ".bash", ".zsh", ".py", ".js", ".ts", ".rb", ".pl"}
MAX_DISPLAY_EXECUTABLES = 10
MAX_DISPLAY_PENDING = 5
SEMGREP_CONFIGS = [
    "auto",
    "p/secrets",
    "p/gitleaks",
    "p/trailofbits",
    "p/command-injection",
    "p/supply-chain",
    "p/security-audit",
    "p/owasp-top-ten",
    "p/bash",
    "p/docker",
    str(Path(__file__).resolve().parent / "claude-plugin-rules.yaml"),
]
UPSTREAM_TYPE_PLUGIN = "plugin"
UPSTREAM_TYPE_RAW_SKILL = "raw-skill"


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
        check=False,
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
            with path.open("rb") as f:
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
        stripped = line.strip()
        if ":" in stripped:
            key, _, value = stripped.partition(":")
            key = key.strip().lower()
            value = value.strip().strip("\"'")
            if key in ("name", "description", "version"):
                frontmatter[key] = value

    if "name" not in frontmatter or "description" not in frontmatter:
        return None

    return frontmatter


# Tools that grant code execution or write access — flag when declared
DANGEROUS_TOOLS = {"Bash", "Write", "Edit", "NotebookEdit"}
# Tools that are always safe
SAFE_TOOLS = {
    "Read",
    "Grep",
    "Glob",
    "Agent",
    "WebSearch",
    "WebFetch",
    "LSP",
    "AskUserQuestion",
    "TodoRead",
    "TodoWrite",
    "TaskCreate",
    "TaskGet",
    "TaskList",
    "TaskUpdate",
    "Skill",
    "ToolSearch",
}


def parse_allowed_tools(skill_md_path: Path) -> list[str] | None:
    """Extract allowed-tools list from SKILL.md YAML frontmatter.

    Returns list of tool names, or None if no allowed-tools declared.
    """
    text = skill_md_path.read_text()
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not match:
        return None

    tools: list[str] = []
    in_allowed_tools = False
    for line in match.group(1).splitlines():
        stripped = line.strip()
        if stripped.startswith("allowed-tools:"):
            in_allowed_tools = True
            continue
        if in_allowed_tools:
            if stripped.startswith("- "):
                tools.append(stripped[2:].strip().strip("\"'"))
            else:
                break
    return tools if tools else None


def check_allowed_tools_policy(target: Path) -> list[str]:
    """Check all SKILL.md files under target for dangerous tool declarations.

    Returns a list of warning strings for each finding.
    """
    warnings: list[str] = []
    for skill_md in target.rglob("SKILL.md"):
        rel = skill_md.relative_to(target)
        tools = parse_allowed_tools(skill_md)
        if tools is None:
            continue

        dangerous_found = [t for t in tools if t in DANGEROUS_TOOLS]
        if dangerous_found:
            warnings.append(f"  {rel}: declares dangerous tools: {', '.join(dangerous_found)}")

        unknown = [t for t in tools if t not in DANGEROUS_TOOLS and t not in SAFE_TOOLS]
        if unknown:
            warnings.append(f"  {rel}: declares unknown tools: {', '.join(unknown)}")

    return warnings


def detect_dependencies(directory: Path) -> list[str]:
    """Detect dependency files that may need installation."""
    patterns = {
        "requirements.txt",
        "pyproject.toml",
        "package.json",
        "Gemfile",
        "go.mod",
        "Cargo.toml",
    }
    return sorted(
        str(path.relative_to(directory)) for path in directory.rglob("*") if path.name in patterns
    )


# --- Import skill ---


@contextmanager
def _extract_upstream(
    repo_url: str, commit: str, upstream_path: str
) -> Generator[Path, None, None]:
    """Clone upstream repo and extract a path to a temp directory.

    Yields the extracted source directory. Cleans up on exit.
    """
    with clone_upstream_bare(repo_url) as bare_dir, tempfile.TemporaryDirectory() as extract_dir:
        result = subprocess.run(
            ["git", "archive", commit, "--", upstream_path],
            check=False,
            capture_output=True,
            cwd=bare_dir,
        )
        if result.returncode != 0:
            print(
                f"Error: Could not extract '{upstream_path}' from {repo_url}",
                file=sys.stderr,
            )
            sys.exit(1)
        subprocess.run(
            ["tar", "xf", "-"],
            check=False,
            input=result.stdout,
            capture_output=True,
            cwd=extract_dir,
        )
        yield Path(extract_dir) / upstream_path


def _resolve_frontmatter(
    source_dir: Path, upstream_path: str, name: str, *, force: bool = False
) -> dict:
    """Find SKILL.md in source_dir and parse its frontmatter.

    Returns frontmatter dict. Exits on failure unless force is True.
    """
    skill_md = source_dir / "SKILL.md"
    if not skill_md.exists():
        for candidate in source_dir.rglob("SKILL.md"):
            skill_md = candidate
            break

    if not skill_md.exists():
        print(f"Error: No SKILL.md found in '{upstream_path}'", file=sys.stderr)
        sys.exit(1)

    frontmatter = parse_skill_frontmatter(skill_md)
    if not frontmatter and not force:
        print(
            "Error: SKILL.md has malformed or missing frontmatter "
            "(requires 'name' and 'description').\n"
            "Use --force to import anyway with manual metadata.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not frontmatter:
        frontmatter = {"name": name, "description": f"Imported skill: {name}"}
        print("Warning: Using fallback metadata due to --force")

    return frontmatter


def _build_plugin_structure(name: str, source_dir: Path, frontmatter: dict) -> None:
    """Create plugin directory with wrapper and copy skill files."""
    plugin_dir = REPO_ROOT / "plugins" / name
    if plugin_dir.exists():
        print(f"Error: Directory plugins/{name} already exists", file=sys.stderr)
        sys.exit(1)

    plugin_meta_dir = plugin_dir / ".claude-plugin"
    plugin_meta_dir.mkdir(parents=True)

    plugin_json = {
        "name": name,
        "version": frontmatter.get("version", "0.1.0"),
        "description": frontmatter.get("description", ""),
    }
    (plugin_meta_dir / "plugin.json").write_text(json.dumps(plugin_json, indent=2) + "\n")

    skill_dest = plugin_dir / "skills" / name
    skill_dest.mkdir(parents=True)
    for item in source_dir.iterdir():
        dest = skill_dest / item.name
        if item.is_dir():
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)


def _print_dry_run_summary(*, sources_entry: dict, marketplace_entry: dict) -> None:
    """Print what would be written to sources.json and marketplace.json."""
    print("\n  sources.json entry:")
    for key, value in sources_entry.items():
        print(f"    {key}: {value}")

    print("\n  marketplace.json entry:")
    for key, value in marketplace_entry.items():
        print(f"    {key}: {value}")


def _print_executable_summary(executables: list[str], *, max_display: int) -> None:
    """Print a summary of detected executable files."""
    print(f"  Contains executable code ({len(executables)} file(s)):")
    for e in executables[:max_display]:
        print(f"    {e}")
    if len(executables) > max_display:
        print(f"    ... and {len(executables) - max_display} more")


def import_skill(args: argparse.Namespace) -> None:
    """Import a raw skill from an upstream repo, wrapping it as a plugin."""
    if not all([args.repo, args.path]):
        print("Error: --import-skill requires --repo and --path", file=sys.stderr)
        sys.exit(1)

    dry_run = args.dry_run

    data = load_sources()
    if args.name in data["plugins"]:
        print(f"Error: Plugin '{args.name}' already tracked", file=sys.stderr)
        sys.exit(1)

    if dry_run:
        print(f"[dry-run] Validating '{args.name}' from {args.repo} @ {args.ref}\n")

    head = get_upstream_head(args.repo, args.ref)
    with _extract_upstream(args.repo, head, args.path) as source_dir:
        frontmatter = _resolve_frontmatter(source_dir, args.path, args.name, force=args.force)
        print(f"  Frontmatter: OK (name={frontmatter.get('name')!r})")

        deps = detect_dependencies(source_dir)
        if deps:
            print("  Dependencies detected (may need installation):")
            for d in deps:
                print(f"    {d}")

        executables = detect_executable_code(source_dir)
        if executables:
            _print_executable_summary(executables, max_display=MAX_DISPLAY_EXECUTABLES)
        else:
            print("  Executable code: none detected")

        # Scan — in dry-run mode always scan and report without blocking
        _gate_scan(source_dir, args.name, skip_scan=args.skip_scan, dry_run=dry_run)

        if dry_run:
            _print_dry_run_summary(
                sources_entry={
                    "upstream_repo": args.repo,
                    "upstream_path": args.path,
                    "upstream_ref": args.ref,
                    "upstream_type": UPSTREAM_TYPE_RAW_SKILL,
                    "last_synced_commit": head,
                    "has_executable_code": bool(executables),
                    "verified": False,
                },
                marketplace_entry={
                    "name": args.name,
                    "version": frontmatter.get("version", "0.1.0"),
                    "description": frontmatter.get("description", ""),
                    "source": f"./plugins/{args.name}",
                },
            )
            print(f"\n[dry-run] '{args.name}' validation complete. No files were modified.")
            return

        # Build plugin structure and register
        _build_plugin_structure(args.name, source_dir, frontmatter)

    description = frontmatter.get("description", "")
    version = frontmatter.get("version", "0.1.0")
    now = datetime.now(UTC).isoformat()
    data["plugins"][args.name] = {
        "upstream_repo": args.repo,
        "upstream_path": args.path,
        "upstream_ref": args.ref,
        "upstream_type": UPSTREAM_TYPE_RAW_SKILL,
        "last_synced_commit": head,
        "last_checked": now,
        "local_modifications": False,
        "has_executable_code": bool(executables),
        "verified": False,
    }
    save_sources(data)

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
        _print_executable_summary(executables, max_display=MAX_DISPLAY_EXECUTABLES)
    print("  Verified: no (use --mark-verified to approve after review)")


# --- Add plugin (existing, updated with new fields) ---


def _read_plugin_metadata(source_dir: Path, name: str) -> dict:
    """Read plugin.json from an extracted plugin directory.

    Returns dict with name, version, description. Falls back to defaults.
    """
    plugin_json_path = source_dir / ".claude-plugin" / "plugin.json"
    if plugin_json_path.exists():
        try:
            meta = json.loads(plugin_json_path.read_text())
            return {
                "name": meta.get("name", name),
                "version": meta.get("version", "0.1.0"),
                "description": meta.get("description", ""),
            }
        except json.JSONDecodeError:
            print("  Warning: malformed plugin.json, using defaults")

    return {"name": name, "version": "0.1.0", "description": f"Plugin: {name}"}


def add_plugin(args: argparse.Namespace) -> None:
    """Fetch an upstream plugin, scan it, and add it to the marketplace."""
    if not all([args.repo, args.path]):
        print("Error: --add requires --repo and --path", file=sys.stderr)
        sys.exit(1)

    dry_run = args.dry_run

    data = load_sources()
    if args.name in data["plugins"]:
        print(f"Error: Plugin '{args.name}' already tracked", file=sys.stderr)
        sys.exit(1)

    plugin_dir = REPO_ROOT / "plugins" / args.name
    if plugin_dir.exists() and not dry_run:
        print(f"Error: Directory plugins/{args.name} already exists", file=sys.stderr)
        sys.exit(1)

    if dry_run:
        print(f"[dry-run] Validating '{args.name}' from {args.repo} @ {args.ref}\n")

    head = get_upstream_head(args.repo, args.ref)
    print(f"  Upstream HEAD: {head[:12]}")

    with _extract_upstream(args.repo, head, args.path) as source_dir:
        metadata = _read_plugin_metadata(source_dir, args.name)
        print(f"  Plugin: {metadata['name']} v{metadata['version']}")
        if metadata["description"]:
            print(f"  Description: {metadata['description']}")

        # Check for executable code
        executables = detect_executable_code(source_dir)
        if executables:
            _print_executable_summary(executables, max_display=MAX_DISPLAY_EXECUTABLES)
        else:
            print("  Executable code: none detected")

        # Scan
        _gate_scan(source_dir, args.name, skip_scan=args.skip_scan, dry_run=dry_run)

        if dry_run:
            _print_dry_run_summary(
                sources_entry={
                    "upstream_repo": args.repo,
                    "upstream_path": args.path,
                    "upstream_ref": args.ref,
                    "upstream_type": UPSTREAM_TYPE_PLUGIN,
                    "last_synced_commit": head,
                    "has_executable_code": bool(executables),
                    "verified": False,
                },
                marketplace_entry={
                    "name": args.name,
                    "version": metadata["version"],
                    "description": metadata["description"],
                    "source": f"./plugins/{args.name}",
                },
            )
            print(f"\n[dry-run] '{args.name}' validation complete. No files were modified.")
            return

        # Copy plugin into plugins/
        shutil.copytree(source_dir, plugin_dir)

    # Register in sources.json
    now = datetime.now(UTC).isoformat()
    data["plugins"][args.name] = {
        "upstream_repo": args.repo,
        "upstream_path": args.path,
        "upstream_ref": args.ref,
        "upstream_type": UPSTREAM_TYPE_PLUGIN,
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
            "version": metadata["version"],
            "description": metadata["description"],
            "source": f"./plugins/{args.name}",
        }
    )
    save_marketplace(marketplace)

    print(f"Added '{args.name}' from {args.repo} @ {args.ref} ({head[:12]})")
    if executables:
        _print_executable_summary(executables, max_display=MAX_DISPLAY_EXECUTABLES)
    print("  Verified: no (use --mark-verified to approve after review)")


# --- Diff and check ---


def get_local_diff(plugin_name: str, info: dict) -> str | None:
    """Diff local plugin directory against upstream at last_synced_commit.

    For raw-skill imports, compares only the skills/<name>/ subtree against upstream.
    For plugin imports, compares the full plugin directory.
    """
    upstream_type = info.get("upstream_type", UPSTREAM_TYPE_PLUGIN)

    upstream_path = info["upstream_path"]
    commit = info["last_synced_commit"]
    with (
        clone_upstream_bare(info["upstream_repo"]) as bare_dir,
        tempfile.TemporaryDirectory() as extractdir,
    ):
        result = subprocess.run(
            ["git", "archive", commit, "--", upstream_path],
            check=False,
            capture_output=True,
            cwd=bare_dir,
        )
        if result.returncode != 0:
            return "  Error: Could not extract upstream at synced commit."
        subprocess.run(
            ["tar", "xf", "-"],
            check=False,
            input=result.stdout,
            capture_output=True,
            cwd=extractdir,
        )

        upstream_dir = str(Path(extractdir) / upstream_path)

        if upstream_type == UPSTREAM_TYPE_RAW_SKILL:
            local_dir = str(REPO_ROOT / "plugins" / plugin_name / "skills" / plugin_name)
        else:
            local_dir = str(REPO_ROOT / "plugins" / plugin_name)

        result = subprocess.run(
            ["diff", "-ruN", upstream_dir, local_dir],
            check=False,
            capture_output=True,
            text=True,
        )
        return result.stdout or None


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
        check=False,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    uncommitted = result.stdout.strip()
    # Compare actual content against upstream at synced commit
    diff_output = get_local_diff(plugin_name, info)
    modified = bool(uncommitted) or diff_output is not None
    return modified, diff_output


def get_upstream_diff(repo_url: str, path: str, old_commit: str, new_commit: str) -> list[str]:
    """Fetch upstream and diff between old and new commits for the plugin path."""
    changed_files = []
    with clone_upstream_bare(repo_url) as tmpdir:
        result = subprocess.run(
            ["git", "diff", "--name-only", old_commit, new_commit, "--", path],
            check=False,
            capture_output=True,
            text=True,
            cwd=tmpdir,
        )
        if result.returncode == 0:
            changed_files = [f for f in result.stdout.strip().splitlines() if f]
    return changed_files


def determine_status(*, upstream_changed: bool, local_modified: bool) -> str:
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


def check_single_plugin(name: str, info: dict, *, show_diff: bool = False) -> dict:
    """Check a single plugin against its upstream. Returns status dict."""
    upstream_type = info.get("upstream_type", UPSTREAM_TYPE_PLUGIN)
    print(f"\n{name}:")
    print(f"  Upstream: {info['upstream_repo']} @ {info['upstream_ref']}")
    if upstream_type == UPSTREAM_TYPE_RAW_SKILL:
        print("  Type: raw-skill (wrapped)")

    current_head = get_upstream_head(info["upstream_repo"], info["upstream_ref"])
    synced = info["last_synced_commit"]
    upstream_changed = current_head != synced

    print(f"  Last synced: {synced[:12]}")
    if upstream_changed:
        print(f"  Current upstream: {current_head[:12]}")

    local_modified, local_diff = has_local_modifications(name, info)
    print(f"  Local modifications: {'yes' if local_modified else 'no'}")

    status = determine_status(upstream_changed=upstream_changed, local_modified=local_modified)
    print(f"  Status: {status}")
    print(f"  Action: {status_action(status)}")

    if info.get("has_executable_code"):
        verified = info.get("verified", False)
        print(f"  Executable code: yes (verified: {'yes' if verified else 'no'})")

    if upstream_changed:
        changed = get_upstream_diff(
            info["upstream_repo"],
            info["upstream_path"],
            synced,
            current_head,
        )
        if changed:
            print("  Files changed upstream:")
            for f in changed:
                print(f"    M {f}")

    if show_diff and local_diff:
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
    now = datetime.now(UTC).isoformat()
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
    now = datetime.now(UTC).isoformat()

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


def list_pending(_args: argparse.Namespace) -> None:
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
        upstream_type = info.get("upstream_type", UPSTREAM_TYPE_PLUGIN)
        repo = info["upstream_repo"]
        short_repo = repo.replace("https://github.com/", "").replace(".git", "")

        print(f"  {name}")
        print(f"    Source: {short_repo}")
        print(f"    Type: {upstream_type}")
        if executables:
            print(f"    !! Contains executable code ({len(executables)} file(s)):")
            for e in executables[:MAX_DISPLAY_PENDING]:
                print(f"       {e}")
            if len(executables) > MAX_DISPLAY_PENDING:
                print(f"       ... and {len(executables) - MAX_DISPLAY_PENDING} more")
        else:
            print("    Executable code: none detected")
        print()


# --- Scan ---


def _find_semgrep() -> str:
    """Locate semgrep binary. Exits if not found."""
    path = shutil.which("semgrep")
    if path:
        return path
    print(
        "Error: semgrep not found. Install with: uv tool install semgrep",
        file=sys.stderr,
    )
    sys.exit(1)


def _run_semgrep(target: Path, semgrep_bin: str) -> tuple[int, str]:
    """Run semgrep with configured rulesets against a target directory.

    Returns (finding_count, output_text).
    """
    base_cmd = [semgrep_bin, "scan", "--no-git-ignore"]
    config_args = []
    for config in SEMGREP_CONFIGS:
        config_args.extend(["--config", config])

    # Text run for human-readable output
    text_result = subprocess.run(
        [*base_cmd, *config_args, "--quiet", str(target)],
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    output = text_result.stdout.strip()

    # Always run JSON to get accurate finding count — exit code alone is
    # unreliable (semgrep returns 0 for WARNINGs even when findings exist).
    finding_count = 0
    json_result = subprocess.run(
        [*base_cmd, *config_args, "--json", "--quiet", str(target)],
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    if json_result.stdout.strip():
        try:
            findings = json.loads(json_result.stdout)
            finding_count = len(findings.get("results", []))
        except json.JSONDecodeError:
            # Fallback: if text run showed output, assume at least 1 finding
            if output:
                finding_count = 1

    return finding_count, output


def _gate_scan(target: Path, name: str, *, skip_scan: bool = False, dry_run: bool = False) -> None:
    """Run semgrep on a directory and abort if findings are detected.

    In dry-run mode, reports findings without blocking.
    Skips the scan if semgrep is not installed or --skip-scan was passed.
    """
    if skip_scan and not dry_run:
        print(f"  Skipping semgrep scan for '{name}' (--skip-scan)")
        return

    semgrep_path = shutil.which("semgrep")
    if not semgrep_path:
        print("  Warning: semgrep not installed, skipping scan")
        print("  Install with: uv tool install semgrep")
        return

    print(f"  Scanning '{name}' with semgrep...")
    finding_count, output = _run_semgrep(target, semgrep_path)

    # Check allowed-tools policy
    tool_warnings = check_allowed_tools_policy(target)
    if tool_warnings:
        print(f"\n  Allowed-tools policy warnings for '{name}':")
        for w in tool_warnings:
            print(w)
        finding_count += len(tool_warnings)

    if finding_count > 0:
        print(output)
        print(f"\n  Scan found {finding_count} finding(s) in '{name}'.")
        if dry_run:
            print("  [dry-run] Findings reported above. Review before importing.")
        else:
            print("  Use --skip-scan to import anyway.")
            sys.exit(1)
    else:
        print("  Scan clean — no findings.")


def _scan_single_plugin(
    plugin_dir: Path,
    semgrep_bin: str,
) -> int:
    """Run semgrep and allowed-tools policy on a single plugin directory.

    Returns the total finding count.
    """
    finding_count, output = _run_semgrep(plugin_dir, semgrep_bin)

    tool_warnings = check_allowed_tools_policy(plugin_dir)
    if tool_warnings:
        print("  Allowed-tools policy warnings:")
        for w in tool_warnings:
            print(w)
        finding_count += len(tool_warnings)

    if output:
        print(output)
    elif not tool_warnings:
        print("  No findings.")
    print()
    return finding_count


def scan_plugins(args: argparse.Namespace) -> None:
    """Run semgrep security scan on unverified plugins (or a specific plugin)."""
    semgrep_bin = _find_semgrep()
    data = load_sources()
    plugins = data["plugins"]

    if args.plugin:
        if args.plugin not in plugins:
            print(f"Error: Plugin '{args.plugin}' not tracked", file=sys.stderr)
            sys.exit(1)
        targets = {args.plugin: plugins[args.plugin]}
    else:
        targets = {name: info for name, info in plugins.items() if not info.get("verified", False)}

    if not targets:
        print("No unverified plugins to scan.")
        return

    print(f"Scanning {len(targets)} plugin(s) with semgrep...")
    print(f"  Rulesets: {', '.join(SEMGREP_CONFIGS)}\n")

    total_findings = 0
    for name, info in targets.items():
        plugin_dir = REPO_ROOT / "plugins" / name
        if not plugin_dir.exists():
            print(f"{name}: SKIP (directory not found)")
            continue

        print(f"{name}:")
        upstream_type = info.get("upstream_type", UPSTREAM_TYPE_PLUGIN)
        print(f"  Type: {upstream_type}")
        print(f"  Verified: {'yes' if info.get('verified', False) else 'no'}")
        print(f"  Scanning {plugin_dir}...")

        total_findings += _scan_single_plugin(plugin_dir, semgrep_bin)

    print(f"Scan complete. Total findings across {len(targets)} plugin(s): {total_findings}")
    if total_findings > 0:
        print("Review findings before marking plugins as verified.")


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
    group.add_argument(
        "--scan",
        action="store_true",
        help="Run semgrep security scan on unverified plugins",
    )

    parser.add_argument("--name", help="Plugin name (default: last component of --path)")
    parser.add_argument("--repo", help="Upstream git repo URL (for --add/--import-skill)")
    parser.add_argument("--path", help="Path within upstream repo (for --add/--import-skill)")
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
    parser.add_argument(
        "--skip-scan",
        action="store_true",
        help="Skip semgrep scan during --add/--import-skill (import despite findings)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and scan without modifying any files (for --add/--import-skill)",
    )
    args = parser.parse_args()

    # Infer --name from --path if not provided
    if not args.name and args.path:
        args.name = Path(args.path).name

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
    elif args.scan:
        scan_plugins(args)
    else:
        check_plugins(args)


if __name__ == "__main__":
    main()
