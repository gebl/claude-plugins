# /// script
# requires-python = ">=3.12"
# ///
"""Generate harness-specific output artifacts from the neutral catalog."""

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG_DIR = REPO_ROOT / "catalog" / "packages"
GENERATED_DIR = REPO_ROOT / "generated"


def load_catalog() -> list[dict]:
    """Load all package records from the catalog."""
    packages = []
    for path in sorted(CATALOG_DIR.glob("*.json")):
        with path.open() as f:
            packages.append(json.load(f))
    return packages


def generate_claude(packages: list[dict]) -> None:
    """Generate Claude marketplace.json from catalog packages."""
    included = []
    excluded = []

    for pkg in packages:
        enabled = pkg.get("generation", {}).get("claude", {}).get("enabled", False)
        if not enabled:
            excluded.append(pkg["name"])
            continue
        included.append(pkg)

    # Sort alphabetically by name
    included.sort(key=lambda p: p["name"])

    # Build plugin entries
    plugins = []
    for pkg in included:
        entry: dict = {
            "name": pkg["name"],
            "version": pkg["version"],
            "description": pkg.get("description", ""),
        }

        # Author from first entry in authors list, if present
        authors = pkg.get("authors", [])
        if authors:
            author = {}
            for key in ("name", "email", "url"):
                if key in authors[0]:
                    author[key] = authors[0][key]
            if author:
                entry["author"] = author

        entry["source"] = f"./plugins/{pkg['name']}"
        plugins.append(entry)

    marketplace = {
        "$schema": "https://anthropic.com/claude-code/marketplace.schema.json",
        "name": "anvil",
        "owner": {"name": "Anvil"},
        "metadata": {
            "description": "Anvil's Claude Code plugin marketplace",
            "version": "1.0.0",
        },
        "plugins": plugins,
    }

    out_dir = GENERATED_DIR / "claude"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "marketplace.json"

    with out_path.open("w") as f:
        json.dump(marketplace, f, indent=2)
        f.write("\n")

    print(f"Generated {out_path}")
    print(f"  Included: {len(included)} plugins")
    if excluded:
        print(f"  Excluded: {len(excluded)} ({', '.join(excluded)})")
    else:
        print("  Excluded: 0")
    print()
    print("Included plugins:")
    for entry in plugins:
        print(f"  - {entry['name']} v{entry['version']}")


def generate_codex(_packages: list[dict]) -> None:
    """Stub for Codex marketplace generation — use generate-codex.py instead."""
    print("Codex generation not yet implemented — use generate-codex.py")


def generate_copilot(_packages: list[dict]) -> None:
    """Stub for Copilot skill generation — use generate-copilot.py instead."""
    print("Copilot generation not yet implemented here — use generate-copilot.py")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate harness-specific output artifacts from the neutral catalog."
    )
    parser.add_argument(
        "--harness",
        required=True,
        choices=["claude", "codex", "copilot"],
        help="Target harness to generate for",
    )
    args = parser.parse_args()

    if not CATALOG_DIR.is_dir():
        print(f"Error: catalog directory not found at {CATALOG_DIR}", file=sys.stderr)
        sys.exit(1)

    packages = load_catalog()
    if not packages:
        print("Error: no package records found in catalog", file=sys.stderr)
        sys.exit(1)

    if args.harness == "claude":
        generate_claude(packages)
    elif args.harness == "codex":
        generate_codex(packages)
    elif args.harness == "copilot":
        generate_copilot(packages)


if __name__ == "__main__":
    main()
