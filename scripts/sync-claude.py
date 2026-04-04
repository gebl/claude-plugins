# /// script
# requires-python = ">=3.12"
# ///
"""Sync generated Claude skills into a Claude-discoverable install tree.

Reads from generated/claude/skills/ and writes to .claude/skills/ (project)
or ~/.claude/skills/ (user-global with --user).
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GENERATED_SKILLS_DIR = REPO_ROOT / "generated" / "claude" / "skills"
PROJECT_SKILLS_DIR = REPO_ROOT / ".claude" / "skills"
USER_SKILLS_DIR = Path.home() / ".claude" / "skills"
MANIFEST_FILENAME = ".anvil-managed.json"


def ensure_generated_exists() -> None:
    if not GENERATED_SKILLS_DIR.is_dir():
        print(
            "Error: generated Claude skills are missing. Run "
            "`uv run scripts/generate-claude.py` first.",
            file=sys.stderr,
        )
        sys.exit(1)


def copy_skill_dir(name: str, target_dir: Path) -> None:
    src = GENERATED_SKILLS_DIR / name
    dst = target_dir / name
    if not src.is_dir():
        print(f"Error: generated skill directory missing for '{name}': {src}", file=sys.stderr)
        sys.exit(1)
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def manifest_path(target_dir: Path) -> Path:
    return target_dir / MANIFEST_FILENAME


def load_managed_skills(target_dir: Path) -> set[str]:
    path = manifest_path(target_dir)
    if not path.is_file():
        return set()
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return set()
    names = data.get("skills", [])
    return {name for name in names if isinstance(name, str)}


def write_managed_skills(target_dir: Path, names: set[str]) -> None:
    path = manifest_path(target_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"skills": sorted(names)}, indent=2) + "\n")


def remove_stale_skills(
    target_dir: Path, expected_names: set[str], managed_names: set[str],
) -> list[str]:
    removed: list[str] = []
    if not target_dir.is_dir():
        return removed
    for name in sorted(managed_names - expected_names):
        child = target_dir / name
        if child.is_dir():
            shutil.rmtree(child)
            removed.append(name)
    return removed


def sync(*, clean: bool, user: bool) -> int:
    ensure_generated_exists()
    skill_names = {path.name for path in GENERATED_SKILLS_DIR.iterdir() if path.is_dir()}
    target_dir = USER_SKILLS_DIR if user else PROJECT_SKILLS_DIR
    managed_names = load_managed_skills(target_dir)

    target_dir.mkdir(parents=True, exist_ok=True)

    for name in sorted(skill_names):
        copy_skill_dir(name, target_dir)

    removed: list[str] = []
    if clean:
        removed = remove_stale_skills(target_dir, skill_names, managed_names)

    write_managed_skills(target_dir, skill_names)

    print(f"Synced {target_dir}")
    print(f"  Installed skills: {len(skill_names)}")
    if clean:
        print(f"  Removed stale skills: {len(removed)}")
        for name in removed:
            print(f"    - {name}")
    else:
        print("  Stale skills: preserved (use --clean to remove)")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Sync generated Claude skill outputs into .claude/skills/ by default, "
            "or ~/.claude/skills/ with --user."
        ),
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove installed skills not present in generated/claude/skills.",
    )
    parser.add_argument(
        "--user",
        action="store_true",
        help="Install into ~/.claude/skills instead of the repo-local .claude/skills path.",
    )
    args = parser.parse_args()
    sys.exit(sync(clean=args.clean, user=args.user))


if __name__ == "__main__":
    main()
