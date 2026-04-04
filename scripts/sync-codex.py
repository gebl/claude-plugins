# /// script
# requires-python = ">=3.12"
# ///
"""Sync generated Codex marketplace artifacts into the repo-local .agents/plugins tree."""

import argparse
import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GENERATED_DIR = REPO_ROOT / "generated" / "codex"
GENERATED_MARKETPLACE = GENERATED_DIR / "marketplace.json"
GENERATED_PLUGINS_DIR = GENERATED_DIR / "plugins"
CODEX_DIR = REPO_ROOT / ".agents" / "plugins"
CODEX_MARKETPLACE = CODEX_DIR / "marketplace.json"
CODEX_PLUGINS_DIR = CODEX_DIR / "plugins"


def load_marketplace(path: Path) -> dict:
    with path.open() as f:
        return json.load(f)


def ensure_generated_exists() -> None:
    if not GENERATED_MARKETPLACE.is_file():
        print(
            "Error: generated Codex marketplace is missing. Run "
            "`uv run scripts/generate-codex.py` first.",
            file=sys.stderr,
        )
        sys.exit(1)


def copy_plugin_dir(name: str) -> None:
    src = GENERATED_PLUGINS_DIR / name
    dst = CODEX_PLUGINS_DIR / name
    if not src.is_dir():
        print(f"Error: generated plugin directory missing for '{name}': {src}", file=sys.stderr)
        sys.exit(1)
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def remove_stale_plugins(expected_names: set[str]) -> list[str]:
    removed: list[str] = []
    if not CODEX_PLUGINS_DIR.is_dir():
        return removed

    for child in sorted(CODEX_PLUGINS_DIR.iterdir()):
        if not child.is_dir():
            continue
        if child.name not in expected_names:
            shutil.rmtree(child)
            removed.append(child.name)
    return removed


def sync(*, clean: bool) -> int:
    ensure_generated_exists()
    marketplace = load_marketplace(GENERATED_MARKETPLACE)
    plugins = marketplace.get("plugins", [])
    plugin_names = {plugin["name"] for plugin in plugins}

    CODEX_DIR.mkdir(parents=True, exist_ok=True)
    CODEX_PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(GENERATED_MARKETPLACE, CODEX_MARKETPLACE)

    for name in sorted(plugin_names):
        copy_plugin_dir(name)

    removed: list[str] = []
    if clean:
        removed = remove_stale_plugins(plugin_names)

    print(f"Synced {CODEX_MARKETPLACE}")
    print(f"  Installed plugins: {len(plugin_names)}")
    print(f"  Plugin root: {CODEX_PLUGINS_DIR}")
    if clean:
        print(f"  Removed stale plugins: {len(removed)}")
        for name in removed:
            print(f"    - {name}")
    else:
        print("  Stale plugins: preserved (use --clean to remove)")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync generated Codex marketplace artifacts into .agents/plugins for local testing."
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove plugin directories in .agents/plugins/plugins that are not in the generated marketplace.",
    )
    args = parser.parse_args()
    sys.exit(sync(clean=args.clean))


if __name__ == "__main__":
    main()
