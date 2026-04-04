"""Query engine for claude-vis session analytics. Outputs markdown tables."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import db


def fmt_duration(ms: int | None) -> str:
    if not ms:
        return "-"
    secs = ms / 1000
    if secs < 60:
        return f"{secs:.0f}s"
    mins = secs / 60
    if mins < 60:
        return f"{mins:.1f}m"
    hours = mins / 60
    return f"{hours:.1f}h"


def fmt_tokens(n: int | None) -> str:
    if not n:
        return "0"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def fmt_cost(usd: float | None) -> str:
    if not usd:
        return "$0.00"
    return f"${usd:.4f}" if usd < 0.01 else f"${usd:.2f}"


def fmt_date(iso: str | None) -> str:
    if not iso:
        return "-"
    return iso[:16].replace("T", " ")


def truncate(s: str | None, n: int = 60) -> str:
    if not s:
        return "-"
    return s[:n] + "..." if len(s) > n else s


def project_name(row: dict) -> str:
    repo = row.get("git_repo") or row.get("project")
    if repo:
        # Extract repo name from URL
        name = repo.rstrip("/").rsplit("/", 1)[-1]
        if name.endswith(".git"):
            name = name[:-4]
        return name
    cwd = row.get("cwd", "")
    return Path(cwd).name if cwd else "-"


def cmd_recent(n: int = 10) -> None:
    rows = db.recent_sessions(n)
    if not rows:
        print("No sessions recorded yet.")
        return

    print(f"## Recent Sessions (last {n})\n")
    print("| Date | Project | Model | Cost | In/Out Tokens | Turns | Duration | Summary |")
    print("|------|---------|-------|------|---------------|-------|----------|---------|")
    for r in rows:
        print(
            f"| {fmt_date(r['started_at'])} "
            f"| {project_name(r)} "
            f"| {r.get('model') or '-'} "
            f"| {fmt_cost(r['total_cost_usd'])} "
            f"| {fmt_tokens(r['total_input_tokens'])}/{fmt_tokens(r['total_output_tokens'])} "
            f"| {r.get('turn_count', 0)} "
            f"| {fmt_duration(r.get('duration_ms'))} "
            f"| {truncate(r.get('summary'), 40)} |"
        )


def cmd_cost_by_project() -> None:
    rows = db.cost_by_project()
    if not rows:
        print("No sessions recorded yet.")
        return

    print("## Cost by Project\n")
    print("| Project | Sessions | Total Cost | Input Tokens | Output Tokens | Duration |")
    print("|---------|----------|------------|--------------|---------------|----------|")
    for r in rows:
        print(
            f"| {project_name(r)} "
            f"| {r['session_count']} "
            f"| {fmt_cost(r['total_cost'])} "
            f"| {fmt_tokens(r['total_input'])} "
            f"| {fmt_tokens(r['total_output'])} "
            f"| {fmt_duration(r.get('total_duration_ms'))} |"
        )


def cmd_totals() -> None:
    t = db.totals()
    if not t or not t.get("session_count"):
        print("No sessions recorded yet.")
        return

    print("## Grand Totals\n")
    print(f"- **Sessions**: {t['session_count']}")
    print(f"- **Total Cost**: {fmt_cost(t['total_cost'])}")
    print(f"- **Input Tokens**: {fmt_tokens(t['total_input'])}")
    print(f"- **Output Tokens**: {fmt_tokens(t['total_output'])}")
    print(f"- **Total Turns**: {t.get('total_turns', 0)}")
    print(f"- **Total Duration**: {fmt_duration(t.get('total_duration_ms'))}")
    print(f"- **Lines Added**: {t.get('total_lines_added', 0)}")
    print(f"- **Lines Removed**: {t.get('total_lines_removed', 0)}")


def cmd_session(session_id: str) -> None:
    detail = db.session_detail(session_id)
    if not detail:
        # Try prefix match
        conn = db.get_db()
        try:
            row = conn.execute(
                "SELECT session_id FROM sessions WHERE session_id LIKE ? LIMIT 1",
                (f"{session_id}%",),
            ).fetchone()
        finally:
            conn.close()

        if row:
            detail = db.session_detail(row["session_id"])

    if not detail:
        print(f"Session `{session_id}` not found.")
        return

    print(f"## Session Detail: `{detail['session_id'][:12]}...`\n")
    print(f"- **Model**: {detail.get('model') or '-'}")
    print(f"- **CWD**: {detail.get('cwd') or '-'}")
    print(f"- **Git**: {detail.get('git_repo') or '-'} @ {detail.get('git_branch') or '-'}")
    print(f"- **Started**: {fmt_date(detail.get('started_at'))}")
    print(f"- **Ended**: {fmt_date(detail.get('ended_at'))}")
    print(f"- **Duration**: {fmt_duration(detail.get('duration_ms'))}")
    print(f"- **Cost**: {fmt_cost(detail.get('total_cost_usd'))}")
    print(f"- **Tokens**: {fmt_tokens(detail.get('total_input_tokens'))} in / {fmt_tokens(detail.get('total_output_tokens'))} out")
    print(f"- **Cache**: {fmt_tokens(detail.get('cache_creation_tokens'))} created / {fmt_tokens(detail.get('cache_read_tokens'))} read")
    print(f"- **Turns**: {detail.get('turn_count', 0)}")
    print(f"- **Lines**: +{detail.get('lines_added', 0)} / -{detail.get('lines_removed', 0)}")
    print(f"- **Summary**: {detail.get('summary') or '-'}")

    if detail.get("tools"):
        print("\n### Tool Usage\n")
        print("| Tool | Count |")
        print("|------|-------|")
        for t in detail["tools"]:
            print(f"| {t['tool_name']} | {t['count']} |")

    if detail.get("commands"):
        print("\n### Commands Run\n")
        print("| Time | Command | Exit |")
        print("|------|---------|------|")
        for c in detail["commands"]:
            print(f"| {fmt_date(c['timestamp'])} | `{truncate(c['command'], 60)}` | {c.get('exit_code') or '-'} |")

    if detail.get("urls"):
        print("\n### URLs Fetched\n")
        print("| Time | Source | URL/Query |")
        print("|------|--------|-----------|")
        for u in detail["urls"]:
            display = u.get("url") or u.get("query") or "-"
            print(f"| {fmt_date(u['timestamp'])} | {u['source']} | {truncate(display, 60)} |")


def cmd_tools(n: int = 20) -> None:
    rows = db.top_tools(n)
    if not rows:
        print("No tool usage recorded yet.")
        return

    print("## Most Used Tools\n")
    print("| Tool | Count |")
    print("|------|-------|")
    for r in rows:
        print(f"| {r['tool_name']} | {r['count']} |")


def cmd_commands(n: int = 20) -> None:
    rows = db.recent_commands(n)
    if not rows:
        print("No commands recorded yet.")
        return

    print(f"## Recent Commands (last {n})\n")
    print("| Time | Project | Command | Exit |")
    print("|------|---------|---------|------|")
    for r in rows:
        print(
            f"| {fmt_date(r['timestamp'])} "
            f"| {project_name(r)} "
            f"| `{truncate(r['command'], 50)}` "
            f"| {r.get('exit_code') or '-'} |"
        )


def cmd_urls(n: int = 20) -> None:
    rows = db.recent_urls(n)
    if not rows:
        print("No URLs recorded yet.")
        return

    print(f"## Recent URLs (last {n})\n")
    print("| Time | Source | URL/Query | Project |")
    print("|------|--------|-----------|---------|")
    for r in rows:
        display = r.get("url") or r.get("query") or "-"
        print(
            f"| {fmt_date(r['timestamp'])} "
            f"| {r['source']} "
            f"| {truncate(display, 50)} "
            f"| {project_name(r)} |"
        )


COMMANDS = {
    "recent": lambda args: cmd_recent(int(args[0]) if args else 10),
    "cost-by-project": lambda args: cmd_cost_by_project(),
    "totals": lambda args: cmd_totals(),
    "session": lambda args: cmd_session(args[0]) if args else print("Usage: session <id>"),
    "tools": lambda args: cmd_tools(int(args[0]) if args else 20),
    "commands": lambda args: cmd_commands(int(args[0]) if args else 20),
    "urls": lambda args: cmd_urls(int(args[0]) if args else 20),
}


def main() -> None:
    args = sys.argv[1:]

    if not args:
        cmd_recent(10)
        print()
        cmd_totals()
        return

    subcmd = args[0]
    if subcmd in COMMANDS:
        COMMANDS[subcmd](args[1:])
    else:
        print(f"Unknown command: {subcmd}")
        print(f"Available: {', '.join(COMMANDS)}")


if __name__ == "__main__":
    main()
