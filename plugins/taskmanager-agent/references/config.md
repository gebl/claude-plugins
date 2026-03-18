# Config Reference

## Reading the Config File

Use the Read tool to read `~/.claude/taskmanager.yaml`.

Parse the YAML content mentally.

### Missing Config

If the file is missing, stop and tell the user:

> "Config not found. Run `/tm-health` first."

### Stale Config

If `last_health_check` is more than 24 hours old, warn the user:

> "Config is stale. Consider running `/tm-health`."

### Fields to Extract

| Field                  | Description                                         |
|------------------------|-----------------------------------------------------|
| `team`                 | Team identifier string                              |
| `statuses`             | Available issue statuses                            |
| `labels`               | Available issue labels                              |
| `projects`             | Project definitions (name, repo, local_path, etc.)  |
| `operator`             | Current operator/user ID                            |
| `stale_threshold_hours`| Hours before an in-progress issue is considered stale |

### Updating the Config

1. Read the current file with the Read tool.
2. Modify the specific field(s) needed.
3. Write the full file back — never write partial content.

## Running Scripts

All CLI scripts live in `${CLAUDE_PLUGIN_ROOT}/scripts/` and must be invoked with the plugin's own virtual environment:

```
${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/<script>.py <args>
```

The `.venv` is set up by `/tm-health` (Step 0). If a script fails with `ModuleNotFoundError`, tell the user to run `/tm-health` to repair the environment.

Every script supports `--help` for usage details. Scripts output JSON to stdout.
