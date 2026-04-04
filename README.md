# Anvil Plugin Registry

A harness-agnostic plugin registry that pulls skills, commands, agents, and hooks from the open-source ecosystem, catalogs them with compatibility metadata, and generates installable marketplaces for both **Claude Code** and **Codex**.

## How It Works

```
Upstream Repos                Neutral Catalog              Harness Marketplaces
(GitHub, Forgejo)             (catalog/)                   (generated/)
                                                          
  trailofbits/skills ──┐                                  ┌─ Claude Code
  garrytan/gstack ─────┤     ┌──────────────────┐         │   marketplace.json
  mattpocock/skills ───┤────>│  Package records  │────────>│   19 plugins
  conorbronsdon/* ─────┤     │  Portability class │        │
  ComposioHQ/* ────────┤     │  Risk assessment  │        ├─ Codex
  Internal repos ──────┘     │  Capability map   │────────>│   marketplace.json
                              └──────────────────┘         │   10 plugins
                                                           └─ (future harnesses)
```

1. **Import** -- Plugins and raw skills are pulled from upstream repositories, scanned with Semgrep, and mirrored byte-for-byte into `plugins/`.
2. **Catalog** -- Each package gets a neutral record in `catalog/packages/` with portability classification, risk assessment, and compatibility findings.
3. **Generate** -- The catalog renders harness-specific marketplace files. Agnostic packages pass through unchanged. Adaptable packages get shallow transforms (tool name mapping, manifest rewriting). Harness-specific packages are included only where they work natively.

## Registry

### Full Package List

| Plugin | Version | Components | Source | Portability |
|--------|---------|------------|--------|-------------|
| [ask-questions-if-underspecified](#ask-questions-if-underspecified) | 1.0.1 | skill | [trailofbits/skills](https://github.com/trailofbits/skills) | Agnostic |
| [avoid-ai-writing](#avoid-ai-writing) | 3.2.0 | skill | [conorbronsdon/avoid-ai-writing](https://github.com/conorbronsdon/avoid-ai-writing) | Adaptable |
| [careful](#careful) | 0.1.0 | skill | [garrytan/gstack](https://github.com/garrytan/gstack) | Adaptable |
| [claude-vis](#claude-vis) | 0.1.0 | skill, command, hooks | Internal | Harness-specific |
| [devcontainer-setup](#devcontainer-setup) | 0.1.0 | skill | [trailofbits/skills](https://github.com/trailofbits/skills) | Harness-specific |
| [differential-review](#differential-review) | 1.0.0 | skill, command | [trailofbits/skills](https://github.com/trailofbits/skills) | Harness-specific |
| [file-organizer](#file-organizer) | 0.1.0 | skill | [ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills) | Agnostic |
| [git-cleanup](#git-cleanup) | 1.0.0 | skill | [trailofbits/skills](https://github.com/trailofbits/skills) | Adaptable |
| [grill-me](#grill-me) | 0.1.0 | skill | [mattpocock/skills](https://github.com/mattpocock/skills) | Agnostic |
| [insecure-defaults](#insecure-defaults) | 1.0.0 | skill | [trailofbits/skills](https://github.com/trailofbits/skills) | Adaptable |
| [investigate](#investigate) | 1.0.0 | skill | [garrytan/gstack](https://github.com/garrytan/gstack) | Harness-specific |
| [modern-python](#modern-python) | 1.5.0 | skill, hooks | [trailofbits/skills](https://github.com/trailofbits/skills) | Harness-specific |
| [office-hours](#office-hours) | 2.0.0 | skill | [garrytan/gstack](https://github.com/garrytan/gstack) | Harness-specific |
| [review](#review) | 1.0.0 | skill | [garrytan/gstack](https://github.com/garrytan/gstack) | Harness-specific |
| [semgrep-rule-creator](#semgrep-rule-creator) | 1.2.0 | skill, command | [trailofbits/skills](https://github.com/trailofbits/skills) | Adaptable |
| [ship](#ship) | 1.0.0 | skill | [garrytan/gstack](https://github.com/garrytan/gstack) | Harness-specific |
| [variant-analysis](#variant-analysis) | 1.0.0 | skill, command | [trailofbits/skills](https://github.com/trailofbits/skills) | Adaptable |
| [workflow-skill-design](#workflow-skill-design) | 1.0.1 | skill, agent | [trailofbits/skills](https://github.com/trailofbits/skills) | Adaptable |
| [yt-transcript](#yt-transcript) | 0.1.0 | skill | Internal | Adaptable |

### Harness Compatibility Matrix

Each package is classified by how well it travels between harnesses:

| Plugin | Claude Code | Codex | Why |
|--------|:-----------:|:-----:|-----|
| ask-questions-if-underspecified | native | generated | Pure markdown, no tool bindings |
| avoid-ai-writing | native | adapted | Tool names remapped |
| careful | native | adapted | Tool names remapped |
| claude-vis | native | -- | Hook lifecycle + Python scripts |
| devcontainer-setup | native | -- | `~/.claude` paths, executable scripts |
| differential-review | native | -- | Complex multi-tool workflow |
| file-organizer | native | generated | Pure markdown, no tool bindings |
| git-cleanup | native | adapted | Tool names remapped |
| grill-me | native | generated | Pure markdown, no tool bindings |
| insecure-defaults | native | adapted | Bash tool remapped to shell |
| investigate | native | -- | Interactive multi-phase workflow |
| modern-python | native | -- | Hook lifecycle + PATH shim scripts |
| office-hours | native | -- | Interactive brainstorm workflow |
| review | native | -- | Complex multi-tool workflow |
| semgrep-rule-creator | native | blocked | Semgrep dependencies, tool mappings |
| ship | native | -- | Hook lifecycle + interactive steps |
| variant-analysis | native | adapted | Tool names remapped |
| workflow-skill-design | native | blocked | Teaching tool, agent definitions |
| yt-transcript | native | adapted | Tool names remapped |

**Legend:**
- **native** -- runs as-is, no transforms needed
- **generated** -- auto-generated from neutral catalog (pure markdown skills)
- **adapted** -- transformed with shallow compatibility layer (tool name mapping, manifest rewriting)
- **blocked** -- intentionally excluded (dependencies or features that don't translate)
- **--** -- harness-specific, no adaptation possible (hooks, complex interactive workflows)

**Summary:** 19 for Claude Code, 10 for Codex (3 generated + 5 adapted + 2 blocked = 10 attempted, 8 usable).

### Portability Classes

| Class | Count | Meaning |
|-------|:-----:|---------|
| **Agnostic** | 3 | Pure markdown skills with no harness bindings. Work everywhere unchanged. |
| **Adaptable** | 8 | Use harness-specific tool names or conventions that can be mechanically remapped. |
| **Harness-specific** | 8 | Depend on hook lifecycles, home directory paths, or interactive workflows unique to one harness. |

### Capability Mappings

When adapting plugins between harnesses, these tool equivalences are used:

| Capability | Claude Code | Codex | Status |
|------------|-------------|-------|--------|
| Read files | `Read` | `read_file` | Exact |
| Search files | `Grep`, `Glob` | `grep_search`, `file_search` | Exact |
| Edit files | `Edit`, `Write` | `edit_file`, `write_file` | Exact |
| Run shell | `Bash` | `shell` | Exact |
| Browse web | `WebSearch`, `WebFetch` | -- | Unsupported in Codex |
| Ask user | `AskUserQuestion` | `assistant_message` | Lossy (degrades to plain text) |
| Spawn subagent | `Agent` | `spawn_agent` | Approximate |

### Plugin Details

#### ask-questions-if-underspecified
Clarify ambiguous requirements by asking questions before implementing. Pure markdown skill -- no executable code.

#### avoid-ai-writing
Audit and rewrite content to remove AI writing patterns ("AI-isms"). Tool references remapped for Codex.

#### careful
Safety guardrail that intercepts destructive bash commands (`rm -rf`, `DROP TABLE`, force push). Contains executable scripts for command interception.

#### claude-vis
Logs session activity, token usage, and cost to SQLite for analytics. Includes `/stats` command, Python hook scripts for `SessionStart`, `PostToolUse`, `Stop`, and `SessionEnd`. Claude Code only due to hook lifecycle dependency.

#### devcontainer-setup
Create pre-configured devcontainers with Claude Code and language-specific tooling. Claude Code only due to `~/.claude` path references and executable scripts.

#### differential-review
Security-focused differential review of code changes with blast radius estimation. Includes `/diff-review` command. Claude Code only due to complex multi-tool workflow.

#### file-organizer
Intelligently organizes files and folders -- finds duplicates, suggests structures, automates cleanup. Pure markdown skill.

#### git-cleanup
Safely analyzes and cleans up local git branches and worktrees. Tool references remapped for Codex.

#### grill-me
Stress-test a plan or design through relentless questioning until reaching shared understanding. Pure markdown skill.

#### insecure-defaults
Detects insecure default configurations: hardcoded credentials, weak authentication, permissive security settings.

#### investigate
Systematic root-cause debugging with four phases: investigate, analyze, hypothesize, implement. Enforces evidence gathering before touching code. Claude Code only due to interactive multi-phase workflow.

#### modern-python
Modern Python best practices with uv, ruff, and ty. Includes `SessionStart` hook for PATH shim setup. Claude Code only.

#### office-hours
Two modes: startup validation (six forcing questions) and builder mode (design thinking brainstorming). Claude Code only due to interactive workflow.

#### review
Pre-landing PR review for structural issues, SQL safety, race conditions, and scope drift. Claude Code only.

#### semgrep-rule-creator
Create custom Semgrep rules for detecting bugs and security vulnerabilities. Includes `/semgrep-rule` command. Blocked on Codex due to Semgrep dependency requirements.

#### ship
Automates pre-merge workflow: tests, review, version bump, changelog, PR creation. Claude Code only due to hook lifecycle and interactive steps.

#### variant-analysis
Find similar vulnerabilities across codebases using pattern-based analysis. Includes `/variants` command. Tool references remapped for Codex.

#### workflow-skill-design
Design patterns and review agent for workflow-based Claude Code skills. Includes `workflow-skill-reviewer` agent. Blocked on Codex due to agent definitions.

#### yt-transcript
Fetch YouTube video transcripts and save as Markdown. Tool references remapped for Codex.

## Setup

### Claude Code

Add the marketplace:

```
/plugin marketplace add git@<HOSTNAME>:Anvil/claude-plugins.git
```

Browse and install plugins with `/plugin`. All 19 plugins are available.

### Codex

The generated Codex marketplace is at `generated/codex/marketplace.json` with 10 compatible plugins. Codex plugin manifests are generated under `generated/codex/plugins/`.

### Optional: Semgrep

Install semgrep for automatic security scanning during imports:

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

Locally-authored plugins don't need a `sources.json` entry -- that's only for upstream forks.

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

Imported skills start unverified. The recommended workflow:

```
1. --pending        List what skills need review
2. --scan           Run semgrep on plugins with unverified skills
3. Review code      Read the findings and source
4. --mark-verified  Mark one skill or all skills in a plugin as reviewed
```

```bash
# List unverified skills (rescans for executable code)
uv run scripts/sync-check.py --pending

# Run semgrep security scan (auto + p/secrets + p/trailofbits rulesets)
uv run scripts/sync-check.py --scan
uv run scripts/sync-check.py --scan --plugin NAME

# Mark all skills in a plugin as reviewed after inspection
uv run scripts/sync-check.py --mark-verified --plugin NAME

# Or mark one skill inside a plugin
uv run scripts/sync-check.py --mark-verified --plugin NAME --skill SKILL_NAME
```

## Repository Structure

```
claude-plugins/
├── .claude-plugin/
│   └── marketplace.json       # Claude Code marketplace (what the harness reads)
├── catalog/
│   ├── catalog.json           # Top-level catalog metadata
│   ├── packages/              # 19 neutral package records (one JSON per plugin)
│   ├── schema/                # JSON schemas for validation
│   ├── rules/                 # Portability, harness binding, risk, and transform rules
│   └── security/suppressions/ # Semgrep finding suppressions
├── generated/
│   ├── claude/marketplace.json  # Generated Claude Code marketplace
│   └── codex/marketplace.json   # Generated Codex marketplace
├── sources.json               # Upstream provenance tracking
├── scripts/
│   └── sync-check.py          # Plugin management CLI
├── docs/plans/                # Design documents
└── plugins/                   # 19 plugin directories (byte-for-byte upstream mirrors)
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
uv run scripts/sync-check.py --pending                       # List unverified skills
uv run scripts/sync-check.py --scan                          # Semgrep scan plugins with unverified skills
uv run scripts/sync-check.py --mark-verified --plugin NAME   # Approve all skills in a plugin
uv run scripts/sync-check.py --mark-verified --plugin NAME --skill SKILL_NAME
```
