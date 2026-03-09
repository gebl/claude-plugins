# Plugin Source Tracker & Upstream Sync Checker

## Purpose

Track where externally-sourced plugins came from and detect when upstream has changed, reporting what action is needed. Designed to evolve toward branch-based merge workflows.

## Components

### sources.json

Root-level manifest tracking upstream provenance:

```json
{
  "plugins": {
    "ask-questions-if-underspecified": {
      "upstream_repo": "https://github.com/trailofbits/skills.git",
      "upstream_path": "plugins/ask-questions-if-underspecified",
      "upstream_ref": "main",
      "last_synced_commit": "<sha>",
      "last_checked": "2026-03-08T20:00:00Z",
      "local_modifications": false
    }
  }
}
```

### scripts/sync-check.py

Python CLI tool (standalone script via `uv run` with inline metadata):

1. Reads `sources.json`
2. For each tracked plugin, fetches upstream ref (shallow clone to temp dir)
3. Compares `last_synced_commit` to current upstream HEAD
4. If different, diffs upstream changes against the synced version
5. Checks if local plugin directory has modifications vs synced snapshot
6. Reports status: `up-to-date`, `upstream-changed`, `local-modified`, `both-changed`

### CLI Interface

```bash
uv run scripts/sync-check.py                                    # Check all
uv run scripts/sync-check.py --plugin <name>                    # Check one
uv run scripts/sync-check.py --add --name <n> --repo <r> --path <p> --ref <ref>  # Track new
uv run scripts/sync-check.py --mark-synced --plugin <name>      # Record sync
```

### Dependencies

- Python 3.12+, no external packages (subprocess + json stdlib)
- `git` on PATH
- `uv` for running

### Future (v2): Branch-Based Merges

- `last_synced_commit` serves as merge base
- `local_modifications` informs 3-way merge need
- Functions structured for reuse by future `--merge` flag
