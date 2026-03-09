# Anvil Claude Code Plugin Marketplace

Private plugin marketplace for Claude Code, hosted on Forgejo.

## Adding This Marketplace to Claude Code

```
/plugin marketplace add git@forgejo.bishop.landq.net:Anvil/claude-plugins.git
```

After adding, browse and install plugins with `/plugin`.

## Adding a New Plugin

### From an upstream source (fork)

1. Copy the plugin into `plugins/`:

```bash
git clone --depth 1 https://github.com/org/repo.git /tmp/source
cp -r /tmp/source/plugins/plugin-name plugins/
rm -rf /tmp/source
```

2. Register it in `.claude-plugin/marketplace.json` — add an entry to the `plugins` array:

```json
{
  "name": "plugin-name",
  "version": "1.0.0",
  "description": "What the plugin does",
  "author": { "name": "Author Name" },
  "source": "./plugins/plugin-name"
}
```

3. Track the upstream source for future sync checks:

```bash
uv run scripts/sync-check.py --add \
  --name plugin-name \
  --repo https://github.com/org/repo.git \
  --path plugins/plugin-name \
  --ref main
```

4. Commit and push:

```bash
git add plugins/plugin-name .claude-plugin/marketplace.json sources.json
git commit -m "Add plugin-name from org/repo"
git push origin main
```

### Creating your own plugin

1. Create the plugin directory structure:

```bash
mkdir -p plugins/my-plugin/.claude-plugin
mkdir -p plugins/my-plugin/skills/my-skill
```

2. Add a `plugins/my-plugin/.claude-plugin/plugin.json`:

```json
{
  "name": "my-plugin",
  "version": "1.0.0",
  "description": "What it does"
}
```

3. Add skills, agents, commands, or hooks as needed under the plugin directory.

4. Register it in `.claude-plugin/marketplace.json` and commit.

No need to add locally-authored plugins to `sources.json` — that's only for tracking upstream forks.

## Checking for Upstream Updates

Run the sync checker to see if any forked plugins have diverged from their upstream sources:

```bash
# Check all tracked plugins
uv run scripts/sync-check.py

# Check a specific plugin
uv run scripts/sync-check.py --plugin ask-questions-if-underspecified
```

### Status meanings

| Status | Meaning | Action |
|--------|---------|--------|
| `up-to-date` | No changes anywhere | Nothing to do |
| `upstream-changed` | Upstream has new commits | Safe to pull changes |
| `local-modified` | You've made local changes | Upstream unchanged |
| `both-changed` | Both sides diverged | Manual merge needed |

### After merging upstream changes

Mark the plugin as synced so future checks use the new baseline:

```bash
uv run scripts/sync-check.py --mark-synced --plugin plugin-name
```

## Pointing to External Repos

Plugins don't have to live in this monorepo. In `marketplace.json`, use a git URL source instead of a relative path:

```json
{
  "name": "external-plugin",
  "source": {
    "source": "url",
    "url": "https://forgejo.bishop.landq.net/Anvil/standalone-plugin.git"
  }
}
```

## Repository Structure

```
claude-plugins/
├── .claude-plugin/
│   └── marketplace.json      # Plugin registry (what Claude Code reads)
├── sources.json               # Upstream provenance tracking
├── scripts/
│   └── sync-check.py          # Upstream sync checker
├── docs/plans/                 # Design documents
└── plugins/
    └── <plugin-name>/         # One directory per plugin
        ├── .claude-plugin/
        │   └── plugin.json
        ├── skills/
        ├── agents/
        ├── commands/
        └── hooks/
```
