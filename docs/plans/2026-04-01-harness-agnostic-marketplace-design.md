# Harness-Agnostic Registry Design

## Goal

Evolve this repository from a Claude-native plugin marketplace into a harness-agnostic
registry that can:

1. Store neutral package metadata once
2. Import packages from upstream repos and assess compatibility during import
3. List packages by supported harness and compatibility class
4. Generate harness-specific outputs for Claude, Codex, Copilot, and future
   harnesses such as Cursor

The repository should stop treating Claude's marketplace format as the source of truth.
Claude, Codex, and Copilot should each be rendered as harness-specific outputs from
the same neutral catalog.

## Problem Statement

The current repository already has valuable provenance and intake machinery:

- `.claude-plugin/marketplace.json` defines a central registry of installable plugins
- `sources.json` tracks upstream provenance, sync state, executable code presence, and
  verification status
- `scripts/sync-check.py` imports either packaged plugins or raw `SKILL.md` repositories
  and applies a security gate before writing to disk

That is a strong base for a package catalog. The main limitation is that the metadata
model and packaging assumptions are Claude-specific:

- The root marketplace file is tied to Claude's schema
- Plugin manifests are stored as `.claude-plugin/plugin.json`
- Hook support assumes Claude lifecycle events
- Skills often contain Claude-specific tool names, file paths, and behavior

As a result, the repository can ingest useful content, but it could not originally answer:

- Which packages are harness-agnostic?
- Which packages support Codex?
- Which packages support Copilot CLI?
- Which packages can be adapted automatically?
- Which packages are Claude-only?

Codex's concrete marketplace and packaging contract is now known from the official
OpenAI docs:

- Codex reads repo marketplaces from `$REPO_ROOT/.agents/plugins/marketplace.json`
  and personal marketplaces from `~/.agents/plugins/marketplace.json`
- A Codex marketplace is a JSON catalog with top-level marketplace metadata and one
  object per plugin under `plugins[]`
- Each plugin entry includes `name`, `source`, `policy`, and `category`
- Local plugin entries typically point `source.path` at `./plugins/<name>`
- Every Codex plugin requires a manifest at `.codex-plugin/plugin.json`
- Codex plugins may additionally bundle `skills/`, `.app.json`, `.mcp.json`, and
  `assets/` at the plugin root

GitHub Copilot CLI's concrete skill packaging contract is now known from the official
GitHub docs:

- Copilot discovers skills from repo-local paths such as `.agents/skills/`,
  `.github/skills/`, and `.claude/skills/`
- Personal skills can also live under `~/.agents/skills/`, `~/.copilot/skills/`, or
  `~/.claude/skills/`
- Each Copilot skill is a directory containing a `SKILL.md` file with YAML frontmatter
- `name` and `description` are required frontmatter fields
- `allowed-tools` and additional scripts or resources may be colocated in the skill
  directory

This removes the earlier uncertainty around whether Codex and Copilot had concrete
runtime surfaces. They do. The remaining work is compatibility modeling and generation.

One more distinction is required for import-time metadata: not every harness feature
should be treated as equally authoritative.

The catalog should distinguish support that is:

- `official`
  - backed by official harness documentation
- `adapter`
  - supported through our own neutral-to-harness transforms
- `convention`
  - observed in a runtime or repository convention, but not confirmed in official docs
- `unknown`
  - not yet validated

This is especially important for Claude. Claude's public docs clearly document hooks,
settings, MCP, subagents, and slash commands, but they do not currently provide the
same official plugin marketplace/package spec that Codex does. Until such docs are
confirmed, `.claude-plugin/plugin.json` and the current Claude marketplace file should be
tracked as repository/runtime conventions rather than official Claude contracts.

## Design Principles

### 1. Separate catalog from renderers

Keep one neutral catalog as the source of truth. Treat Claude, Codex, and future
harnesses as output renderers over that catalog.

### 2. Keep adaptation shallow in this repository

Do not reduce compatibility to a boolean. Many packages will not be fully agnostic but
can still be adapted safely. However, this repository should only perform shallow,
deterministic cross-harness transforms. Deeper semantic rewrites should live in
separate fork repositories.

### 3. Make assessment explicit and explainable

Compatibility decisions should come from structured findings recorded during import, not
 opaque heuristics.

### 4. Be conservative when generating outputs

If support for a harness is unclear, do not generate an entry for that harness.
Prefer omission plus an actionable compatibility report over shipping broken packages.

### 5. Keep provenance and security first-class

The current provenance and executable-code tracking should remain core parts of the
system rather than being bolted on later.

### 6. Do not hide forks as transforms

If making a package work on another harness requires workflow rewrites, runtime-specific
behavior changes, hook redesign, or repeated manual reconciliation with upstream, that
package is no longer a simple transform target. It should become a separately maintained
fork repository and be imported here as its own package.

### 7. Keep imported source files identical to upstream

Imported upstream mirrors should remain byte-for-byte identical to their source
repositories whenever possible. Local security exceptions such as Semgrep suppressions
must not be expressed by editing imported files. They should be stored as repository-
owned suppression metadata outside the mirror.

## Proposed Repository Layout

Introduce neutral catalog files and generated outputs:

```text
claude-plugins/
├── catalog/
│   ├── catalog.json
│   ├── packages/
│   │   └── <package-name>.json
│   ├── indexes/
│   │   ├── by-name.json
│   │   ├── by-harness.json
│   │   └── by-portability.json
│   ├── security/
│   │   └── suppressions/
│   │       └── <package-name>.json
│   ├── schema/
│   │   ├── package.schema.json
│   │   ├── catalog.schema.json
│   │   └── compatibility.schema.json
│   └── rules/
│       ├── portability-rules.json
│       ├── harness-claude.json
│       ├── harness-codex.json
│       ├── risk-rules.json
│       └── transforms.json
├── generated/
│   ├── claude/
│   │   └── marketplace.json
│   └── codex/
│       ├── marketplace.json
│       └── plugins/
│           └── <plugin-name>/
├── plugins/
│   └── <plugin-name>/
├── scripts/
│   ├── sync-check.py
│   ├── assess-package.py
│   └── generate-marketplace.py
└── .claude-plugin/
    └── marketplace.json
```

During migration, `.claude-plugin/marketplace.json` remains present for compatibility,
but it becomes generated from the neutral catalog.

For Codex, the generated targets should align with the documented repo-marketplace path
and plugin package shape:

- repo marketplace target: `$REPO_ROOT/.agents/plugins/marketplace.json`
- personal marketplace target: `~/.agents/plugins/marketplace.json`
- plugin manifest target: `.codex-plugin/plugin.json` under each plugin root

## Source of Truth

The new source of truth is the neutral catalog under `catalog/`.

Recommended layout:

- `catalog/catalog.json`
  - top-level catalog metadata including schema version
- `catalog/packages/<name>.json`
  - one package record per file
- `catalog/indexes/*.json`
  - generated indexes for listing and filtering

This keeps package diffs reviewable, makes `git blame` meaningful, and reduces merge
conflicts when multiple packages change in parallel.

Indexes should be generated artifacts, not hand-edited source files.

Recommended behavior:

- build or refresh indexes whenever package records change
- commit them if they materially improve repository browsing and review ergonomics
- treat them as derived from `catalog/packages/*.json`

Suggested initial rule:

- package records are source of truth
- indexes are regenerated during import and catalog update commands

Each package entry should describe:

- Identity
- Provenance
- Source relationship model
- Package contents
- Risk signals
- Compatibility assessment
- Harness-specific generation state

Suggested shape for `catalog/packages/review.json`:

```json
{
  "name": "review",
  "version": "1.0.0",
  "description": "Pre-landing PR review",
  "authors": [
    {
      "name": "Garry Tan"
    }
  ],
  "upstream": {
    "repo": "https://github.com/garrytan/gstack.git",
    "path": "review",
    "ref": "main",
    "type": "raw-skill",
    "last_synced_commit": "<sha>",
    "last_checked": "2026-04-01T00:00:00Z"
  },
  "package_type": "skill-wrapper",
  "files": {
    "has_skill": true,
    "has_plugin_manifest": true,
    "has_hooks": false,
    "has_commands": false,
    "has_agents": false,
    "has_templates": true
  },
  "risk": {
    "has_executable_code": false,
    "dependency_files": [],
    "tool_risk": {
      "declared_tools": ["Bash", "Write", "Edit"],
      "risk_level": "medium",
      "reasons": ["workspace mutation", "shell execution"]
    }
  },
  "compatibility": {
    "assessment_version": "2026-04-01.1",
    "portability_class": "harness-specific",
    "supported_harnesses": ["claude"],
    "support_basis": {
      "claude": "convention",
      "codex": "unsupported"
    },
    "status_by_harness": {
      "claude": "native",
      "codex": "unsupported"
    },
    "findings": [
      {
        "code": "CLAUDE_HOME_PATH",
        "severity": "error",
        "path": "plugins/review/skills/review/SKILL.md",
        "message": "References ~/.claude paths"
      }
    ],
    "adaptation_hints": [
      "Replace Claude-specific paths and tool names"
    ]
  },
  "generation": {
    "claude": {
      "enabled": true,
      "mode": "native"
    },
    "codex": {
      "enabled": false,
      "mode": "none",
      "marketplace": {
        "policy": {
          "installation": "AVAILABLE",
          "authentication": "ON_INSTALL"
        },
        "category": "Developer Tools"
      }
    }
  },
  "verification": {
    "reviewed": false,
    "skills": {
      "review": false
    }
  }
}
```

Suggested shape for `catalog/catalog.json`:

```json
{
  "catalog_schema_version": "1.0.0",
  "generated_at": "2026-04-01T00:00:00Z",
  "package_count": 18,
  "supported_harnesses": ["claude", "codex"]
}
```

Additional source relationship fields should distinguish direct upstream mirrors from
adapted fork repositories:

```json
{
  "name": "review-codex",
  "source_model": "adapted-fork",
  "canonical_harness": "codex",
  "fork_of": {
    "package": "review",
    "repo": "https://github.com/garrytan/gstack.git",
    "path": "review"
  }
}
```

## Compatibility Model

### Portability Classes

Use explicit classes rather than a single `portable` boolean.

- `agnostic`
  - Package content is harness-neutral and can be rendered directly into multiple
    harnesses without semantic changes
- `adaptable`
  - Package is mostly portable, but requires a deterministic transform for one or more
    harnesses
- `harness-specific`
  - Package depends on runtime features or assumptions specific to a single harness
- `unknown`
  - Assessment could not classify the package safely

### Per-Harness Status

Each harness should have its own status:

- `native`
  - The package is authored for this harness directly
- `generated`
  - The package is generated for this harness from neutral metadata
- `adapted`
  - The package is converted from another harness with explicit transforms
- `unsupported`
  - The package cannot be used on this harness
- `blocked`
  - The package may be conceptually portable but is blocked by risk or incomplete mapping
- `unknown`
  - No conclusion yet

### Support Basis

Each harness should also record why the support decision exists:

- `official`
  - backed by official harness documentation
- `adapter`
  - supported through a maintained transform or compatibility layer in this repository
- `convention`
  - supported by repository/runtime convention, but not yet confirmed in official docs
- `unsupported`
  - no support path exists
- `unknown`
  - not enough evidence yet

This should be stored alongside `status_by_harness`, not inferred later.

### Why Both Dimensions Exist

`portability_class` answers "what kind of package is this?"

`status_by_harness` answers "what do we do with it for Claude/Codex/etc.?"

Example:

- A pure markdown skill might be `agnostic`
- A markdown skill with Claude tool names might be `adaptable`
- A hook-driven plugin might be `harness-specific`

## Import-Time Assessment

Import should become a two-phase process:

1. Fetch and stage upstream content
2. Assess the staged package before writing catalog state or generated artifacts

The assessment result is stored in the catalog and surfaced to users.

### Assessment Inputs

The importer should analyze:

- File structure
- Metadata files
- `SKILL.md` frontmatter
- Hook definitions
- Command docs
- Script files
- Dependency manifests
- Runtime-specific paths and strings
- repository-owned suppression metadata

### Assessment Outputs

For every imported package, persist:

- detected package type
- detected assets
- risk flags
- compatibility class
- per-harness statuses
- per-harness support basis
- structured findings
- adaptation hints

The importer should make three passes:

1. Detect neutral components
2. Detect harness-specific bindings
3. Resolve support status plus support basis for each harness

Security scanning should follow this order:

1. scan the staged upstream content exactly as imported
2. collect raw findings
3. apply repository-owned suppressions from `catalog/security/suppressions/`
4. persist both unsuppressed findings and suppression records
5. fail import only on unsuppressed blocking findings

### Source Relationship Model

Each imported package should also be classified by source relationship:

- `upstream-mirror`
  - direct sync from an original source repository
- `adapted-fork`
  - direct sync from a separate fork repository that exists to support another harness
- `local-original`
  - authored locally in this marketplace repository

This is independent of portability class. A package can be:

- an `upstream-mirror` and `agnostic`
- an `upstream-mirror` and `harness-specific`
- an `adapted-fork` and `native` for its canonical harness

#### Adapted Forks

`adapted-fork` is a source relationship model, not a portability class.

Use it when:

- the original package is native to one harness
- a different harness needs a materially rewritten version
- that rewrite is maintained in a separate repository
- this marketplace imports both the original and the fork as distinct packages

### External Security Suppression Model

Semgrep suppressions for imported packages should be managed outside imported files.

Use per-package suppression files under:

- `catalog/security/suppressions/<package-name>.json`

These files are local policy owned by this repository. They are not part of the upstream
mirror and should never require editing imported content just to silence scanner output.

Suggested shape:

```json
{
  "package": "devcontainer-setup",
  "suppressions": [
    {
      "path": "skills/devcontainer-setup/resources/Dockerfile",
      "rule_id": "claude-pipe-to-shell",
      "reason": "Trusted installer inside container build",
      "scope": "snippet-match",
      "snippet_hash": "<stable-hash>"
    }
  ]
}
```

V1 suppressions should require a stable content-derived fingerprint such as a snippet
hash in addition to path and rule id. Do not rely on line-number-only matching in v1,
because upstream edits will cause excessive suppression churn and re-block imports.

The key design rule is that suppressions live outside imported files.

### Rule Categories

#### Packaging Rules

Determine what kind of package this is.

Examples:

- `HAS_SKILL_MD`
- `HAS_CLAUDE_PLUGIN_MANIFEST`
- `HAS_HOOKS_JSON`
- `HAS_COMMANDS_DIR`
- `HAS_AGENTS_DIR`

These rules should identify neutral components such as:

- `skill`
- `hook-config`
- `agent-definition`
- `mcp-config`
- `app-connector-config`
- `install-surface-metadata`

#### Portability Rules

Detect whether the package can travel across harnesses.

Examples:

- `PURE_MARKDOWN_SKILL_ONLY`
- `HAS_RUNTIME_SPECIFIC_HOME_PATH`
- `HAS_RUNTIME_SPECIFIC_HOOK_LIFECYCLE`
- `HAS_RUNTIME_SPECIFIC_SCHEMA_REFERENCE`

#### Harness Rules

Detect references that tie the package to Claude, Codex, or later Cursor.

Examples:

- `CLAUDE_MARKETPLACE_SCHEMA`
- `CLAUDE_HOME_PATH`
- `CLAUDE_HOOKS_JSON`
- `CLAUDE_SETTINGS_HOOKS`
- `CLAUDE_SUBAGENT_MD`
- `CLAUDE_SLASH_COMMAND_MD`
- `CLAUDE_TOOL_NAME`
- `CLAUDE_PLUGIN_CONVENTION`
- `CODEX_MARKETPLACE_FILE`
- `CODEX_PLUGIN_MANIFEST`
- `CODEX_HOOKS_JSON`
- `CODEX_AGENT_TOML`
- `CODEX_APP_JSON`
- `CODEX_MCP_JSON`
- `CODEX_TOOL_NAME`
- `CURSOR_COMMAND_CONVENTION`

#### Risk Rules

Retain and expand the current executable code and dependency checks.

Examples:

- `EXECUTABLE_CODE_PRESENT`
- `DEPENDENCY_FILE_PRESENT`
- `DANGEROUS_TOOL_DECLARATION`
- `NETWORK_SCRIPT_PRESENT`

Risk findings should distinguish:

- raw findings from the scanner
- suppressed findings covered by local policy
- unsuppressed findings that block import or verification

### Example Findings

```json
[
  {
    "code": "CLAUDE_HOOKS_JSON",
    "kind": "harness",
    "severity": "error",
    "path": "plugins/modern-python/hooks/hooks.json",
    "message": "Uses Claude hook lifecycle"
  },
  {
    "code": "CLAUDE_HOME_PATH",
    "kind": "harness",
    "severity": "error",
    "path": "plugins/review/skills/review/SKILL.md",
    "message": "References ~/.claude paths"
  },
  {
    "code": "EXECUTABLE_CODE_PRESENT",
    "kind": "risk",
    "severity": "warn",
    "path": "plugins/claude-vis/scripts/session_end.py",
    "message": "Executable code requires manual review"
  }
]
```

### Shared vs Harness-Specific Feature Inventory

The importer should classify features against a maintained inventory derived from
official docs.

#### Shared Official Concepts

These are officially documented on both Codex and Claude, and should be modeled as
neutral components:

- skills or markdown instruction bundles
- hooks
- MCP integration
- delegated agents/subagents

#### Codex-Official Features

These are officially documented Codex package/install features:

- `.codex-plugin/plugin.json`
- `.agents/plugins/marketplace.json`
- `~/.agents/plugins/marketplace.json`
- `.app.json`
- `.mcp.json`
- `.codex/hooks.json`
- `.codex/agents/*.toml`
- Codex marketplace `policy` and `category` fields

#### Claude-Official Features

These are officially documented Claude runtime/config features:

- `.claude/settings.json`
- `.claude/settings.local.json`
- hook configuration in Claude settings
- `.claude/agents/*.md`
- custom slash command markdown files
- Claude tool vocabulary

#### Convention-Only Features

These are used in this repository/runtime but should not be treated as official until
backed by official docs:

- `.claude-plugin/plugin.json`
- root Claude marketplace manifest used by this repository

The assessment engine should never silently upgrade a convention-only feature to
official. That must happen only when documentation is verified.

## Package Classification Rules

The importer should classify packages using deterministic rules.

### `agnostic`

A package can be classified as `agnostic` if all of the following are true:

- contains only neutral content such as markdown skill instructions and assets
- does not declare harness-specific hooks
- does not reference harness-specific home directories or config files
- does not rely on proprietary tool names that cannot be mapped neutrally
- has no harness-specific manifest as its only source of metadata
- all harness support claims are either `official` on both sides or `adapter` through
  explicit transforms

### `adaptable`

A package should be `adaptable` if:

- its core behavior is portable
- harness-specific concerns are limited to metadata or simple syntax
- transforms are deterministic and loss is acceptable

Examples:

- tool names can be mapped from a neutral capability set to a Codex or Claude vocabulary
- package layout can be rewritten without changing semantics
- metadata can be moved from `.claude-plugin/plugin.json` into a neutral form
- one or more target harnesses depend on `adapter` support rather than shared official
  constructs

In this repository, `adaptable` should mean shallow adaptation only:

- metadata generation
- file layout remapping
- path variable rewriting
- tool vocabulary mapping
- small wrapper file generation

If compatibility requires semantic rewrites to workflow logic, hook behavior, or
subagent/agent design, the package should not remain `adaptable` here. It should become
an `adapted-fork`.

### `harness-specific`

A package should be `harness-specific` if:

- it depends on lifecycle hooks unique to one harness
- it requires harness-owned config or directory structures
- it assumes one harness's runtime commands or marketplace contracts
- it uses installation/runtime behavior without an equivalent in the target harness
- it depends on a convention-only feature with no maintained adapter path

### `unknown`

Use only when the importer cannot classify safely. This should be rare and should
produce a visible warning.

## Neutral Capability Model

To support output generation, the catalog needs a neutral vocabulary for what a package
does, separate from harness-specific tool names.

Suggested capability families:

- `read_files`
- `search_files`
- `edit_files`
- `run_shell`
- `browse_web`
- `ask_user`
- `spawn_subagent`
- `register_hook`
- `define_command`
- `query_local_db`

This model is not a promise that every harness supports every capability. It is a way
to describe the package's needs in neutral terms.

Each harness then maps those capabilities to concrete features or marks them unsupported.

Neutral capability mapping should not be the only layer of compatibility logic. The
assessment must also capture whether a package's install surface is official, adapter-
driven, or convention-only for each harness.

### Capability Mapping Contract

The neutral capability model needs to be explicit enough that adapters do not redesign it
mid-implementation.

Each capability mapping should declare:

- `capability`
- `target_harness`
- `mapped_features`
- `mapping_mode`
- `semantic_notes`
- `status`

Where:

- `mapped_features`
  - one or more concrete features/tools in the target harness
- `mapping_mode`
  - `one_to_one`, `one_to_many`, `many_to_one`, or `unsupported`
- `semantic_notes`
  - what changes in meaning, scope, or guarantees
- `status`
  - `exact`, `approximate`, `lossy`, or `unsupported`

Example:

```json
{
  "capability": "browse_web",
  "target_harness": "claude",
  "mapped_features": ["WebSearch", "WebFetch"],
  "mapping_mode": "one_to_many",
  "semantic_notes": "neutral browse_web splits into search and direct fetch in Claude",
  "status": "approximate"
}
```

Example:

```json
{
  "capability": "ask_user",
  "target_harness": "codex",
  "mapped_features": ["assistant_message"],
  "mapping_mode": "one_to_one",
  "semantic_notes": "interactive multiple-choice prompts may need degradation to plain-text questions",
  "status": "lossy"
}
```

This contract should live in rule/config files rather than code-only logic so it can be
reviewed and versioned.

## Harness Adapters

Harness support should be implemented as explicit adapters, not embedded conditionals
spread across the importer.

### Decision: Source Packages vs Generated Outputs

This plan chooses the layout now:

- keep source packages in `plugins/<name>/`
- generate harness-specific metadata under `generated/<harness>/`
- for Codex, generate rendered plugin directories only when transforms need to modify
  package contents or package metadata
- do not duplicate package contents unless a transform actually modifies files

That keeps v1 metadata-only where possible while still leaving room for future
per-harness rendered package directories if transforms become material.

### Claude Adapter

Input:

- neutral package metadata
- package directory
- compatibility assessment

Output:

- generated Claude marketplace manifest
- optionally generated Claude-specific plugin metadata if needed

Rules:

- include packages with Claude status `native`, `generated`, or `adapted`
- exclude `unsupported`, `blocked`, and `unknown`
- preserve Claude-native hook/plugin packaging when the package is explicitly Claude-only
- mark generated Claude outputs that rely on `.claude-plugin` packaging as `support_basis:
  convention` unless official Anthropic plugin packaging docs are later confirmed

### Codex Adapter

Input:

- neutral package metadata
- package directory
- compatibility assessment

Output:

- generated Codex marketplace artifact matching the documented marketplace format
- transformed plugin directories only when required
- rendered `.codex-plugin/plugin.json` manifests for Codex-compatible installation

Rules:

- include packages with Codex status `generated` or `adapted`
- include `agnostic` packages by default if all required capabilities map cleanly
- exclude hook-driven or Claude-runtime-dependent packages
- emit a report for skipped packages and reasons
- mark Codex plugin and marketplace outputs as `support_basis: official` because the
  package and marketplace contracts are documented

Concrete target files:

- repo-scoped marketplace: `.agents/plugins/marketplace.json`
- generated staging artifact: `generated/codex/marketplace.json`
- optional rendered plugin roots: `generated/codex/plugins/<name>/`

Codex marketplace entry shape should match the documented contract:

```json
{
  "name": "local-example-plugins",
  "interface": {
    "displayName": "Local Example Plugins"
  },
  "plugins": [
    {
      "name": "my-plugin",
      "source": {
        "source": "local",
        "path": "./plugins/my-plugin"
      },
      "policy": {
        "installation": "AVAILABLE",
        "authentication": "ON_INSTALL"
      },
      "category": "Productivity"
    }
  ]
}
```

Codex plugin package shape should target:

```text
my-plugin/
├── .codex-plugin/
│   └── plugin.json
├── skills/
├── .app.json
├── .mcp.json
└── assets/
```

Codex plugin manifests should support:

- required package metadata: `name`, `version`, `description`
- component pointers: `skills`, `apps`, `mcpServers`
- discovery and install-surface metadata under `interface`

The generator should keep all manifest paths relative to the plugin root and prefixed
with `./`, matching the documented Codex path rules.

Codex-specific marketplace fields need explicit defaults or overrides.

Recommended v1 behavior:

- default `policy.installation` to `AVAILABLE`
- default `policy.authentication` to `ON_INSTALL`
- default `category` from a maintained mapping table based on package capabilities
- allow per-package overrides in the package record when defaults are wrong

Suggested package metadata shape:

```json
{
  "generation": {
    "codex": {
      "marketplace": {
        "policy": {
          "installation": "AVAILABLE",
          "authentication": "ON_INSTALL"
        },
        "category": "Developer Tools"
      }
    }
  }
}
```

### Future Cursor Adapter

The same adapter contract should support future harnesses without changing the catalog
schema. Only adapter config and rule files should need additions.

## Adaptation Strategy

This repository supports only shallow transforms for cross-harness generation.

Allowed in-repo transforms:

- map harness-specific tool names to neutral capabilities, then back to target harness terms
- strip or replace shallow harness-specific preambles
- rewrite hardcoded path variables into harness-specific config variables
- flatten raw-skill imports into target harness packaging
- generate wrapper manifests or small wrapper skill files

Not allowed as long-lived in-repo adaptation strategies:

- patch stacks carrying semantic workflow rewrites
- large-scale edits to imported upstream skill instructions
- redesigning hooks or lifecycle behavior inline
- repeated manual conflict resolution against upstream inside this repository

If a package needs those deeper changes, it must be maintained as a separate fork
repository and imported back into this marketplace as its own package.

Transforms should be recorded in generation metadata:

```json
{
  "generation": {
    "codex": {
      "enabled": true,
      "mode": "adapted",
      "transforms": [
        "tool-name-map-v1",
        "remove-claude-home-paths-v1"
      ]
    }
  }
}
```

### Transform Contract

Transforms must not be opaque names with undocumented behavior.

Each transform should have:

- `transform_id`
- `version`
- `input_contract`
- `output_contract`
- `reversible`
- `description`
- `tests`

Suggested rule entry:

```json
{
  "transform_id": "tool-name-map",
  "version": "1.0.0",
  "input_contract": "neutral capability set plus source metadata",
  "output_contract": "target harness tool metadata",
  "reversible": false,
  "description": "Maps neutral capabilities to target harness tool names",
  "tests": ["tests/transforms/test_tool_name_map.py"]
}
```

`generation.*.transforms` should record both ID and version:

```json
{
  "generation": {
    "codex": {
      "enabled": true,
      "mode": "adapted",
      "transforms": [
        "tool-name-map@1.0.0",
        "remove-claude-home-paths@1.0.0"
      ]
    }
  }
}
```

### Fork Policy

When a cross-harness version requires more than shallow transforms, use a separate fork
repository instead of carrying the adaptation locally.

Forked packages should:

- be imported as normal packages through the same catalog process
- declare `source_model: adapted-fork`
- link back to the original package via `fork_of`
- declare their own canonical harness

This repository may index both:

- the original upstream package for its native harness
- the adapted fork package for the other harness

That keeps update management simple:

- original upstream package syncs from the original repo
- adapted fork syncs from the fork repo
- this repository does not carry deep adaptation deltas inline

For v1, do not attempt to auto-convert hook-driven or semantically coupled packages.
Treat them as `harness-specific` unless a real shallow transform path exists. If they
need to support another harness, create a fork repository.

## Listing and Querying

The catalog should support listing packages by harness and compatibility status.

Suggested CLI:

```bash
uv run scripts/catalog.py list --harness claude
uv run scripts/catalog.py list --harness codex
uv run scripts/catalog.py list --class agnostic
uv run scripts/catalog.py list --status adapted --harness codex
uv run scripts/catalog.py show review
uv run scripts/catalog.py findings review
```

Suggested filters:

- `--harness <name>`
- `--class <agnostic|adaptable|harness-specific|unknown>`
- `--status <native|generated|adapted|unsupported|blocked|unknown>`
- `--basis <official|adapter|convention|unsupported|unknown>`
- `--verified`
- `--has-executable-code`

This makes the repository answer operational questions directly:

- Which plugins work in Codex today?
- Which ones are adaptable but not yet transformed?
- Which ones are Claude-only because of hooks?
- Which ones rely on conventions rather than official contracts?

## Generation Pipeline

Generation should be separate from import. Import updates the catalog; generation renders
the catalog into marketplace outputs.

### Step 1: Import

- fetch upstream content
- stage package
- run security and compatibility assessment
- write neutral catalog entry
- copy or update package files under `plugins/`

As part of assessment, import should assign:

- neutral components detected
- harness-specific bindings detected
- `status_by_harness`
- `support_basis`
- convention-only findings where applicable
- `source_model`
- `canonical_harness`
- `fork_of` when the package is an adapted fork

### Step 2: Generate

- read `catalog/packages/`
- select packages supported for target harness
- render target marketplace artifact
- optionally validate generated output against target harness schema

For Codex specifically:

- render repo-scoped marketplace output to `generated/codex/marketplace.json`
- validate that every plugin entry includes `policy.installation`,
  `policy.authentication`, and `category`
- ensure every generated `source.path` is relative, `./`-prefixed, and remains inside
  the marketplace root
- render `.codex-plugin/plugin.json` only for packages whose Codex output differs from
  source package metadata

### Step 3: Publish

- commit catalog changes and generated artifacts together

This keeps the system deterministic and auditable.

## Changes to Existing Files

### `sources.json`

Current `sources.json` should be migrated into `catalog/sources.json` or folded into
`catalog/packages.json` under `upstream`.

The current fields remain useful:

- `upstream_repo`
- `upstream_path`
- `upstream_ref`
- `last_synced_commit`
- `last_checked`
- `local_modifications`
- `has_executable_code`
- `verification.skills`

Additional provenance fields will be needed for adapted forks:

- `source_model`
- `canonical_harness`
- `fork_of`
- `upstream_strategy`

Additional local policy files will be needed for mirror-preserving security exceptions:

- `catalog/security/suppressions/<package>.json`

### `.claude-plugin/marketplace.json`

Current root marketplace file should become generated output from the neutral catalog.
It should no longer be hand-edited.

### `.agents/plugins/marketplace.json`

Add a generated Codex marketplace output path. The generated file should be suitable for
copying or syncing into `$REPO_ROOT/.agents/plugins/marketplace.json` for repo-scoped
Codex testing.

### `scripts/sync-check.py`

This script should remain the main intake workflow, but it needs to be refactored into:

- import/staging logic
- compatibility assessment
- catalog writes
- output generation triggers

It should stop writing Claude-native marketplace entries directly as the primary action.

## Schema Versioning and Migration

The catalog itself needs versioning, not just per-package `assessment_version`.

### Top-Level Versioning

`catalog/catalog.json` should contain:

- `catalog_schema_version`
- `generator_versions`
- `supported_harnesses`

### Migration Policy

For v1, schema evolution can be simple:

- bump `catalog_schema_version` when structure changes
- provide a migration script if stored files need rewriting
- if migration is mechanical, allow `uv run scripts/migrate-catalog.py`
- if migration is assessment-only, re-run assessment across all packages

This prevents silent drift between stored package records and code expectations.

Suppression files should version with the catalog schema as needed so that suppression
matching logic can evolve without mutating imported package content.

## Testing Strategy

The assessment engine is the highest-risk logic in this design and needs first-class
tests, not ad hoc manual validation.

### Golden Tests

Create a suite of package fixtures with expected assessment outputs:

- pure markdown skill expected `agnostic`
- Claude hook-driven plugin expected `harness-specific`
- package with hardcoded `~/.claude` paths expected `harness-specific`
- package with simple metadata-only coupling expected `adaptable`
- package with `.codex-plugin/plugin.json` expected Codex `support_basis: official`
- package with `.claude-plugin/plugin.json` expected Claude `support_basis: convention`
- package with local Semgrep suppressions expected to preserve upstream file bytes while
  downgrading matching raw findings to suppressed findings

Suggested test style:

- fixture package under `tests/fixtures/packages/<name>/`
- expected findings JSON under `tests/fixtures/expected/<name>.json`
- test asserts portability class, per-harness status, and critical findings

### Transform Tests

Each transform should have isolated tests for:

- input parsing
- expected output
- unchanged fields
- failure behavior on unsupported input

### Generator Tests

Generators should have snapshot or schema validation tests for:

- generated Claude marketplace output
- generated Codex marketplace output
- exclusion behavior for unsupported packages

### Security Policy Tests

The import/security pipeline should have tests for:

- suppression application without mutating imported content
- unsuppressed findings still blocking import
- stale suppressions surfacing as warnings when a finding disappears or no longer matches

## Initial Implementation Plan

### Phase 1: Introduce neutral schema and backfill current catalog

Create:

- `catalog/catalog.json`
- `catalog/packages/`
- `catalog/security/suppressions/`
- `catalog/schema/package.schema.json`
- `catalog/schema/catalog.schema.json`
- `catalog/schema/compatibility.schema.json`

Backfill all existing packages into per-package catalog files using current metadata from:

- `.claude-plugin/marketplace.json`
- `sources.json`
- plugin-local `.claude-plugin/plugin.json`

Also identify imported files that were locally edited only to add inline Semgrep
suppression comments. Migrate those suppressions into
`catalog/security/suppressions/<package>.json` and restore imported files to match
upstream where possible.

### Phase 2: Add assessment engine

Implement a reusable assessment module that:

- scans package contents
- emits findings
- assigns portability class
- assigns per-harness status
- assigns `source_model` and `canonical_harness`
- applies repository-owned suppression metadata after raw scanning

This should run during import and also be rerunnable across the whole repository.

Suggested entry point:

```bash
uv run scripts/assess-package.py --plugin review
uv run scripts/assess-package.py --all
```

### Phase 3: Add listing/query CLI

Implement a simple catalog query command:

```bash
uv run scripts/catalog.py list --harness codex
uv run scripts/catalog.py show modern-python
```

### Phase 4: Generate Claude output from neutral catalog

Implement:

```bash
uv run scripts/generate-marketplace.py --harness claude
```

The generated output should match the current Claude marketplace as closely as possible.

### Phase 5: Implement Codex adapter

Implement:

```bash
uv run scripts/generate-marketplace.py --harness codex
```

The Codex generator should start conservative:

- include `agnostic` packages automatically
- include `adaptable` packages only if an explicit transform path exists
- exclude `harness-specific` packages
- treat `adapted-fork` packages as independent native inputs for their canonical harness

Expected outputs:

- `generated/codex/marketplace.json`
- optional `generated/codex/plugins/<name>/` directories for transformed packages
- optional sync step into `$REPO_ROOT/.agents/plugins/marketplace.json` for local testing

### Phase 6: Make generation mandatory

Once the generated Claude output is stable:

- stop hand-editing `.claude-plugin/marketplace.json`
- validate generated artifacts in CI
- fail CI if catalog and generated output diverge

## Conservative V1 Policy

To avoid breaking users, v1 should be intentionally conservative.

### Auto-include for Claude

- `native`
- `generated`
- `adapted`

### Auto-include for Codex

- `agnostic` packages with full capability mapping

### Manual review required

- `adaptable` packages before first transform implementation
- any package with executable code
- any package with unknown capability mappings
- any package proposed for cross-harness support that exceeds shallow transform policy

### Never auto-convert in v1

- hook-driven packages
- packages that modify harness-owned config/state during startup
- packages with opaque script installers

## Open Questions

These need resolution before implementation is complete:

### 1. How much adaptation is acceptable?

We should decide whether adaptation can be:

- metadata-only
- text rewriting in skills
- structural packaging changes
- code patching

Decision: allow metadata generation, deterministic text/layout rewrites, path rewriting,
tool vocabulary mapping, and small wrapper-file generation only. Do not allow code
patching or semantic workflow rewrites as part of normal generation in this repository.
Those belong in separate fork repositories.

### 2. Is verification global, per harness, or per skill?

Decision: track verification per skill. Verification is a repository review state over
imported skill content, not a harness-support claim. Harness compatibility remains in
`status_by_harness` and `support_basis`; verification should answer only whether a
specific imported skill has been reviewed and approved.

## Recommended First Deliverable

The first deliverable should not be Codex generation. It should be the neutral catalog
and assessment engine.

Specifically:

1. create `catalog/catalog.json` and `catalog/packages/<name>.json`
2. migrate current metadata into it
3. add structured compatibility findings plus `support_basis` for all current plugins
4. add `source_model` and `canonical_harness` tracking
5. add `list --harness` and `list --basis` support
6. regenerate Claude marketplace from the catalog

That yields immediate value even before Codex support is complete, because it gives
clear answers about package portability and removes Claude metadata from the role of
source of truth.

## Success Criteria

This design is complete when the repository can:

1. Import an upstream package and automatically assess its harness compatibility
2. Persist structured compatibility findings in a neutral catalog
3. List packages by harness support and compatibility class
4. Generate a Claude marketplace artifact from the neutral catalog
5. Generate a Codex marketplace artifact from the same neutral catalog
6. Add a future harness without redesigning the underlying metadata model
