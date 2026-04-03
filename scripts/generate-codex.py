# /// script
# requires-python = ">=3.12"
# ///
"""Generate Codex marketplace artifacts from the neutral catalog."""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG_DIR = REPO_ROOT / "catalog" / "packages"
GENERATED_DIR = REPO_ROOT / "generated" / "codex"


def load_catalog() -> list[dict]:
    """Load all package records from the catalog."""
    packages = []
    for path in sorted(CATALOG_DIR.glob("*.json")):
        with path.open() as f:
            packages.append(json.load(f))
    return packages


def title_case_name(name: str) -> str:
    """Convert a kebab-case package name to a title-cased display name."""
    return " ".join(word.capitalize() for word in name.split("-"))


def generate_codex(packages: list[dict]) -> None:
    """Generate Codex marketplace.json and per-plugin manifests."""
    included: list[dict] = []
    excluded: list[tuple[str, str]] = []

    for pkg in packages:
        codex_cfg = pkg.get("generation", {}).get("codex", {})
        if not codex_cfg.get("enabled", False):
            excluded.append((pkg["name"], "generation.codex.enabled is false"))
            continue
        if "marketplace" not in codex_cfg:
            excluded.append((pkg["name"], "missing generation.codex.marketplace config"))
            continue
        included.append(pkg)

    included.sort(key=lambda p: p["name"])

    # Build marketplace plugin entries
    marketplace_plugins = []
    for pkg in included:
        mkt = pkg["generation"]["codex"]["marketplace"]
        marketplace_plugins.append(
            {
                "name": pkg["name"],
                "source": {
                    "source": "local",
                    "path": f"./plugins/{pkg['name']}",
                },
                "policy": mkt["policy"],
                "category": mkt["category"],
            }
        )

    marketplace = {
        "name": "local-marketplace",
        "interface": {
            "displayName": "Local Plugin Marketplace",
        },
        "plugins": marketplace_plugins,
    }

    # Write marketplace.json
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    marketplace_path = GENERATED_DIR / "marketplace.json"
    with marketplace_path.open("w") as f:
        json.dump(marketplace, f, indent=2)
        f.write("\n")

    # Generate per-plugin .codex-plugin/plugin.json manifests
    for pkg in included:
        has_skill = pkg.get("files", {}).get("has_skill", False)
        skills = ["./skills"] if has_skill else []

        manifest = {
            "name": pkg["name"],
            "version": pkg["version"],
            "description": pkg.get("description", ""),
            "skills": skills,
            "interface": {
                "displayName": title_case_name(pkg["name"]),
            },
        }

        plugin_dir = GENERATED_DIR / "plugins" / pkg["name"] / ".codex-plugin"
        plugin_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = plugin_dir / "plugin.json"
        with manifest_path.open("w") as f:
            json.dump(manifest, f, indent=2)
            f.write("\n")

    # Summary
    print(f"Generated {marketplace_path}")
    print(f"  Included: {len(included)} plugins")
    print(f"  Excluded: {len(excluded)} plugins")
    print()

    print("Included plugins:")
    for pkg in included:
        manifest_rel = f"generated/codex/plugins/{pkg['name']}/.codex-plugin/plugin.json"
        print(f"  + {pkg['name']} v{pkg['version']}  ({manifest_rel})")

    if excluded:
        print()
        print("Excluded plugins:")
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

    generate_codex(packages)


if __name__ == "__main__":
    main()
