# Anvil Claude Code Plugin Marketplace

Plugin marketplace for Claude Code, hosted on github/forgejo to integrate with claud code and cowork.

## Available Plugins

| Plugin | Description | Author | Source |
|--------|-------------|--------|--------|
| ask-questions-if-underspecified | Clarify ambiguous requirements by asking questions before implementing | Kevin Valerio | [trailofbits/skills](https://github.com/trailofbits/skills) |
| devcontainer-setup | Create pre-configured devcontainers with Claude Code and language-specific tooling | Alexis Challande | [trailofbits/skills](https://github.com/trailofbits/skills) |
| differential-review | Security-focused differential review of code changes with blast radius estimation | Omar Inuwa | [trailofbits/skills](https://github.com/trailofbits/skills) |
| git-cleanup | Safely analyzes and cleans up local git branches and worktrees | Henrik Brodin | [trailofbits/skills](https://github.com/trailofbits/skills) |
| grill-me | Stress-test a plan or design through relentless questioning | Matt Pocock | [mattpocock/skills](https://github.com/mattpocock/skills) |
| insecure-defaults | Detects insecure default configurations (hardcoded creds, weak auth, etc.) | Trail of Bits | [trailofbits/skills](https://github.com/trailofbits/skills) |
| modern-python | Modern Python best practices with uv, ruff, and ty | William Tan | [trailofbits/skills](https://github.com/trailofbits/skills) |
| semgrep-rule-creator | Create custom Semgrep rules for detecting bugs and security vulnerabilities | Maciej Domanski | [trailofbits/skills](https://github.com/trailofbits/skills) |
| taskmanager-agent | Backend-agnostic task management agent (Linear, etc.) with worktree-based execution | Anvil | Internal |
| variant-analysis | Find similar vulnerabilities across codebases using pattern-based analysis | Axel Mierczuk | [trailofbits/skills](https://github.com/trailofbits/skills) |
| workflow-skill-design | Design patterns and review agent for workflow-based Claude Code skills | Benjamin Samuels | [trailofbits/skills](https://github.com/trailofbits/skills) |
| yt-transcript | Fetch YouTube video transcripts and save as Markdown | Anvil | Internal |

## Setup

Add the marketplace to Claude Code:

```
/plugin marketplace add git@<HOSTNAME>:Anvil/claude-plugins.git
```

Browse and install plugins with `/plugin`.

**Optional:** Install semgrep for automatic security scanning during imports:

```bash
uv tool install semgrep
```

## Adding Plugins

All imports are automatically scanned with semgrep before anything is written to disk. If findings are detected, the import is blocked. Use `--dry-run` to validate without modifying files, or `--skip-scan` to bypass the scan.

### From an upstream plugin repo

Fetches the plugin, scans it with semgrep, copies it into `plugins/`, and registers it in both `marketplace.json` and `sources.json`:

```bash
uv run scripts/sync-check.py --add \
  --repo https://github.com/org/repo.git \
  --path plugins/plugin-name
```

The plugin name is inferred from `--path` (here: `plugin-name`). Use `--name` to override. Then commit and push.

### From a raw skill repo

For repos with standalone `SKILL.md` files without plugin packaging (e.g., ComposioHQ/awesome-claude-skills). This auto-generates the plugin wrapper, copies all files, and registers everything:

```bash
uv run scripts/sync-check.py --import-skill \
  --repo https://github.com/org/repo.git \
  --path skill-name
```

Use `--force` if the `SKILL.md` frontmatter is malformed or missing required fields.

### Creating your own plugin

1. Create the directory structure:

```bash
mkdir -p plugins/my-plugin/.claude-plugin
mkdir -p plugins/my-plugin/skills/my-skill
```

2. Add `plugins/my-plugin/.claude-plugin/plugin.json`:

```json
{
  "name": "my-plugin",
  "version": "1.0.0",
  "description": "What it does"
}
```

3. Add skills, agents, commands, or hooks under the plugin directory.

4. Register in `.claude-plugin/marketplace.json` and commit.

Locally-authored plugins don't need a `sources.json` entry — that's only for upstream forks.

### External repos

Plugins don't have to live in this monorepo. Use a git URL in `marketplace.json`:

```json
{
  "name": "external-plugin",
  "source": {
    "source": "url",
    "url": "https://<HOSTNAME>/Anvil/standalone-plugin.git"
  }
}
```

## Upstream Sync

Check if upstream repos have new changes:

```bash
uv run scripts/sync-check.py                # All tracked plugins
uv run scripts/sync-check.py --plugin NAME   # One plugin
uv run scripts/sync-check.py --diff          # Include full diffs
```

| Status | Meaning | Action |
|--------|---------|--------|
| `up-to-date` | No changes | Nothing to do |
| `upstream-changed` | Upstream has new commits | Safe to pull |
| `local-modified` | Local changes only | Upstream unchanged |
| `both-changed` | Both sides diverged | Manual merge needed |

After merging upstream changes, update the baseline:

```bash
uv run scripts/sync-check.py --mark-synced --plugin NAME
```

## Verification Workflow

Imported plugins start unverified. The recommended workflow:

```
1. --pending        List what needs review
2. --scan           Run semgrep on unverified plugins
3. Review code      Read the findings and source
4. --mark-verified  Mark as reviewed
```

```bash
# List unverified plugins (rescans for executable code)
uv run scripts/sync-check.py --pending

# Run semgrep security scan (auto + p/secrets + p/trailofbits rulesets)
uv run scripts/sync-check.py --scan
uv run scripts/sync-check.py --scan --plugin NAME

# Mark as reviewed after inspection
uv run scripts/sync-check.py --mark-verified --plugin NAME
```

## Repository Structure

```
claude-plugins/
├── .claude-plugin/
│   └── marketplace.json      # Plugin registry (what Claude Code reads)
├── sources.json               # Upstream provenance tracking
├── ruff.toml                  # Linter config for scripts/
├── scripts/
│   └── sync-check.py          # Plugin management CLI
├── docs/plans/                 # Design documents
└── plugins/
    └── <plugin-name>/
        ├── .claude-plugin/
        │   └── plugin.json
        ├── skills/
        ├── agents/
        ├── commands/
        └── hooks/
```

## Quick Reference

```bash
# Importing (name inferred from --path, override with --name)
uv run scripts/sync-check.py --add --repo URL --path P          # Fetch upstream plugin
uv run scripts/sync-check.py --import-skill --repo URL --path P  # Import raw skill
#   Add --dry-run to validate without modifying files
#   Add --skip-scan to bypass semgrep gate
#   Add --force to ignore malformed SKILL.md frontmatter

# Sync checking
uv run scripts/sync-check.py                              # Check all
uv run scripts/sync-check.py --diff --plugin NAME         # Full diff for one
uv run scripts/sync-check.py --mark-synced --plugin NAME  # Record sync

# Verification
uv run scripts/sync-check.py --pending                     # List unverified
uv run scripts/sync-check.py --scan                        # Semgrep scan unverified
uv run scripts/sync-check.py --mark-verified --plugin NAME  # Approve after review
```
