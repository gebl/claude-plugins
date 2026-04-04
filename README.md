# Anvil Plugin Registry

A harness-agnostic registry that pulls skills, commands, agents, and hooks from the open-source ecosystem, catalogs them with compatibility metadata, and generates harness-specific outputs for **Claude Code**, **Codex**, and **GitHub Copilot CLI**.

## How It Works

```
Upstream Repos                Neutral Catalog              Harness Outputs
(GitHub, Forgejo)             (catalog/)                   (generated/)
                                                          
  trailofbits/skills ──┐                                  ┌─ Claude Code
  garrytan/gstack ─────┤     ┌──────────────────┐         │   marketplace.json
  mattpocock/skills ───┤────>│  Package records  │────────>│   19 plugins
  conorbronsdon/* ─────┤     │  Portability class │        │
  ComposioHQ/* ────────┤     │  Risk assessment  │        ├─ Codex
  Internal repos ──────┘     │  Capability map   │────────>│   marketplace.json
                              └──────────────────┘         │   generated + syncable
                                                           ├─ Copilot CLI
                                                           │   skills/ + syncable
                                                           └─ (future harnesses)
```

1. **Import** -- Plugins and raw skills are pulled from upstream repositories, scanned with Semgrep, and mirrored byte-for-byte into `plugins-claude/` (or `plugins-codex/` / `plugins-copilot/` for non-Claude-native skills).
2. **Catalog** -- Each package gets a neutral record in `catalog/packages/` with portability classification, risk assessment, and compatibility findings.
3. **Generate** -- The catalog renders harness-specific output artifacts. Agnostic packages pass through unchanged. Adaptable packages get shallow transforms (tool name mapping, manifest rewriting, frontmatter normalization). Harness-specific packages are included only where they work natively.

## Registry

### Full Package List

| Plugin | Version | Components | Source | Portability |
|--------|---------|------------|--------|-------------|
| [ask-questions-if-underspecified](#ask-questions-if-underspecified) | 1.0.1 | skill | [trailofbits/skills](https://github.com/trailofbits/skills) | Agnostic |
| [avoid-ai-writing](#avoid-ai-writing) | 3.2.0 | skill | [conorbronsdon/avoid-ai-writing](https://github.com/conorbronsdon/avoid-ai-writing) | Agnostic |
| [careful](#careful) | 0.1.0 | skill | [garrytan/gstack](https://github.com/garrytan/gstack) | Harness-specific |
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

| Plugin | Claude Code | Codex | Copilot CLI | Why |
|--------|:-----------:|:-----:|:-----------:|-----|
| ask-questions-if-underspecified | native | generated | generated | Pure markdown, no tool bindings |
| avoid-ai-writing | native | generated | generated | Pure markdown skill with no runtime tool requirements |
| careful | native | unsupported | unsupported | Inline hooks/frontmatter and command interception are harness-specific |
| claude-vis | native | unsupported | unsupported | Hook lifecycle, commands, and Python scripts |
| devcontainer-setup | native | unsupported | unsupported | `~/.claude` paths and executable scripts |
| differential-review | native | unsupported | unsupported | Complex multi-tool workflow tied to Claude conventions |
| file-organizer | native | generated | generated | Pure markdown, no tool bindings |
| git-cleanup | native | adapted | adapted | Tool names remapped to documented Codex and Copilot tools |
| grill-me | native | generated | generated | Pure markdown, no tool bindings |
| insecure-defaults | native | adapted | adapted | Tool names remapped to documented Codex and Copilot tools |
| investigate | native | unsupported | unsupported | Interactive multi-phase workflow |
| modern-python | native | unsupported | unsupported | Hook lifecycle and PATH shim scripts |
| office-hours | native | unsupported | unsupported | Interactive brainstorm workflow |
| review | native | unsupported | unsupported | Complex multi-tool workflow |
| semgrep-rule-creator | native | blocked | blocked | Semgrep dependency and runtime/tooling assumptions |
| ship | native | unsupported | unsupported | Hook lifecycle and interactive release steps |
| variant-analysis | native | adapted | adapted | Tool names remapped; skill body and bundled resources are portable |
| workflow-skill-design | native | blocked | blocked | Teaching tool with agent definitions |
| yt-transcript | native | adapted | adapted | Helper script is copied into the skill directory and invocation is normalized |

**Legend:**
- **native** -- runs as-is, no transforms needed
- **generated** -- auto-generated from neutral catalog (pure markdown skills)
- **adapted** -- transformed with shallow compatibility layer (tool name mapping, manifest rewriting)
- **blocked** -- intentionally excluded (dependencies or features that don't translate)
- **--** -- harness-specific, no adaptation possible (hooks, complex interactive workflows)

**Summary:** Claude Code exposes all 19 packages. Codex and Copilot CLI are both generated from the neutral catalog, synced into their repo-local install paths, and validated as first-class harness outputs in this repository.

### Portability Classes

| Class | Count | Meaning |
|-------|:-----:|---------|
| **Agnostic** | 4 | Pure markdown skills with no harness bindings. Work everywhere unchanged. |
| **Adaptable** | 6 | Use harness-specific tool names or conventions that can be mechanically remapped. |
| **Harness-specific** | 9 | Depend on hook lifecycles, home directory paths, or interactive workflows unique to one harness. |

### Capability Mappings

When adapting plugins between harnesses, these tool equivalences are used:

| Capability | Claude Code | Codex | Copilot CLI | Status |
|------------|-------------|-------|-------------|--------|
| Read files | `Read` | `read_file` | `view` | Exact |
| Search files | `Grep`, `Glob` | `grep_search`, `file_search` | `grep`, `glob` | Exact |
| Edit files | `Edit`, `Write` | `edit_file`, `write_file` | `edit`, `create` | Approximate |
| Run shell | `Bash` | `shell` | `bash` | Exact |
| Browse web | `WebSearch`, `WebFetch` | -- | `web_fetch` | Unsupported in this registry |
| Ask user | `AskUserQuestion` | `assistant_message` | `ask_user` | Lossy |
| Spawn subagent | `Agent` | `spawn_agent` | `task` | Approximate |

### Plugin Details

#### ask-questions-if-underspecified
Clarify ambiguous requirements by asking questions before implementing. Pure markdown skill -- no executable code.

#### avoid-ai-writing
Audit and rewrite content to remove AI writing patterns ("AI-isms"). Generated unchanged for Codex and Copilot.

#### careful
Safety guardrail that intercepts destructive bash commands (`rm -rf`, `DROP TABLE`, force push). Claude-only because it depends on inline hooks/frontmatter plus executable command-interception scripts.

#### claude-vis
Logs session activity, token usage, and cost to SQLite for analytics. Includes `/stats` command, Python hook scripts for `SessionStart`, `PostToolUse`, `Stop`, and `SessionEnd`. Claude Code only due to hook lifecycle dependency.

#### devcontainer-setup
Create pre-configured devcontainers with Claude Code and language-specific tooling. Claude Code only due to `~/.claude` path references and executable scripts.

#### differential-review
Security-focused differential review of code changes with blast radius estimation. Includes `/diff-review` command. Claude Code only due to complex multi-tool workflow.

#### file-organizer
Intelligently organizes files and folders -- finds duplicates, suggests structures, automates cleanup. Pure markdown skill.

#### git-cleanup
Safely analyzes and cleans up local git branches and worktrees. Tool references remapped for Codex and Copilot.

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
Create custom Semgrep rules for detecting bugs and security vulnerabilities. Includes `/semgrep-rule` command. Blocked on Codex and Copilot due to Semgrep dependency and runtime assumptions.

#### ship
Automates pre-merge workflow: tests, review, version bump, changelog, PR creation. Claude Code only due to hook lifecycle and interactive steps.

#### variant-analysis
Find similar vulnerabilities across codebases using pattern-based analysis. Includes `/variants` command. Tool references remapped for Codex and Copilot.

#### workflow-skill-design
Design patterns and review agent for workflow-based Claude Code skills. Includes `workflow-skill-reviewer` agent. Blocked on Codex and Copilot due to agent definitions.

#### yt-transcript
Fetch YouTube video transcripts and save as Markdown. Tool references remapped for Codex and Copilot, with the helper script copied into the generated skill directory.

## Setup

### Python Tooling

This repo now has a root `pyproject.toml`, so you can install the registry tooling once and use console scripts instead of `uv run <script.py>`:

```bash
uv sync
source .venv/bin/activate
```

That gives you commands such as:

- `anvil-generate-codex`
- `anvil-sync-codex`
- `anvil-generate-copilot`
- `anvil-sync-copilot`
- `anvil-catalog`
- `anvil-assess-package`

If you do not want to activate the environment, you can call the installed entry points directly from `.venv/bin/`.

### Claude Code

Add the marketplace:

```
/plugin marketplace add git@<HOSTNAME>:Anvil/claude-plugins.git
```

Browse and install plugins with `/plugin`. All 19 plugins are available.

### Codex

Codex reads a repo-local marketplace from `.agents/plugins/marketplace.json`, and each installed plugin needs its own `.codex-plugin/plugin.json`.

This repo treats Codex setup as a two-step flow:

1. Generate Codex artifacts from the neutral catalog:

```bash
anvil-generate-codex
```

This writes:

- `generated/codex/marketplace.json`
- `generated/codex/plugins/<name>/.codex-plugin/plugin.json`
- transformed `skills/` trees for adapted plugins

2. Sync the generated artifacts into Codex's repo-local path:

```bash
anvil-sync-codex
```

This writes:

- `.agents/plugins/marketplace.json`
- `.agents/plugins/plugins/<name>/...`

If you want the repo-local Codex plugin tree to exactly match the generated marketplace, remove stale plugin directories during sync:

```bash
anvil-sync-codex --clean
```

The generated marketplace uses local relative paths like `./plugins/<name>`, so the sync step preserves that layout under `.agents/plugins/`.

If `/plugins` in Codex shows marketplace entries but the detail view fails with messages such as `Failed to load plugin details` or `plugin/read failed in TUI`, the repo-local plugin tree is usually under-populated. The common cause is having `.agents/plugins/marketplace.json` without the corresponding `.agents/plugins/plugins/<name>/.codex-plugin/plugin.json` files. Re-run:

```bash
anvil-sync-codex --clean
```

Then reopen `/plugins`. If Codex cached the earlier broken state, restart the session once.

For one-shot local setup:

```bash
anvil-generate-codex && anvil-sync-codex --clean
```

### Copilot CLI

GitHub Copilot CLI skills are generated as skill directories, not plugin manifests.

1. Generate Copilot skill outputs from the neutral catalog:

```bash
anvil-generate-copilot
```

This writes:

- `generated/copilot/skills/<name>/SKILL.md`
- copied skill-local resources for enabled packages

2. Sync the generated skills into the default repo-local Copilot discovery path:

```bash
anvil-sync-copilot --clean
```

This writes:

- `.github/skills/<name>/...`
- `.github/skills/.anvil-managed.json`

This installs the full Copilot-ready set currently supported by the catalog:

- `ask-questions-if-underspecified`
- `avoid-ai-writing`
- `file-organizer`
- `git-cleanup`
- `grill-me`
- `insecure-defaults`
- `variant-analysis`
- `yt-transcript`

Copilot reads project skills from `.github/skills/` or `.claude/skills/`, and personal skills from paths such as `~/.copilot/skills/` or `~/.claude/skills/`. This repo generates skill directories under `generated/copilot/skills/` and syncs them into `.github/skills/` by default. The sync command writes `.github/skills/.anvil-managed.json` so `--clean` only removes Anvil-managed skills and leaves unrelated custom skills alone.

If you want a user-level install instead of a project-level one:

```bash
anvil-sync-copilot --user --clean
```

That installs the same generated skills into `~/.copilot/skills/`.

### Copilot CLI Smoke Test

Use this flow to verify the generated Copilot skills behave as expected:

```bash
anvil-generate-copilot
anvil-sync-copilot --clean
```

Then in Copilot CLI:

1. Run `/skills list` and confirm the generated skills appear.
2. Run `/skills info` and confirm the installed path points at `.github/skills/...` for project installs, or `~/.copilot/skills/...` for `--user` installs.
3. Invoke a specific skill by name, for example `/grill-me` or `/git-cleanup`.
4. If Copilot reports `missing or malformed YAML frontmatter`, inspect the installed `SKILL.md` and ensure it starts with:

```yaml
---
name: skill-name
description: Short description
---
```

### Optional: Semgrep

Install semgrep for automatic security scanning during imports:

```bash
uv tool install semgrep
```

## Adding Plugins

All imports are automatically scanned with semgrep before anything is written to disk. If findings are detected, the import is blocked. Use `--dry-run` to validate without modifying files, or `--skip-scan` to bypass the scan.

### From an upstream plugin repo

Fetches the plugin, scans it with semgrep, copies it into `plugins-claude/`, and registers it in both `marketplace.json` and `sources.json`:

```bash
anvil-sync-check --add \
  --repo https://github.com/org/repo.git \
  --path plugins/plugin-name
```

The plugin name is inferred from `--path` (here: `plugin-name`). Use `--name` to override. Then commit and push.

### From a raw skill repo

For repos with standalone `SKILL.md` files without plugin packaging (e.g., ComposioHQ/awesome-claude-skills). This auto-generates the plugin wrapper, copies all files, and registers everything:

```bash
anvil-sync-check --import-skill \
  --repo https://github.com/org/repo.git \
  --path skill-name
```

Use `--force` if the `SKILL.md` frontmatter is malformed or missing required fields.

### Creating your own plugin

1. Create the directory structure:

```bash
mkdir -p plugins-claude/my-plugin/.claude-plugin
mkdir -p plugins-claude/my-plugin/skills/my-skill
```

2. Add `plugins-claude/my-plugin/.claude-plugin/plugin.json`:

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

To include a package in generated harness outputs, add per-harness metadata under `generation.<harness>` in `catalog/packages/<name>.json`. Codex uses marketplace fields such as `policy` and `category`; Copilot uses install metadata such as `target_dir` and currently syncs to `.github/skills` by default.

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
anvil-sync-check                # All tracked plugins
anvil-sync-check --plugin NAME   # One plugin
anvil-sync-check --diff          # Include full diffs
```

| Status | Meaning | Action |
|--------|---------|--------|
| `up-to-date` | No changes | Nothing to do |
| `upstream-changed` | Upstream has new commits | Safe to pull |
| `local-modified` | Local changes only | Upstream unchanged |
| `both-changed` | Both sides diverged | Manual merge needed |

After merging upstream changes, update the baseline:

```bash
anvil-sync-check --mark-synced --plugin NAME
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
anvil-sync-check --pending

# Run semgrep security scan (auto + p/secrets + p/trailofbits rulesets)
anvil-sync-check --scan
anvil-sync-check --scan --plugin NAME

# Mark all skills in a plugin as reviewed after inspection
anvil-sync-check --mark-verified --plugin NAME

# Or mark one skill inside a plugin
anvil-sync-check --mark-verified --plugin NAME --skill SKILL_NAME
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
│   ├── codex/marketplace.json   # Generated Codex marketplace
│   └── copilot/skills/          # Generated Copilot CLI skills
├── .agents/
│   ├── plugins/                 # Repo-local Codex install tree
│   └── skills/                  # Repo-local Copilot CLI install tree
├── sources.json               # Upstream provenance tracking
├── scripts/
│   └── sync-check.py          # Plugin management CLI
├── docs/plans/                # Design documents
└── plugins-claude/              # 19 plugin directories (byte-for-byte upstream mirrors)
    └── <plugin-name>/
        ├── .claude-plugin/
        │   └── plugin.json
        ├── skills/
        ├── agents/
        ├── commands/
        └── hooks/
```

Codex- and Copilot-native skills live in `plugins-codex/` and `plugins-copilot/` respectively.

## Quick Reference

```bash
# Importing (name inferred from --path, override with --name)
anvil-sync-check --add --repo URL --path P          # Fetch upstream plugin
anvil-sync-check --import-skill --repo URL --path P  # Import raw skill
#   Add --dry-run to validate without modifying files
#   Add --skip-scan to bypass semgrep gate
#   Add --force to ignore malformed SKILL.md frontmatter

# Sync checking
anvil-sync-check                              # Check all
anvil-sync-check --diff --plugin NAME         # Full diff for one
anvil-sync-check --mark-synced --plugin NAME  # Record sync

# Verification
anvil-sync-check --pending                       # List unverified skills
anvil-sync-check --scan                          # Semgrep scan plugins with unverified skills
anvil-sync-check --mark-verified --plugin NAME   # Approve all skills in a plugin
anvil-sync-check --mark-verified --plugin NAME --skill SKILL_NAME
```
