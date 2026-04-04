# Copilot CLI Skills Rollout

## Goal

Extend the registry to generate GitHub Copilot CLI skill outputs without forcing Copilot into the existing Codex marketplace model.

## Runtime Contract

The GitHub Docs page for creating Copilot CLI skills defines the v1 target:

- Copilot discovers skills from a filesystem skill tree rather than a plugin manifest.
- Each skill must provide a `SKILL.md`.
- `SKILL.md` must use YAML frontmatter with required metadata such as `name` and `description`.
- Skills can be installed from repo-local `.agents/skills/`.

For this repository, that means:

- generated staging root: `generated/copilot/skills/<name>/`
- local sync target: `.agents/skills/<name>/`
- no Copilot marketplace manifest in v1

## Architecture

The neutral catalog remains the source of truth.

- `catalog/packages/*.json` stores Copilot compatibility and generation metadata
- `catalog/rules/harness-copilot.json` stores Copilot-specific detection/runtime rules
- `scripts/generate-copilot.py` renders staged skill trees from catalog decisions
- `scripts/sync-copilot.py` installs generated skills into `.agents/skills/`

## Scope

Initial support is intentionally narrow.

- Assess and enable only agnostic skills first
- Prove end-to-end generation and sync with `grill-me`
- Keep adaptable and harness-specific packages out of Copilot generation until validated

## Acceptance Criteria

Phase 1 is complete when:

- the catalog can represent `copilot` as a harness
- `generated/copilot/skills/grill-me/SKILL.md` is produced from the catalog
- `uv run scripts/sync-copilot.py --clean` installs `grill-me` into `.agents/skills/`
- docs describe Copilot as a generated skill output, not as a marketplace
