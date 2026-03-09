# Anvil Claude Code Plugin Marketplace

Private plugin marketplace for Claude Code, hosted on Forgejo.

## Adding This Marketplace to Claude Code

```
/plugin marketplace add git@forgejo.bishop.landq.net:Anvil/claude-plugins.git
```

After adding, browse and install plugins with `/plugin`.

## Adding a New Plugin

### From an upstream plugin repo (fork)

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

### From a raw skill repo (auto-wrapping)

For repos that contain standalone `SKILL.md` files without plugin packaging (e.g., ComposioHQ/awesome-claude-skills):

```bash
uv run scripts/sync-check.py --import-skill \
  --name skill-name \
  --repo https://github.com/org/repo.git \
  --path skill-name \
  --ref main
```

This will:
- Read `SKILL.md` frontmatter to extract metadata
- Auto-generate the plugin wrapper (`.claude-plugin/plugin.json`)
- Copy all skill files (scripts, examples, references)
- Register in both `marketplace.json` and `sources.json`
- Detect and flag any executable code
- Warn about dependency files that may need installation

Use `--force` to import even if the `SKILL.md` frontmatter is malformed or missing required fields.

Both `--add` and `--import-skill` run a semgrep security scan before importing. If findings are detected, the import is blocked. Use `--skip-scan` to bypass:

```bash
uv run scripts/sync-check.py --import-skill --skip-scan \
  --name skill-name --repo URL --path P --ref main
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

```bash
# Check all tracked plugins
uv run scripts/sync-check.py

# Check a specific plugin
uv run scripts/sync-check.py --plugin plugin-name

# Show full diff of changes
uv run scripts/sync-check.py --diff
uv run scripts/sync-check.py --diff --plugin plugin-name
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

## Verification Workflow

All imported plugins start as unverified. This tracks whether you've reviewed the code — especially important for plugins containing executable scripts.

```bash
# List all plugins pending review
uv run scripts/sync-check.py --pending

# Mark a plugin as reviewed and verified
uv run scripts/sync-check.py --mark-verified --plugin plugin-name
```

The `--pending` command rescans plugin directories for executable code (.sh, .bash, .zsh, .py, .js, .ts, .rb, .pl, files with shebangs, or executable permissions) and highlights which plugins need attention.

### Security scanning with semgrep

Run semgrep against unverified plugins to catch security issues before marking them as verified:

```bash
# Scan all unverified plugins
uv run scripts/sync-check.py --scan

# Scan a specific plugin
uv run scripts/sync-check.py --scan --plugin plugin-name
```

Scans use three rulesets: `auto` (broad coverage), `p/secrets` (credential detection), and `p/trailofbits` (security-focused rules). Requires semgrep (`uv tool install semgrep`).

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
│   └── sync-check.py          # Plugin management tool
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

## Quick Reference

```bash
# Sync checking
uv run scripts/sync-check.py                      # Check all plugins
uv run scripts/sync-check.py --diff                # Check with full diff
uv run scripts/sync-check.py --plugin NAME         # Check one plugin
uv run scripts/sync-check.py --mark-synced --plugin NAME  # Record sync

# Importing
uv run scripts/sync-check.py --add --name N --repo URL --path P       # Track a plugin
uv run scripts/sync-check.py --import-skill --name N --repo URL --path P  # Import raw skill

# Verification
uv run scripts/sync-check.py --pending                     # List unverified
uv run scripts/sync-check.py --scan                        # Semgrep scan unverified
uv run scripts/sync-check.py --scan --plugin NAME          # Scan one plugin
uv run scripts/sync-check.py --mark-verified --plugin NAME  # Mark as reviewed
```
