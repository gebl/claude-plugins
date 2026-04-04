# /// script
# requires-python = ">=3.12"
# ///
"""Generate Codex marketplace artifacts from the neutral catalog.

Reads neutral package records from catalog/packages/ and produces:
  - generated/codex/marketplace.json  (marketplace registry)
  - generated/codex/plugins/<name>/.codex-plugin/plugin.json  (per-plugin manifests)
  - generated/codex/plugins/<name>/skills/  (skill trees, transformed where needed)

Codex's plugin.json schema (from codex-rs/core/src/plugins/manifest.rs):
  - name: string (required)
  - description: string|null
  - skills: string|null  (relative path starting with './', e.g. "./skills")
  - interface.displayName: string|null
  - interface.shortDescription: string|null
  - interface.longDescription: string|null
  - interface.developerName: string|null
  - interface.category: string|null
  - interface.capabilities: [string]
"""

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from transforms import transform_plugin_for_codex

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG_DIR = REPO_ROOT / "catalog" / "packages"
PLUGINS_DIR = REPO_ROOT / "plugins"
GENERATED_DIR = REPO_ROOT / "generated" / "codex"

# Words that should stay uppercased in display names
UPPERCASE_WORDS = {"ai", "pr", "sql", "api", "yt", "ci", "cd", "tdd", "xss", "mcp"}

# Codex shortDescription max length
SHORT_DESC_MAX = 128

# Fallback developer names keyed by substring match against upstream repo URL
UPSTREAM_DEVELOPERS = {
    "trailofbits": "Trail of Bits",
    "garrytan": "Garry Tan",
    "mattpocock": "Matt Pocock",
    "conorbronsdon": "Conor Bronsdon",
    "ComposioHQ": "ComposioHQ",
}


def load_catalog() -> list[dict]:
    """Load all package records from the catalog."""
    packages = []
    for path in sorted(CATALOG_DIR.glob("*.json")):
        with path.open() as f:
            packages.append(json.load(f))
    return packages


def display_name(name: str) -> str:
    """Convert a kebab-case package name to a display name.

    Preserves known acronyms (AI, PR, YT, etc.) and capitalizes other words.
    """
    return " ".join(
        word.upper() if word.lower() in UPPERCASE_WORDS else word.capitalize()
        for word in name.split("-")
    )


def short_description(pkg: dict) -> str:
    """Extract a short description suitable for the Codex TUI subtitle.

    Uses the first sentence of the catalog description, capped at SHORT_DESC_MAX chars.
    """
    desc = pkg.get("description", "")
    for sep in [". ", ".\n", ".\t"]:
        if sep in desc:
            desc = desc[: desc.index(sep) + 1]
            break
    if len(desc) > SHORT_DESC_MAX:
        desc = desc[: SHORT_DESC_MAX - 3] + "..."
    return desc


def developer_name(pkg: dict) -> str | None:
    """Resolve developer name from the Claude plugin manifest or upstream metadata."""
    claude_manifest = PLUGINS_DIR / pkg["name"] / ".claude-plugin" / "plugin.json"
    if claude_manifest.is_file():
        data = json.loads(claude_manifest.read_text())
        author = data.get("author")
        if isinstance(author, dict) and author.get("name"):
            return author["name"]
        if isinstance(author, str) and author:
            return author

    repo = pkg.get("upstream", {}).get("repo", "")
    for substr, name in UPSTREAM_DEVELOPERS.items():
        if substr in repo:
            return name

    return None


def infer_capabilities(pkg: dict) -> list[str]:
    """Infer Codex capability tags from the package risk/file metadata."""
    caps = []
    tools = pkg.get("risk", {}).get("tool_risk", {}).get("declared_tools", [])

    write_tools = {"Edit", "Write"}
    if write_tools & set(tools):
        caps.append("Write")
    if "Bash" in tools:
        caps.append("Shell")
    if "Agent" in tools:
        caps.append("Subagent")
    if "AskUserQuestion" in tools:
        caps.append("Interactive")

    return caps


def copy_skills_tree(plugin_name: str, output_dir: Path) -> int:
    """Copy a plugin's raw skills tree into the generated Codex output."""
    src = PLUGINS_DIR / plugin_name / "skills"
    dst = output_dir / "skills"
    if not src.is_dir():
        return 0
    shutil.copytree(src, dst, dirs_exist_ok=True)
    return sum(1 for path in dst.rglob("*") if path.is_file())


def build_plugin_manifest(pkg: dict) -> dict:
    """Build a Codex .codex-plugin/plugin.json manifest from catalog metadata."""
    has_skill = pkg.get("files", {}).get("has_skill", False)
    mkt = pkg["generation"]["codex"]["marketplace"]

    dev = developer_name(pkg)
    caps = infer_capabilities(pkg)

    interface: dict = {
        "displayName": display_name(pkg["name"]),
        "shortDescription": short_description(pkg),
        "longDescription": pkg.get("description", ""),
        "category": mkt.get("category", "Developer Tools"),
    }
    if dev:
        interface["developerName"] = dev
    if caps:
        interface["capabilities"] = caps

    manifest: dict = {
        "name": pkg["name"],
        "description": pkg.get("description", ""),
    }
    if has_skill:
        manifest["skills"] = "./skills"
    manifest["interface"] = interface

    return manifest


def write_marketplace(included: list[dict], marketplace_path: Path) -> None:
    """Write the top-level marketplace.json."""
    plugins = []
    for pkg in included:
        mkt = pkg["generation"]["codex"]["marketplace"]
        plugins.append(
            {
                "name": pkg["name"],
                "source": {
                    "source": "local",
                    "path": f"./plugins/{pkg['name']}",
                },
                "policy": mkt["policy"],
                "category": mkt.get("category", "Developer Tools"),
            }
        )

    marketplace = {
        "name": "local-marketplace",
        "interface": {"displayName": "Local Plugin Marketplace"},
        "plugins": plugins,
    }

    marketplace_path.parent.mkdir(parents=True, exist_ok=True)
    with marketplace_path.open("w") as f:
        json.dump(marketplace, f, indent=2)
        f.write("\n")


def generate_plugin(pkg: dict) -> int:
    """Generate a single plugin's Codex artifacts. Returns count of transformed files."""
    has_skill = pkg.get("files", {}).get("has_skill", False)
    codex_mode = pkg.get("generation", {}).get("codex", {}).get("mode", "")

    manifest = build_plugin_manifest(pkg)
    plugin_out = GENERATED_DIR / "plugins" / pkg["name"]
    codex_manifest_dir = plugin_out / ".codex-plugin"
    codex_manifest_dir.mkdir(parents=True, exist_ok=True)

    with (codex_manifest_dir / "plugin.json").open("w") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")

    if has_skill and codex_mode != "adapted":
        copy_skills_tree(pkg["name"], plugin_out)

    if codex_mode == "adapted" and has_skill:
        return len(transform_plugin_for_codex(pkg["name"], plugin_out))

    return 0


def generate_codex(packages: list[dict]) -> None:
    """Generate Codex marketplace.json and per-plugin manifests."""
    included: list[dict] = []
    excluded: list[tuple[str, str]] = []

    for pkg in packages:
        codex_cfg = pkg.get("generation", {}).get("codex", {})
        if not codex_cfg.get("enabled", False):
            excluded.append((pkg["name"], "generation.codex.enabled is false"))
        elif "marketplace" not in codex_cfg:
            excluded.append((pkg["name"], "missing generation.codex.marketplace config"))
        else:
            included.append(pkg)

    included.sort(key=lambda p: p["name"])

    marketplace_path = GENERATED_DIR / "marketplace.json"
    write_marketplace(included, marketplace_path)

    transformed_counts: dict[str, int] = {}
    for pkg in included:
        tc = generate_plugin(pkg)
        if tc:
            transformed_counts[pkg["name"]] = tc

    # Summary
    print(f"Generated {marketplace_path}")
    print(f"  Included: {len(included)} plugins")
    print(f"  Excluded: {len(excluded)} plugins")
    print()

    print("Included plugins:")
    for pkg in included:
        mode = pkg.get("generation", {}).get("codex", {}).get("mode", "")
        tc = transformed_counts.get(pkg["name"], 0)
        suffix = f"  (adapted, {tc} files transformed)" if tc else ""
        print(f"  + {pkg['name']} [{mode}]{suffix}")

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
