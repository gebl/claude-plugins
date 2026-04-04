# /// script
# requires-python = ">=3.12"
# ///
"""Sync generated Copilot skills into the repo-local .agents/skills tree."""

import argparse
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GENERATED_SKILLS_DIR = REPO_ROOT / "generated" / "copilot" / "skills"
COPILOT_SKILLS_DIR = REPO_ROOT / ".agents" / "skills"


def ensure_generated_exists() -> None:
    if not GENERATED_SKILLS_DIR.is_dir():
        print(
            "Error: generated Copilot skills are missing. Run "
            "`uv run scripts/generate-copilot.py` first.",
            file=sys.stderr,
        )
        sys.exit(1)


def copy_skill_dir(name: str) -> None:
    src = GENERATED_SKILLS_DIR / name
    dst = COPILOT_SKILLS_DIR / name
    if not src.is_dir():
        print(f"Error: generated skill directory missing for '{name}': {src}", file=sys.stderr)
        sys.exit(1)
    # Copy in place so updates do not depend on deleting the destination first.
    # This is safer for repeated syncs and avoids partial installs if deletion succeeds
    # but the subsequent copy is interrupted.
    shutil.copytree(src, dst, dirs_exist_ok=True)


def remove_stale_skills(expected_names: set[str]) -> list[str]:
    removed: list[str] = []
    if not COPILOT_SKILLS_DIR.is_dir():
        return removed

    for child in sorted(COPILOT_SKILLS_DIR.iterdir()):
        if not child.is_dir():
            continue
        if child.name not in expected_names:
            shutil.rmtree(child)
            removed.append(child.name)
    return removed


def sync(*, clean: bool) -> int:
    ensure_generated_exists()
    skill_names = {path.name for path in GENERATED_SKILLS_DIR.iterdir() if path.is_dir()}

    COPILOT_SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    for name in sorted(skill_names):
        copy_skill_dir(name)

    removed: list[str] = []
    if clean:
        removed = remove_stale_skills(skill_names)

    print(f"Synced {COPILOT_SKILLS_DIR}")
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
        description="Sync generated Copilot skill outputs into .agents/skills for local testing.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove installed skills not present in generated/copilot/skills.",
    )
    args = parser.parse_args()
    sys.exit(sync(clean=args.clean))


if __name__ == "__main__":
    main()
