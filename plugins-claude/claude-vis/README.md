# claude-vis

A Claude Code plugin that logs session activity, token usage, and cost to a local SQLite database. Gives you full visibility into how you use Claude Code across projects.

## What it tracks

- **Sessions** -- start/end time, model, project, git branch, duration, token counts, cost, and a summary of what was asked
- **Tool usage** -- every tool call (Read, Write, Edit, Bash, Grep, etc.) with timestamps
- **Commands** -- every Bash command executed, in a dedicated table for easy querying
- **URLs** -- every WebFetch URL and WebSearch query

All data is stored locally in `~/.config/claude-vis/sessions.db`.

## How it works

Four hooks fire automatically during Claude Code sessions:

| Hook | When | What it logs |
|------|------|-------------|
| `SessionStart` | Session begins | Creates session row with cwd, model, git repo/branch |
| `PostToolUse` | After each tool call | Tool name + Bash commands and URLs to separate tables |
| `Stop` | After each assistant turn | Increments turn counter |
| `SessionEnd` | Session ends | Parses transcript for token totals and summary, calculates duration |

No status line modification required. Zero external dependencies -- stdlib Python only.

## Installation

Clone the repo:

```bash
git clone ssh://git@forgejo.bishop.landq.net:2222/Anvil/claude-vis.git ~/Projects/claude-vis
```

Add to your `~/.claude/settings.json`:

```json
{
  "enabledPlugins": {
    "claude-vis@local": true
  }
}
```

Then register the plugin path. The simplest way is to symlink it into your local plugins directory, or point Claude Code at the repo path during plugin development.

Restart Claude Code. The hooks will start logging automatically.

## Querying your data

### /cv-stats command

Use the `/cv-stats` slash command to query analytics from within Claude Code:

```
/cv-stats                    # recent sessions + grand totals
/cv-stats recent 20          # last 20 sessions
/cv-stats cost-by-project    # cost grouped by project
/cv-stats totals             # grand totals across all sessions
/cv-stats session <id>       # detail for a session (partial ID works)
/cv-stats tools              # most-used tools
/cv-stats commands           # recent Bash commands
/cv-stats urls               # recent WebFetch/WebSearch URLs
```

You can also just ask naturally -- the stats skill auto-triggers on questions about cost, tokens, spending, or session history.

### Direct SQLite access

```bash
sqlite3 ~/.config/claude-vis/sessions.db
```

Useful queries:

```sql
-- Recent sessions with cost
SELECT session_id, model, cwd, total_cost_usd, turn_count, summary
FROM sessions ORDER BY started_at DESC LIMIT 10;

-- Total spend
SELECT SUM(total_cost_usd) AS total_spend FROM sessions;

-- Cost by project
SELECT COALESCE(git_repo, cwd) AS project, SUM(total_cost_usd) AS cost
FROM sessions GROUP BY project ORDER BY cost DESC;

-- Most-used tools
SELECT tool_name, COUNT(*) AS n FROM tool_uses GROUP BY tool_name ORDER BY n DESC;

-- All commands from today
SELECT command, timestamp FROM commands_run
WHERE timestamp >= date('now') ORDER BY timestamp;
```

## Database schema

**sessions** -- one row per Claude Code session

| Column | Type | Description |
|--------|------|-------------|
| session_id | TEXT PK | Session identifier |
| model | TEXT | Model used (opus, sonnet, etc.) |
| cwd | TEXT | Working directory |
| git_repo | TEXT | Git remote URL |
| git_branch | TEXT | Branch name |
| started_at / ended_at | TEXT | ISO 8601 timestamps |
| duration_ms | INTEGER | Wall clock duration |
| total_input_tokens | INTEGER | Total input tokens consumed |
| total_output_tokens | INTEGER | Total output tokens generated |
| cache_creation_tokens | INTEGER | Tokens used for cache creation |
| cache_read_tokens | INTEGER | Tokens read from cache |
| total_cost_usd | REAL | Session cost in USD |
| turn_count | INTEGER | Number of assistant turns |
| summary | TEXT | First user prompt (truncated to 200 chars) |

**tool_uses** -- one row per tool call

| Column | Type | Description |
|--------|------|-------------|
| session_id | TEXT FK | Parent session |
| tool_name | TEXT | Tool name (Bash, Edit, Read, etc.) |
| timestamp | TEXT | When the tool was called |
| success | INTEGER | 1 for success |

**commands_run** -- one row per Bash command

| Column | Type | Description |
|--------|------|-------------|
| session_id | TEXT FK | Parent session |
| command | TEXT | The command string |
| timestamp | TEXT | When it ran |
| exit_code | INTEGER | Exit code (if available) |

**urls_fetched** -- one row per web request

| Column | Type | Description |
|--------|------|-------------|
| session_id | TEXT FK | Parent session |
| url | TEXT | URL or search query |
| source | TEXT | `WebFetch` or `WebSearch` |
| query | TEXT | Prompt (WebFetch) or search query (WebSearch) |
| timestamp | TEXT | When it was fetched |

## Limitations

- **No rate limit tracking** -- rate limit data is only available via the status line JSON, which this plugin does not intercept. This is planned for a future version.
- **No context window tracking** -- same reason as above.
- **Cost is estimated from transcript token counts** -- not from billing API.
- **Summary is basic** -- v1 just captures the first user prompt. LLM-generated summaries are planned.

## Requirements

- Python 3.12+
- Claude Code with plugin support
- No external Python dependencies
