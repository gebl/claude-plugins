# /// script
# requires-python = ">=3.12"
# ///
"""Assess package compatibility for the harness-agnostic catalog.

Usage:
    uv run scripts/assess-package.py --plugin review
    uv run scripts/assess-package.py --all
    uv run scripts/assess-package.py --all --summary
"""

import argparse
import sys
from pathlib import Path

# Allow importing assess.py from the same directory
sys.path.insert(0, str(Path(__file__).resolve().parent))

from assess import assess_package, list_all_packages, update_package_record


def print_assessment(name: str, result, *, verbose: bool = False) -> None:
    """Print a single package assessment."""
    compat = result.portability_class
    claude = result.status_by_harness.get("claude", "unknown")
    codex = result.status_by_harness.get("codex", "unknown")
    copilot = result.status_by_harness.get("copilot", "unknown")

    print(f"  {name}: {compat} (claude={claude}, codex={codex}, copilot={copilot})")

    if verbose:
        unsuppressed = [f for f in result.findings if not f.suppressed]
        suppressed = [f for f in result.findings if f.suppressed]

        if unsuppressed:
            for f in unsuppressed:
                marker = {"error": "!!", "warn": "!", "info": "-"}[f.severity]
                print(f"    {marker} [{f.code}] {f.message} ({f.path})")

        if suppressed:
            print(f"    ({len(suppressed)} finding(s) suppressed by external policy)")

        if result.adaptation_hints:
            print("    Hints:")
            for hint in result.adaptation_hints:
                print(f"      * {hint}")
        print()


def print_summary(results: dict) -> None:
    """Print classification summary table."""
    classes: dict[str, list[str]] = {}
    for name, result in results.items():
        c = result.portability_class
        classes.setdefault(c, []).append(name)

    print("\nClassification summary:")
    for cls in ["agnostic", "adaptable", "harness-specific", "unknown"]:
        names = classes.get(cls, [])
        if names:
            print(f"  {cls} ({len(names)}):")
            for n in sorted(names):
                print(f"    - {n}")

    total = len(results)
    codex_ready = sum(
        1 for r in results.values()
        if r.status_by_harness.get("codex") in ("generated", "adapted")
    )
    copilot_ready = sum(
        1 for r in results.values()
        if r.status_by_harness.get("copilot") in ("generated", "adapted")
    )
    print(
        f"\n  Total: {total} | Codex-ready: {codex_ready} | "
        f"Copilot-ready: {copilot_ready}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Assess package compatibility for the harness-agnostic catalog"
    )
    parser.add_argument("--plugin", help="Assess a specific plugin")
    parser.add_argument("--all", action="store_true", help="Assess all packages")
    parser.add_argument("--summary", action="store_true", help="Print classification summary")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed findings")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Assess without writing changes to catalog"
    )
    args = parser.parse_args()

    if not args.plugin and not args.all:
        parser.error("Specify --plugin NAME or --all")

    if args.plugin:
        names = [args.plugin]
    else:
        names = list_all_packages()

    results = {}
    errors = []

    for name in names:
        try:
            result = assess_package(name)
            results[name] = result

            if not args.dry_run:
                update_package_record(name, result)

            print_assessment(name, result, verbose=args.verbose)
        except FileNotFoundError as e:
            errors.append((name, str(e)))
            print(f"  {name}: ERROR - {e}", file=sys.stderr)

    if args.summary or args.all:
        print_summary(results)

    if not args.dry_run and results:
        print(f"\nUpdated {len(results)} package record(s) in catalog/packages/")

    if errors:
        print(f"\n{len(errors)} error(s) encountered", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
