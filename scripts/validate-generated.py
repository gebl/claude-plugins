# /// script
# requires-python = ">=3.12"
# ///
"""Validate that generated marketplace artifacts are up-to-date with the neutral catalog."""

import argparse
import contextlib
import importlib.util
import io
import json
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"


def _import_from_file(name: str, filepath: Path):
    """Import a Python module from a file path (supports hyphenated filenames)."""
    spec = importlib.util.spec_from_file_location(name, filepath)
    if spec is None or spec.loader is None:
        print(f"Error: cannot load {filepath}", file=sys.stderr)
        sys.exit(1)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gen_marketplace = _import_from_file("gen_marketplace", SCRIPTS_DIR / "generate-marketplace.py")
gen_codex = _import_from_file("gen_codex", SCRIPTS_DIR / "generate-codex.py")


def collect_tree(directory: Path) -> dict[str, bytes]:
    """Recursively collect all files under a directory, keyed by relative path."""
    results = {}
    if not directory.exists():
        return results
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        rel = str(path.relative_to(directory))
        results[rel] = path.read_bytes()
    return results


def compare_trees(expected_dir: Path, actual_dir: Path, label: str) -> list[str]:
    """Compare two directory trees. Return list of stale display paths."""
    expected = collect_tree(expected_dir)
    actual = collect_tree(actual_dir)
    stale = []

    all_keys = sorted(set(expected) | set(actual))
    for key in all_keys:
        display = f"{label}/{key}"
        if key not in actual:
            print(f"  Checking {display}... MISSING")
            stale.append(display)
        elif key not in expected:
            print(f"  Checking {display}... EXTRA")
            stale.append(display)
        elif expected[key] != actual[key]:
            print(f"  Checking {display}... STALE")
            stale.append(display)
        else:
            print(f"  Checking {display}... OK")

    return stale


def generate_to_temp(tmp: Path) -> None:
    """Run both generators, writing output to a temp directory tree."""
    packages = gen_marketplace.load_catalog()

    # Temporarily override output directories
    orig_claude_dir = gen_marketplace.GENERATED_DIR
    gen_marketplace.GENERATED_DIR = tmp / "generated"

    orig_codex_dir = gen_codex.GENERATED_DIR
    gen_codex.GENERATED_DIR = tmp / "generated" / "codex"

    try:
        with contextlib.redirect_stdout(io.StringIO()):
            gen_marketplace.generate_claude(packages)
            gen_codex.generate_codex(packages)
    finally:
        gen_marketplace.GENERATED_DIR = orig_claude_dir
        gen_codex.GENERATED_DIR = orig_codex_dir


def validate(*, fix: bool = False) -> int:
    """Validate generated artifacts. Returns 0 if all match, 1 if any diverge."""
    if fix:
        return run_fix()

    tmp_dir = Path(tempfile.mkdtemp(prefix="validate-generated-"))
    try:
        generate_to_temp(tmp_dir)
        stale: list[str] = []

        # Compare generated/claude/
        stale.extend(
            compare_trees(
                tmp_dir / "generated" / "claude",
                REPO_ROOT / "generated" / "claude",
                "generated/claude",
            )
        )

        # Compare generated/codex/
        stale.extend(
            compare_trees(
                tmp_dir / "generated" / "codex",
                REPO_ROOT / "generated" / "codex",
                "generated/codex",
            )
        )

        # Compare .claude-plugin/marketplace.json against generated/claude/marketplace.json
        claude_plugin_path = REPO_ROOT / ".claude-plugin" / "marketplace.json"
        generated_claude_path = REPO_ROOT / "generated" / "claude" / "marketplace.json"
        display = ".claude-plugin/marketplace.json"

        if not claude_plugin_path.exists():
            print(f"  Checking {display}... MISSING")
            stale.append(display)
        elif not generated_claude_path.exists():
            print(f"  Checking {display}... SKIP (no generated/claude/marketplace.json)")
        else:
            with claude_plugin_path.open() as f:
                cp_data = json.load(f)
            with generated_claude_path.open() as f:
                gc_data = json.load(f)
            if cp_data != gc_data:
                print(f"  Checking {display}... STALE")
                stale.append(display)
            else:
                print(f"  Checking {display}... OK")

        print()
        if stale:
            print(f"{len(stale)} file(s) out of sync. Run with --fix to regenerate.")
            return 1

        print("All generated artifacts are up-to-date.")
        return 0
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def run_fix() -> int:
    """Regenerate all artifacts in-place and sync .claude-plugin/."""
    packages = gen_marketplace.load_catalog()

    with contextlib.redirect_stdout(io.StringIO()):
        gen_marketplace.generate_claude(packages)
        gen_codex.generate_codex(packages)

    # Copy generated/claude/marketplace.json -> .claude-plugin/marketplace.json
    src = REPO_ROOT / "generated" / "claude" / "marketplace.json"
    dst = REPO_ROOT / ".claude-plugin" / "marketplace.json"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)

    print("Regenerated all marketplace artifacts.")
    print("  generated/claude/marketplace.json")
    print("  generated/codex/marketplace.json")
    print("  generated/codex/plugins/*/")
    print("  .claude-plugin/marketplace.json (copied from generated/claude/)")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate that generated marketplace artifacts match the neutral catalog."
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Regenerate artifacts in-place instead of just checking.",
    )
    args = parser.parse_args()
    sys.exit(validate(fix=args.fix))


if __name__ == "__main__":
    main()
