---
name: claude-vis-stats
description: Query session analytics, cost tracking, token usage, and activity logs from the claude-vis database. Triggers when the user asks about session costs, spending, token usage, analytics, session history, or activity logs.
version: 1.0.0
allowed-tools:
  - Bash
  - Read
---

# Session Analytics

When the user asks about session costs, token usage, spending, session history, commands run, URLs visited, or any analytics question, run the appropriate query from the claude-vis stats engine.

## How to Query

Run via Bash with the appropriate subcommand:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/stats_query.py <subcommand> [args]
```

Subcommands:
- `recent [N]` — last N sessions (default 10)
- `cost-by-project` — cost grouped by project
- `totals` — grand totals across all sessions
- `session <id>` — detail for one session (supports partial ID prefix match)
- `tools` — most-used tools
- `commands [N]` — recent Bash commands
- `urls [N]` — recent WebFetch/WebSearch URLs

No arguments runs `recent` + `totals` together.

Present output directly — it is pre-formatted as markdown tables.
