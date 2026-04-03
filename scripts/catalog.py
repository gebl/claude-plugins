# /// script
# requires-python = ">=3.12"
# dependencies = ["rich"]
# ///

import argparse
import json
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.pretty import pprint

CATALOG_DIR = Path(__file__).resolve().parent.parent / "catalog" / "packages"
console = Console()


def load_all_packages() -> list[dict]:
    """Load all package JSON files from the catalog directory."""
    packages = []
    for path in sorted(CATALOG_DIR.glob("*.json")):
        with path.open() as f:
            packages.append(json.load(f))
    return packages


def load_package(name: str) -> dict | None:
    """Load a single package by name."""
    path = CATALOG_DIR / f"{name}.json"
    if not path.exists():
        return None
    with path.open() as f:
        return json.load(f)


def get_harness_status(pkg: dict, harness: str) -> str:
    """Get the status for a specific harness, defaulting to 'unknown'."""
    return pkg.get("compatibility", {}).get("status_by_harness", {}).get(harness, "unknown")


def get_support_basis(pkg: dict, harness: str) -> str:
    """Get the support basis for a specific harness, defaulting to 'unknown'."""
    return pkg.get("compatibility", {}).get("support_basis", {}).get(harness, "unknown")


def get_portability_class(pkg: dict) -> str:
    """Get the portability class, defaulting to 'unknown'."""
    return pkg.get("compatibility", {}).get("portability_class", "unknown")


def filter_packages(
    packages: list[dict],
    *,
    harness: str | None = None,
    port_class: str | None = None,
    status: str | None = None,
    basis: str | None = None,
    verified: bool = False,
    has_executable_code: bool = False,
) -> list[dict]:
    """Apply all filters to a list of packages."""
    result = packages

    if harness:
        result = [
            p for p in result
            if harness in p.get("compatibility", {}).get("supported_harnesses", [])
        ]

    if port_class:
        result = [p for p in result if get_portability_class(p) == port_class]

    if status:
        if not harness:
            console.print("[red]Error:[/] --status requires --harness", style="bold")
            sys.exit(1)
        result = [p for p in result if get_harness_status(p, harness) == status]

    if basis:
        if not harness:
            console.print("[red]Error:[/] --basis requires --harness", style="bold")
            sys.exit(1)
        result = [p for p in result if get_support_basis(p, harness) == basis]

    if verified:
        result = [p for p in result if p.get("verification", {}).get("reviewed", False)]

    if has_executable_code:
        result = [p for p in result if p.get("risk", {}).get("has_executable_code", False)]

    return result


def style_status(status: str) -> str:
    """Return a rich-styled status string."""
    styles = {
        "native": "[green]native[/]",
        "generated": "[cyan]generated[/]",
        "adapted": "[yellow]adapted[/]",
        "unsupported": "[red]unsupported[/]",
        "blocked": "[bold red]blocked[/]",
    }
    return styles.get(status, f"[dim]{status}[/]")


def style_class(port_class: str) -> str:
    """Return a rich-styled portability class string."""
    styles = {
        "agnostic": "[green]agnostic[/]",
        "adaptable": "[yellow]adaptable[/]",
        "harness-specific": "[red]harness-specific[/]",
    }
    return styles.get(port_class, f"[dim]{port_class}[/]")


def cmd_list(args: argparse.Namespace) -> None:
    """Handle the 'list' subcommand."""
    packages = load_all_packages()
    filtered = filter_packages(
        packages,
        harness=args.harness,
        port_class=getattr(args, "class"),
        status=args.status,
        basis=args.basis,
        verified=args.verified,
        has_executable_code=args.has_executable_code,
    )

    if not filtered:
        console.print("[dim]No packages match the given filters.[/]")
        return

    table = Table(title="Plugin Catalog")
    table.add_column("Name", style="bold")
    table.add_column("Class")
    table.add_column("Claude")
    table.add_column("Codex")
    table.add_column("Verified", justify="center")

    for pkg in filtered:
        name = pkg.get("name", "?")
        port_class = get_portability_class(pkg)
        claude_status = get_harness_status(pkg, "claude")
        codex_status = get_harness_status(pkg, "codex")
        reviewed = pkg.get("verification", {}).get("reviewed", False)

        table.add_row(
            name,
            style_class(port_class),
            style_status(claude_status),
            style_status(codex_status),
            "[green]yes[/]" if reviewed else "[dim]no[/]",
        )

    console.print(table)


def cmd_show(args: argparse.Namespace) -> None:
    """Handle the 'show' subcommand."""
    pkg = load_package(args.name)
    if not pkg:
        console.print(f"[red]Error:[/] package '{args.name}' not found")
        sys.exit(1)

    pprint(pkg, console=console, expand_all=True)


def cmd_findings(args: argparse.Namespace) -> None:
    """Handle the 'findings' subcommand."""
    pkg = load_package(args.name)
    if not pkg:
        console.print(f"[red]Error:[/] package '{args.name}' not found")
        sys.exit(1)

    findings = pkg.get("compatibility", {}).get("findings", [])
    if not findings:
        console.print(f"[dim]No findings for '{args.name}'.[/]")
        return

    table = Table(title=f"Findings: {args.name}")
    table.add_column("Severity")
    table.add_column("Code", style="bold")
    table.add_column("Kind")
    table.add_column("Path")
    table.add_column("Message")

    severity_styles = {
        "error": "[bold red]error[/]",
        "warning": "[yellow]warning[/]",
        "info": "[dim]info[/]",
    }

    for f in findings:
        table.add_row(
            severity_styles.get(f.get("severity", ""), f.get("severity", "")),
            f.get("code", ""),
            f.get("kind", ""),
            f.get("path", ""),
            f.get("message", ""),
        )

    console.print(table)


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        description="Query the harness-agnostic plugin catalog",
    )
    subs = parser.add_subparsers(dest="command", required=True)

    # list
    ls = subs.add_parser("list", help="List packages with optional filters")
    ls.add_argument("--harness", help="Filter by supported harness (e.g. claude, codex)")
    ls.add_argument("--class", dest="class", choices=["agnostic", "adaptable", "harness-specific", "unknown"],
                     help="Filter by portability class")
    ls.add_argument("--status", choices=["native", "generated", "adapted", "unsupported", "blocked", "unknown"],
                     help="Filter by per-harness status (requires --harness)")
    ls.add_argument("--basis", choices=["official", "adapter", "convention", "unsupported", "unknown"],
                     help="Filter by support basis (requires --harness)")
    ls.add_argument("--verified", action="store_true", help="Only fully verified packages")
    ls.add_argument("--has-executable-code", action="store_true", help="Only packages with executable code")

    # show
    show = subs.add_parser("show", help="Pretty-print a package record")
    show.add_argument("name", help="Package name")

    # findings
    findings = subs.add_parser("findings", help="Show compatibility findings for a package")
    findings.add_argument("name", help="Package name")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    handlers = {
        "list": cmd_list,
        "show": cmd_show,
        "findings": cmd_findings,
    }
    handlers[args.command](args)


if __name__ == "__main__":
    main()
