# /// script
# requires-python = ">=3.12"
# ///
"""Shallow cross-harness transforms for generated harness outputs.

Rewrites skill content from a source harness's tool names and path variables to the
equivalent names in any target harness (N×N mapping).
"""

import json
import re
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TRANSFORMS_JSON = REPO_ROOT / "catalog" / "rules" / "transforms.json"

# Per-harness path variable names keyed by semantic role.
# Maps role → the variable string used in that harness's skill text.
_HARNESS_PATH_VARS: dict[str, dict[str, str]] = {
    "claude":  {"plugin_root": "${CLAUDE_PLUGIN_ROOT}",   "skill_dir": "${CLAUDE_SKILL_DIR}"},
    "codex":   {"plugin_root": "${CODEX_PLUGIN_ROOT}",    "skill_dir": "${CODEX_SKILL_DIR}"},
    "copilot": {"plugin_root": "${COPILOT_SKILL_ROOT}",   "skill_dir": "${COPILOT_SKILL_DIR}"},
}

# Backward-compat: target harness → path var substitution map assuming claude as source.
PATH_VARS_BY_HARNESS = {
    target: {
        _HARNESS_PATH_VARS["claude"][role]: _HARNESS_PATH_VARS[target][role]
        for role in _HARNESS_PATH_VARS["claude"]
    }
    for target in ("codex", "copilot")
}

COPILOT_CONTENT_REWRITES = (
    (r'cd "\$\{COPILOT_SKILL_ROOT\}" && uv run python', 'python3'),
    (r'cd "\$\{COPILOT_SKILL_ROOT\}" &&', ''),
    (r'Use the CLI script at "\$\{COPILOT_SKILL_ROOT\}/', 'Use the colocated CLI script `'),
    (r'Run it with `uv run` from the plugin directory:', 'Run it from this skill directory:'),
    (r'If `uv` is not available, instruct the user to install it\.', 'If `python3` is not available, tell the user the transcript helper cannot run in the current environment.'),
)


def _load_capability_mappings() -> list[dict]:
    """Load capability_mappings from transforms.json."""
    data = json.loads(TRANSFORMS_JSON.read_text())
    return data["capability_mappings"]


def get_path_var_map(source_harness: str, target_harness: str) -> dict[str, str]:
    """Return a mapping from source harness path variables to target harness path variables.

    Returns an empty dict when source == target or either harness is unknown.
    """
    if source_harness == target_harness:
        return {}
    src = _HARNESS_PATH_VARS.get(source_harness, {})
    tgt = _HARNESS_PATH_VARS.get(target_harness, {})
    return {src[role]: tgt[role] for role in src if role in tgt}


def build_tool_maps(
    source_harness: str, target_harness: str
) -> tuple[dict[str, str], frozenset[str]]:
    """Return (tool_name_map, unsupported_tools) for a (source, target) harness pair.

    tool_name_map maps source tool names to target tool names for all mappable capabilities.
    unsupported_tools is the set of source tool names whose capabilities are unavailable in
    the target harness.
    """
    mappings = _load_capability_mappings()
    tool_map: dict[str, str] = {}
    unsupported: set[str] = set()

    for cap in mappings:
        source = cap["mappings"].get(source_harness, {})
        target = cap["mappings"].get(target_harness, {})

        source_features = source.get("features", [])
        target_features = target.get("features", [])
        target_status = target.get("status", "")

        if target_status == "unsupported" or not target_features:
            unsupported.update(source_features)
            continue

        # Positional mapping: source features → target features
        for i, src_name in enumerate(source_features):
            if i < len(target_features):
                tool_map[src_name] = target_features[i]

    return tool_map, frozenset(unsupported)


def build_tool_name_map(
    source_harness: str, target_harness: str | None = None
) -> dict[str, str]:
    """Return a dict mapping source harness tool names to target harness tool names.

    When called with a single argument (legacy usage), the argument is treated as
    target_harness with claude assumed as the source.
    """
    if target_harness is None:
        # Legacy single-argument call: build_tool_name_map("codex") → claude → codex
        target_harness = source_harness
        source_harness = "claude"
    tool_map, _ = build_tool_maps(source_harness, target_harness)
    return tool_map


def can_adapt_for_harness(
    tool_refs: list[str],
    source_harness: str,
    target_harness: str | None = None,
) -> tuple[bool, list[str]]:
    """Check whether all referenced tools can be adapted from source to target harness.

    When called with two arguments (legacy usage), source_harness is treated as
    target_harness with claude assumed as the source.

    Returns (True, []) if every tool has a mapping (exact, approximate, or lossy).
    Returns (False, missing_tools) if any tool has no target-harness mapping.
    """
    if target_harness is None:
        # Legacy call: can_adapt_for_harness(tools, "codex") → claude → codex
        target_harness = source_harness
        source_harness = "claude"

    tool_map, unsupported_tools = build_tool_maps(source_harness, target_harness)
    supported = set(tool_map.keys())

    truly_unsupported = [t for t in tool_refs if t in unsupported_tools]
    unrecognized = [t for t in tool_refs if t not in supported and t not in unsupported_tools]

    missing = truly_unsupported + unrecognized
    if not missing:
        return (True, [])
    return (False, missing)


def can_adapt_for_codex(tool_refs: list[str]) -> tuple[bool, list[str]]:
    return can_adapt_for_harness(tool_refs, "claude", "codex")


def can_adapt_for_copilot(tool_refs: list[str]) -> tuple[bool, list[str]]:
    return can_adapt_for_harness(tool_refs, "claude", "copilot")


def _build_tool_pattern(tool_map: dict[str, str]) -> re.Pattern[str]:
    """Build a regex that matches source tool names as whole words.

    Matches tool names that are:
    - Surrounded by word boundaries (won't match "Reading" for "Read")
    - In backticks like `Read`
    - In natural language like "the Read tool" or "Use Bash"
    """
    names = sorted(tool_map.keys(), key=len, reverse=True)
    alternatives = "|".join(re.escape(name) for name in names)
    return re.compile(rf"(?<![a-zA-Z0-9_])({alternatives})(?![a-zA-Z0-9_])")


def transform_skill_content(
    content: str,
    tool_map: dict[str, str],
    path_vars: dict[str, str] | None = None,
    *,
    target_harness: str | None = None,
) -> str:
    """Rewrite skill markdown, replacing source tool names and path variables.

    Handles patterns like "the Read tool", "`Bash`", "Use Agent", etc.
    Does NOT replace partial matches (e.g. "Read" won't match "Reading" or "README").

    When target_harness="copilot", additional Copilot-specific content rewrites are applied.
    """
    if not tool_map:
        result = content
    else:
        pattern = _build_tool_pattern(tool_map)

        def _replace_tool(match: re.Match[str]) -> str:
            return tool_map[match.group(1)]

        result = pattern.sub(_replace_tool, content)

    for source_var, target_var in (path_vars or {}).items():
        result = result.replace(source_var, target_var)

    if target_harness == "copilot":
        for pat, replacement in COPILOT_CONTENT_REWRITES:
            result = re.sub(pat, replacement, result)
        result = result.replace("`${COPILOT_SKILL_ROOT}/", "`")

    return result


def transform_plugin_for_harness(
    plugin_name: str,
    output_dir: Path,
    target_harness: str,
    source_harness: str = "claude",
) -> list[str]:
    """Copy a plugin's skills/ directory to output_dir, applying target-harness transforms.

    Reads the plugin from plugins-{source_harness}/{plugin_name}/skills/ and writes
    transformed .md files (with all other files copied verbatim) to output_dir/skills/.

    Returns list of transformed file paths (relative to output_dir/skills/).
    Does NOT copy non-skill content (hooks, commands, agents).
    """
    plugin_dir = REPO_ROOT / f"plugins-{source_harness}" / plugin_name
    skills_dir = plugin_dir / "skills"

    if not skills_dir.is_dir():
        return []

    tool_map = build_tool_name_map(source_harness, target_harness)
    path_vars = get_path_var_map(source_harness, target_harness)
    transformed: list[str] = []
    output_skills = output_dir / "skills"

    for src_file in skills_dir.rglob("*"):
        if not src_file.is_file():
            continue

        rel = src_file.relative_to(skills_dir)
        dest = output_skills / rel
        dest.parent.mkdir(parents=True, exist_ok=True)

        if src_file.suffix == ".md":
            content = src_file.read_text()
            transformed_content = transform_skill_content(
                content, tool_map, path_vars, target_harness=target_harness
            )
            dest.write_text(transformed_content)
            transformed.append(str(rel))
        else:
            shutil.copy2(src_file, dest)

    return transformed


def transform_plugin_for_codex(
    plugin_name: str, output_dir: Path, source_harness: str = "claude"
) -> list[str]:
    return transform_plugin_for_harness(plugin_name, output_dir, "codex", source_harness)


def transform_plugin_for_copilot(
    plugin_name: str, output_dir: Path, source_harness: str = "claude"
) -> list[str]:
    return transform_plugin_for_harness(plugin_name, output_dir, "copilot", source_harness)


if __name__ == "__main__":
    print("=== Tool Name Map (claude → codex) ===")
    tool_map = build_tool_name_map("claude", "codex")
    for src_name, tgt_name in sorted(tool_map.items()):
        print(f"  {src_name:20s} -> {tgt_name}")

    print("\n=== Tool Name Map (codex → claude) ===")
    reverse_map = build_tool_name_map("codex", "claude")
    for src_name, tgt_name in sorted(reverse_map.items()):
        print(f"  {src_name:20s} -> {tgt_name}")

    print("\n=== Path Var Map (claude → copilot) ===")
    pv_map = get_path_var_map("claude", "copilot")
    for src_var, tgt_var in pv_map.items():
        print(f"  {src_var} -> {tgt_var}")

    print("\n=== Path Var Map (codex → claude) ===")
    pv_map2 = get_path_var_map("codex", "claude")
    for src_var, tgt_var in pv_map2.items():
        print(f"  {src_var} -> {tgt_var}")

    print("\n=== can_adapt_for_harness tests ===")

    # N×N: claude → codex (backward compat)
    ok, missing = can_adapt_for_harness(["Read", "Edit", "Bash"], "claude", "codex")
    print(f"  claude→codex [Read, Edit, Bash]          -> adaptable={ok}, missing={missing}")
    assert ok is True  # noqa: S101
    assert missing == []  # noqa: S101

    ok, missing = can_adapt_for_harness(["Read", "WebSearch"], "claude", "codex")
    print(f"  claude→codex [Read, WebSearch]           -> adaptable={ok}, missing={missing}")
    assert ok is False  # noqa: S101
    assert "WebSearch" in missing  # noqa: S101

    # N×N: codex → claude
    ok, missing = can_adapt_for_harness(["read_file", "shell", "grep_search"], "codex", "claude")
    print(f"  codex→claude [read_file, shell, grep_search] -> adaptable={ok}, missing={missing}")
    assert ok is True  # noqa: S101

    # Legacy single-arg call still works
    ok, missing = can_adapt_for_codex(["Read", "Edit", "Bash"])
    print(f"  can_adapt_for_codex [Read, Edit, Bash]   -> adaptable={ok}, missing={missing}")
    assert ok is True  # noqa: S101

    print("\n=== transform_skill_content tests ===")
    tool_map_cl_cx = build_tool_name_map("claude", "codex")
    sample = (
        "Use the Read tool to inspect files. "
        "Call `Bash` for shell commands. "
        "The Agent can spawn subagents. "
        "Reading files is easy. "
        "Check the README for details. "
        "Use Grep and Glob for searching. "
        "Path: ${CLAUDE_PLUGIN_ROOT}/config "
        "Skill: ${CLAUDE_SKILL_DIR}/bin/run.sh"
    )
    path_vars = get_path_var_map("claude", "codex")
    result = transform_skill_content(sample, tool_map_cl_cx, path_vars, target_harness="codex")
    print(f"  Input:  {sample}")
    print(f"  Output: {result}")

    assert "read_file" in result  # noqa: S101
    assert "shell" in result  # noqa: S101
    assert "spawn_agent" in result  # noqa: S101
    assert "grep_search" in result  # noqa: S101
    assert "file_search" in result  # noqa: S101
    assert "Reading" in result  # Should NOT be transformed # noqa: S101
    assert "README" in result  # Should NOT be transformed # noqa: S101
    assert "${CODEX_PLUGIN_ROOT}" in result  # noqa: S101
    assert "${CODEX_SKILL_DIR}" in result  # noqa: S101
    assert "${CLAUDE_PLUGIN_ROOT}" not in result  # noqa: S101
    assert "${CLAUDE_SKILL_DIR}" not in result  # noqa: S101

    # Test codex → claude reverse transform
    codex_sample = (
        "Use read_file to inspect files. "
        "Run shell commands. "
        "Path: ${CODEX_PLUGIN_ROOT}/config "
        "Skill: ${CODEX_SKILL_DIR}/bin/run.sh"
    )
    rev_tool_map = build_tool_name_map("codex", "claude")
    rev_path_vars = get_path_var_map("codex", "claude")
    rev_result = transform_skill_content(codex_sample, rev_tool_map, rev_path_vars, target_harness="claude")
    print(f"\n  Codex→Claude input:  {codex_sample}")
    print(f"  Codex→Claude output: {rev_result}")
    assert "Read" in rev_result  # noqa: S101
    assert "${CLAUDE_PLUGIN_ROOT}" in rev_result  # noqa: S101
    assert "${CODEX_PLUGIN_ROOT}" not in rev_result  # noqa: S101

    print("\n=== All tests passed ===")

