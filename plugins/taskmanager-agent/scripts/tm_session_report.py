"""Standalone CLI script to generate session metrics reports from the SQLite database."""

from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path

import click

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from taskmanager.daemon import database


@click.command()
@click.option("--project", default=None, help="Filter by project name.")
@click.option("--issue", default=None, help="Filter by issue identifier (e.g. LAN-42).")
@click.option("--since", default=None, help="Only sessions after this ISO date.")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["table", "csv", "json"]),
    default="table",
    help="Output format.",
)
def main(
    project: str | None,
    issue: str | None,
    since: str | None,
    output_format: str,
) -> None:
    """Generate a report of daemon session metrics."""
    database.init_db()

    sessions = database.query_sessions(
        project_name=project,
        issue_identifier=issue,
        since=since,
    )

    if output_format == "json":
        _output_json(sessions, project, since)
    elif output_format == "csv":
        _output_csv(sessions)
    else:
        _output_table(sessions, project, since)


def _output_json(
    sessions: list[dict],
    project: str | None,
    since: str | None,
) -> None:
    stats = database.get_summary_stats(project_name=project, since=since)
    click.echo(
        json.dumps(
            {"summary": stats, "sessions": sessions},
            indent=2,
            default=str,
        )
    )


def _output_csv(sessions: list[dict]) -> None:
    if not sessions:
        click.echo("No sessions found.")
        return

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=sessions[0].keys())
    writer.writeheader()
    writer.writerows(sessions)
    click.echo(buf.getvalue())


def _output_table(
    sessions: list[dict],
    project: str | None,
    since: str | None,
) -> None:
    try:
        from rich.console import Console
        from rich.table import Table
    except ImportError:
        click.echo("rich is required for table output: pip install rich")
        raise SystemExit(1)

    console = Console()

    # Summary stats
    stats = database.get_summary_stats(project_name=project, since=since)
    if not stats or stats.get("total_sessions", 0) == 0:
        console.print("[yellow]No sessions found.[/yellow]")
        return

    console.print()
    console.print("[bold]Session Metrics Summary[/bold]")
    console.print(f"  Total sessions:  {stats['total_sessions']}")
    console.print(f"  Unique issues:   {stats['unique_issues']}")
    console.print(f"  Total cost:      ${stats['total_cost']:.4f}")
    console.print(
        f"  Total tokens:    {stats['total_input_tokens']:,} in / {stats['total_output_tokens']:,} out"
    )
    console.print(f"  Avg duration:    {stats['avg_duration'] / 60:.1f}m")
    console.print(f"  Total turns:     {int(stats['total_turns']):,}")
    console.print()

    # Sessions table
    table = Table(title="Sessions")
    table.add_column("Issue", style="cyan", no_wrap=True)
    table.add_column("Project", style="green")
    table.add_column("Outcome", style="bold")
    table.add_column("Summary", max_width=50)
    table.add_column("PR", style="blue", max_width=60)
    table.add_column("Duration", justify="right")
    table.add_column("Cost", justify="right")
    table.add_column("Tokens (in/out)", justify="right")
    table.add_column("Turns", justify="right")
    table.add_column("Finished", style="dim")

    for s in sessions:
        duration = (
            f"{s.get('duration_seconds', 0) / 60:.1f}m"
            if s.get("duration_seconds")
            else "-"
        )
        cost = f"${s.get('total_cost_usd', 0):.4f}" if s.get("total_cost_usd") else "-"
        tokens_in = f"{s.get('input_tokens', 0):,}" if s.get("input_tokens") else "0"
        tokens_out = f"{s.get('output_tokens', 0):,}" if s.get("output_tokens") else "0"
        turns = str(s.get("num_turns", "-"))
        finished = s.get("finished_at", "-")
        if isinstance(finished, str) and len(finished) > 19:
            finished = finished[:19]

        summary = s.get("summary") or "-"
        if len(summary) > 50:
            summary = summary[:47] + "..."

        pr_url = s.get("pr_url") or "-"

        outcome_style = {
            "completed": "green",
            "timeout": "red",
            "unchanged": "yellow",
            "invalid_transition": "red",
            "missing_artifacts": "yellow",
        }.get(s.get("outcome", ""), "")

        outcome_text = (
            f"[{outcome_style}]{s.get('outcome', '-')}[/{outcome_style}]"
            if outcome_style
            else s.get("outcome", "-")
        )

        table.add_row(
            s.get("issue_identifier", "-"),
            s.get("project_name", "-"),
            outcome_text,
            summary,
            pr_url,
            duration,
            cost,
            f"{tokens_in}/{tokens_out}",
            turns,
            finished,
        )

    console.print(table)

    # Per-issue breakdown
    console.print()
    issue_map: dict[str, list[dict]] = {}
    for s in sessions:
        key = s.get("issue_identifier", "unknown")
        issue_map.setdefault(key, []).append(s)

    breakdown = Table(title="Per-Issue Breakdown")
    breakdown.add_column("Issue", style="cyan", no_wrap=True)
    breakdown.add_column("Sessions", justify="right")
    breakdown.add_column("Total Cost", justify="right")
    breakdown.add_column("Total Duration", justify="right")
    breakdown.add_column("Outcomes")
    breakdown.add_column("Latest Summary", max_width=50)

    for issue_key, issue_sessions in sorted(issue_map.items()):
        total_cost = sum(s.get("total_cost_usd") or 0 for s in issue_sessions)
        total_duration = sum(s.get("duration_seconds") or 0 for s in issue_sessions)
        outcomes = {}
        for s in issue_sessions:
            o = s.get("outcome", "unknown")
            outcomes[o] = outcomes.get(o, 0) + 1
        outcomes_str = ", ".join(f"{k}:{v}" for k, v in sorted(outcomes.items()))

        # Most recent session's summary (sessions are ordered by finished_at DESC)
        latest_summary = "-"
        for s in issue_sessions:
            if s.get("summary"):
                latest_summary = str(s["summary"])
                break
        if len(latest_summary) > 50:
            latest_summary = latest_summary[:47] + "..."

        breakdown.add_row(
            issue_key,
            str(len(issue_sessions)),
            f"${total_cost:.4f}",
            f"{total_duration / 60:.1f}m",
            outcomes_str,
            latest_summary,
        )

    console.print(breakdown)


if __name__ == "__main__":
    main()
