# /// script
# requires-python = ">=3.12"
# ///
"""Generate GitHub Copilot CLI skill outputs from the neutral catalog.

Reads package records from catalog/packages/ and produces:
  - generated/copilot/skills/<name>/SKILL.md
  - generated/copilot/skills/<name>/...resource files...

This generator follows the GitHub Copilot CLI skill contract rather than the
Codex marketplace manifest model.
"""

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from transforms import transform_plugin_for_copilot

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG_DIR = REPO_ROOT / "catalog" / "packages"
PLUGINS_DIR = REPO_ROOT / "plugins"
GENERATED_DIR = REPO_ROOT / "generated" / "copilot"


def load_catalog() -> list[dict]:
    packages = []
    for path in sorted(CATALOG_DIR.glob("*.json")):
        with path.open() as f:
            packages.append(json.load(f))
    return packages


def copy_skill_tree(plugin_name: str, output_dir: Path) -> int:
    src = PLUGINS_DIR / plugin_name / "skills" / plugin_name
    dst = output_dir / plugin_name
    if not src.is_dir():
        return 0
    shutil.copytree(src, dst, dirs_exist_ok=True)
    return sum(1 for path in dst.rglob("*") if path.is_file())


def copy_extra_files(pkg: dict) -> int:
    extra_files = pkg.get("generation", {}).get("copilot", {}).get("extra_files", [])
    if not extra_files:
        return 0

    plugin_dir = PLUGINS_DIR / pkg["name"]
    skill_dir = GENERATED_DIR / "skills" / pkg["name"]
    copied = 0
    for rel in extra_files:
        src = plugin_dir / rel
        dst = skill_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied += 1
    return copied


def generate_skill(pkg: dict) -> int:
    copilot_mode = pkg.get("generation", {}).get("copilot", {}).get("mode", "")

    if copilot_mode == "adapted":
        transformed = len(transform_plugin_for_copilot(pkg["name"], GENERATED_DIR))
        return transformed + copy_extra_files(pkg)
    return copy_skill_tree(pkg["name"], GENERATED_DIR / "skills") + copy_extra_files(pkg)


def generate_copilot(packages: list[dict]) -> None:
    included: list[dict] = []
    excluded: list[tuple[str, str]] = []

    if GENERATED_DIR.exists():
        shutil.rmtree(GENERATED_DIR)

    for pkg in packages:
        copilot_cfg = pkg.get("generation", {}).get("copilot", {})
        if not copilot_cfg.get("enabled", False):
            excluded.append((pkg["name"], "generation.copilot.enabled is false"))
        else:
            included.append(pkg)

    included.sort(key=lambda p: p["name"])

    rendered_counts: dict[str, int] = {}
    for pkg in included:
        count = generate_skill(pkg)
        if count:
            rendered_counts[pkg["name"]] = count

    print(f"Generated {GENERATED_DIR}")
    print(f"  Included: {len(included)} skills")
    print(f"  Excluded: {len(excluded)} packages")
    print()

    print("Included skills:")
    for pkg in included:
        mode = pkg.get("generation", {}).get("copilot", {}).get("mode", "")
        count = rendered_counts.get(pkg["name"], 0)
        suffix = f"  ({count} files rendered)" if count else ""
        print(f"  + {pkg['name']} [{mode}]{suffix}")

    if excluded:
        print()
        print("Excluded packages:")
        for name, reason in excluded:
            print(f"  - {name}: {reason}")


def main() -> None:
    if not CATALOG_DIR.is_dir():
        print(f"Error: catalog directory not found at {CATALOG_DIR}", file=sys.stderr)
        sys.exit(1)

    packages = load_catalog()
    if not packages:
        print("Error: no package records found in catalog", file=sys.stderr)
        sys.exit(1)

    generate_copilot(packages)


if __name__ == "__main__":
    main()
