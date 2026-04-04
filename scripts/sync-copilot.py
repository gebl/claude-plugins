# /// script
# requires-python = ">=3.12"
# ///
"""Sync generated Copilot skills into a Copilot-discoverable install tree."""

import argparse
import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GENERATED_SKILLS_DIR = REPO_ROOT / "generated" / "copilot" / "skills"
PROJECT_SKILLS_DIR = REPO_ROOT / ".github" / "skills"
LEGACY_PROJECT_SKILLS_DIR = REPO_ROOT / ".claude" / "skills"
USER_SKILLS_DIR = Path.home() / ".copilot" / "skills"
MANIFEST_FILENAME = ".anvil-managed.json"


def ensure_generated_exists() -> None:
    if not GENERATED_SKILLS_DIR.is_dir():
        print(
            "Error: generated Copilot skills are missing. Run "
            "`uv run scripts/generate-copilot.py` first.",
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
    except Exception:
        return set()
    names = data.get("skills", [])
    return {name for name in names if isinstance(name, str)}


def write_managed_skills(target_dir: Path, names: set[str]) -> None:
    path = manifest_path(target_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"skills": sorted(names)}, indent=2) + "\n")


def remove_stale_skills(target_dir: Path, expected_names: set[str], managed_names: set[str]) -> list[str]:
    removed: list[str] = []
    if not target_dir.is_dir():
        return removed

    for name in sorted(managed_names - expected_names):
        child = target_dir / name
        if child.is_dir():
            shutil.rmtree(child)
            removed.append(name)
    return removed


def cleanup_legacy_project_install(expected_names: set[str]) -> list[str]:
    """Remove previously Anvil-managed skills from the old .claude/skills project path."""
    removed: list[str] = []
    managed_names = load_managed_skills(LEGACY_PROJECT_SKILLS_DIR)
    if not managed_names:
        return removed
    for name in sorted(managed_names & expected_names):
        child = LEGACY_PROJECT_SKILLS_DIR / name
        if child.is_dir():
            shutil.rmtree(child)
            removed.append(name)
    # Remove any stale legacy-managed skills too.
    removed.extend(remove_stale_skills(LEGACY_PROJECT_SKILLS_DIR, set(), managed_names - set(removed)))
    legacy_manifest = manifest_path(LEGACY_PROJECT_SKILLS_DIR)
    if legacy_manifest.exists():
        legacy_manifest.unlink()
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
    migrated: list[str] = []
    if not user:
        migrated = cleanup_legacy_project_install(skill_names)

    print(f"Synced {target_dir}")
    print(f"  Installed skills: {len(skill_names)}")
    if clean:
        print(f"  Removed stale skills: {len(removed)}")
        for name in removed:
            print(f"    - {name}")
    else:
        print("  Stale skills: preserved (use --clean to remove)")
    if migrated:
        print(f"  Removed legacy .claude/skills installs: {len(migrated)}")
        for name in migrated:
            print(f"    - {name}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync generated Copilot skill outputs into .github/skills by default, or ~/.copilot/skills with --user.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove installed skills not present in generated/copilot/skills.",
    )
    parser.add_argument(
        "--user",
        action="store_true",
        help="Install into ~/.copilot/skills instead of the repo-local .github/skills path.",
    )
    args = parser.parse_args()
    sys.exit(sync(clean=args.clean, user=args.user))


if __name__ == "__main__":
    main()
