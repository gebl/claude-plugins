# /// script
# requires-python = ">=3.12"
# ///
"""Generate Claude skill outputs from the neutral catalog.

Reads package records from catalog/packages/ and produces:
  - generated/claude/skills/<name>/  (skill trees)
  - generated/claude/marketplace.json  (Claude marketplace registry)

For claude-native skills: passthrough copy from plugins-claude/.
For codex/copilot-native skills: transform to Claude format using transforms.py.
"""

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from transforms import transform_plugin_for_harness

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG_DIR = REPO_ROOT / "catalog" / "packages"
GENERATED_DIR = REPO_ROOT / "generated" / "claude"


def load_catalog() -> list[dict]:
    packages = []
    for path in sorted(CATALOG_DIR.glob("*.json")):
        with path.open() as f:
            packages.append(json.load(f))
    return packages


def copy_skill_tree(plugin_name: str, output_dir: Path, source_harness: str = "claude") -> int:
    """Copy a plugin's raw skill tree into the generated Claude output."""
    src = REPO_ROOT / f"plugins-{source_harness}" / plugin_name / "skills" / plugin_name
    dst = output_dir / plugin_name
    if not src.is_dir():
        return 0
    shutil.copytree(src, dst, dirs_exist_ok=True)
    return sum(1 for path in dst.rglob("*") if path.is_file())


def generate_skill(pkg: dict) -> tuple[int, str]:
    """Generate Claude artifacts for one package. Returns (file_count, mode_used)."""
    claude_cfg = pkg.get("generation", {}).get("claude", {})
    mode = claude_cfg.get("mode", "native")
    source_harness = pkg.get("canonical_harness", "claude")

    skills_out = GENERATED_DIR / "skills"

    if source_harness == "claude" or mode == "native":
        count = copy_skill_tree(pkg["name"], skills_out, source_harness)
        return count, "native"

    # Non-claude-native: adapt to claude format
    transformed = transform_plugin_for_harness(
        pkg["name"],
        GENERATED_DIR,
        target_harness="claude",
        source_harness=source_harness,
    )
    return len(transformed), "adapted"


def generate_marketplace(packages: list[dict]) -> dict:
    """Build a full claude marketplace.json from catalog packages with generation enabled."""
    plugins = []
    for pkg in sorted(packages, key=lambda p: p["name"]):
        if not pkg.get("generation", {}).get("claude", {}).get("enabled", False):
            continue
        source_harness = pkg.get("canonical_harness", "claude")
        entry: dict = {
            "name": pkg["name"],
            "version": pkg.get("version", "0.0.0"),
            "description": pkg.get("description", ""),
        }
        authors = pkg.get("authors", [])
        if authors:
            author: dict = {}
            for key in ("name", "email", "url"):
                if key in authors[0]:
                    author[key] = authors[0][key]
            if author:
                entry["author"] = author
        entry["source"] = f"./plugins-{source_harness}/{pkg['name']}"
        plugins.append(entry)

    return {
        "$schema": "https://anthropic.com/claude-code/marketplace.schema.json",
        "name": "anvil",
        "owner": {"name": "Anvil"},
        "metadata": {
            "description": "Anvil's Claude Code plugin marketplace",
            "version": "1.0.0",
        },
        "plugins": plugins,
    }


def generate_claude(packages: list[dict]) -> None:
    included: list[dict] = []
    excluded: list[tuple[str, str]] = []

    if GENERATED_DIR.exists():
        shutil.rmtree(GENERATED_DIR)

    for pkg in packages:
        claude_cfg = pkg.get("generation", {}).get("claude", {})
        if not claude_cfg.get("enabled", False):
            excluded.append((pkg["name"], "generation.claude.enabled is false"))
        else:
            included.append(pkg)

    included.sort(key=lambda p: p["name"])

    rendered_counts: dict[str, str] = {}
    file_counts: dict[str, int] = {}
    for pkg in included:
        count, mode = generate_skill(pkg)
        rendered_counts[pkg["name"]] = mode
        if count:
            file_counts[pkg["name"]] = count

    marketplace = generate_marketplace(included)
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    mp_path = GENERATED_DIR / "marketplace.json"
    mp_path.write_text(json.dumps(marketplace, indent=2) + "\n")

    print(f"Generated {GENERATED_DIR}")
    print(f"  Included: {len(included)} skills")
    print(f"  Excluded: {len(excluded)} packages")
    print()

    print("Included skills:")
    for pkg in included:
        mode = rendered_counts.get(pkg["name"], "")
        count = file_counts.get(pkg["name"], 0)
        suffix = f"  ({count} files)" if count else ""
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

    generate_claude(packages)


if __name__ == "__main__":
    main()
