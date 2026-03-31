---
name: stats
description: "Query claude-vis session analytics: recent sessions, cost breakdown, token usage, and more"
allowed-tools:
  - Bash
  - Read
---

# /stats — Session Analytics

Query the claude-vis SQLite database for session activity and cost analytics.

Arguments: $ARGUMENTS

Run the appropriate query based on what the user asks for. If no specific query type is mentioned, run the default (recent + totals).

## Available Queries

Run these via Bash:

**Default (recent sessions + totals):**
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/stats_query.py
```

**Recent sessions:**
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/stats_query.py recent 10
```

**Cost by project:**
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/stats_query.py cost-by-project
```

**Grand totals:**
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/stats_query.py totals
```

**Session detail** (accepts full or partial session ID):
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/stats_query.py session <session_id>
```

**Most used tools:**
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/stats_query.py tools
```

**Recent commands run:**
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/stats_query.py commands
```

**Recent URLs fetched:**
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/stats_query.py urls
```

Present the output directly to the user — it is already formatted as markdown.
