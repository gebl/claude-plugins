# /// script
# requires-python = ">=3.12"
# ///
"""Shallow cross-harness transforms for generated harness outputs.

Rewrites skill content from Claude-specific tool names and paths to target harness equivalents.
"""

import json
import re
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TRANSFORMS_JSON = REPO_ROOT / "catalog" / "rules" / "transforms.json"

UNSUPPORTED_TOOLS_BY_HARNESS = {
    "codex": frozenset(
        {
            "WebSearch",
            "WebFetch",
            "TodoRead",
            "TodoWrite",
            "TaskCreate",
            "TaskUpdate",
            "NotebookEdit",
            "EnterPlanMode",
        }
    ),
    "copilot": frozenset(
        {
            "WebSearch",
            "WebFetch",
            "TodoRead",
            "TodoWrite",
            "TaskCreate",
            "TaskUpdate",
            "NotebookEdit",
            "EnterPlanMode",
            "Agent",
        }
    ),
}

PATH_VARS_BY_HARNESS = {
    "codex": {
        "${CLAUDE_PLUGIN_ROOT}": "${CODEX_PLUGIN_ROOT}",
        "${CLAUDE_SKILL_DIR}": "${CODEX_SKILL_DIR}",
    },
    "copilot": {
        "${CLAUDE_PLUGIN_ROOT}": "${COPILOT_SKILL_ROOT}",
        "${CLAUDE_SKILL_DIR}": "${COPILOT_SKILL_DIR}",
    },
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


def build_tool_name_map(target_harness: str) -> dict[str, str]:
    """Return a dict mapping Claude tool names to target-harness tool names.

    For one_to_many mappings, each Claude feature maps positionally to its target feature.
    """
    mappings = _load_capability_mappings()
    tool_map: dict[str, str] = {}

    for cap in mappings:
        claude = cap["mappings"].get("claude", {})
        target = cap["mappings"].get(target_harness, {})

        claude_features = claude.get("features", [])
        target_features = target.get("features", [])
        target_status = target.get("status", "")

        if target_status == "unsupported" or not target_features:
            continue

        # Positional mapping: Read->read_file, Grep->grep_search, etc.
        for i, claude_name in enumerate(claude_features):
            if i < len(target_features):
                tool_map[claude_name] = target_features[i]

    return tool_map


def can_adapt_for_harness(tool_refs: list[str], target_harness: str) -> tuple[bool, list[str]]:
    """Check whether all referenced tools can be adapted for a target harness.

    Returns (True, []) if every tool has a mapping (exact, approximate, or lossy).
    Returns (False, unsupported_tools) if any tool has no target-harness mapping.
    """
    tool_map = build_tool_name_map(target_harness)
    supported = set(tool_map.keys())
    unsupported_tools = UNSUPPORTED_TOOLS_BY_HARNESS.get(target_harness, frozenset())

    unsupported = [t for t in tool_refs if t not in supported and t not in unsupported_tools]
    truly_unsupported = [t for t in tool_refs if t in unsupported_tools]

    missing = truly_unsupported + unsupported
    if not missing:
        return (True, [])
    return (False, missing)


def can_adapt_for_codex(tool_refs: list[str]) -> tuple[bool, list[str]]:
    return can_adapt_for_harness(tool_refs, "codex")


def can_adapt_for_copilot(tool_refs: list[str]) -> tuple[bool, list[str]]:
    return can_adapt_for_harness(tool_refs, "copilot")


def _build_tool_pattern(tool_map: dict[str, str]) -> re.Pattern[str]:
    """Build a regex that matches Claude tool names as whole words.

    Matches tool names that are:
    - Surrounded by word boundaries (won't match "Reading" for "Read")
    - In backticks like `Read`
    - In natural language like "the Read tool" or "Use Bash"
    """
    names = sorted(tool_map.keys(), key=len, reverse=True)
    # Use word boundaries to avoid partial matches.
    # Negative lookbehind for alphanumeric and negative lookahead for alphanumeric/underscore
    # ensures we don't match inside longer words.
    alternatives = "|".join(re.escape(name) for name in names)
    return re.compile(rf"(?<![a-zA-Z0-9_])({alternatives})(?![a-zA-Z0-9_])")


def transform_skill_content(
    content: str,
    tool_map: dict[str, str],
    path_vars: dict[str, str] | None = None,
) -> str:
    """Rewrite skill markdown, replacing Claude tool names and path variables.

    Handles patterns like "the Read tool", "`Bash`", "Use Agent", etc.
    Does NOT replace partial matches (e.g. "Read" won't match "Reading" or "README").
    """
    if not tool_map:
        return content

    pattern = _build_tool_pattern(tool_map)

    def _replace_tool(match: re.Match[str]) -> str:
        return tool_map[match.group(1)]

    result = pattern.sub(_replace_tool, content)

    for source_var, target_var in (path_vars or {}).items():
        result = result.replace(source_var, target_var)

    if path_vars == PATH_VARS_BY_HARNESS.get("copilot"):
        for pattern, replacement in COPILOT_CONTENT_REWRITES:
            result = re.sub(pattern, replacement, result)
        result = result.replace("`${COPILOT_SKILL_ROOT}/", "`")

    return result


def transform_plugin_for_harness(plugin_name: str, output_dir: Path, target_harness: str) -> list[str]:
    """Copy a plugin's skills/ directory to output_dir, applying target-harness transforms to .md files.

    Returns list of transformed file paths (relative to output_dir).
    Does NOT copy non-skill content (hooks, commands, agents).
    """
    plugin_dir = REPO_ROOT / "plugins" / plugin_name
    skills_dir = plugin_dir / "skills"

    if not skills_dir.is_dir():
        return []

    tool_map = build_tool_name_map(target_harness)
    path_vars = PATH_VARS_BY_HARNESS.get(target_harness, {})
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
            transformed_content = transform_skill_content(content, tool_map, path_vars)
            dest.write_text(transformed_content)
            transformed.append(str(rel))
        else:
            shutil.copy2(src_file, dest)

    return transformed


def transform_plugin_for_codex(plugin_name: str, output_dir: Path) -> list[str]:
    return transform_plugin_for_harness(plugin_name, output_dir, "codex")


def transform_plugin_for_copilot(plugin_name: str, output_dir: Path) -> list[str]:
    return transform_plugin_for_harness(plugin_name, output_dir, "copilot")


if __name__ == "__main__":
    print("=== Tool Name Map ===")
    tool_map = build_tool_name_map("codex")
    for claude_name, codex_name in sorted(tool_map.items()):
        print(f"  {claude_name:20s} -> {codex_name}")

    print("\n=== can_adapt_for_codex tests ===")

    # All supported
    ok, missing = can_adapt_for_codex(["Read", "Edit", "Bash"])
    print(f"  [Read, Edit, Bash]          -> adaptable={ok}, missing={missing}")
    assert ok is True  # noqa: S101
    assert missing == []  # noqa: S101

    # Includes lossy (AskUserQuestion -> assistant_message)
    ok, missing = can_adapt_for_codex(["Read", "AskUserQuestion"])
    print(f"  [Read, AskUserQuestion]     -> adaptable={ok}, missing={missing}")
    assert ok is True  # noqa: S101

    # Unsupported tool
    ok, missing = can_adapt_for_codex(["Read", "WebSearch"])
    print(f"  [Read, WebSearch]           -> adaptable={ok}, missing={missing}")
    assert ok is False  # noqa: S101
    assert "WebSearch" in missing  # noqa: S101

    # Multiple unsupported
    ok, missing = can_adapt_for_codex(["TodoRead", "NotebookEdit", "Bash"])
    print(f"  [TodoRead, NotebookEdit, Bash] -> adaptable={ok}, missing={missing}")
    assert ok is False  # noqa: S101
    assert "TodoRead" in missing  # noqa: S101
    assert "NotebookEdit" in missing  # noqa: S101

    print("\n=== transform_skill_content tests ===")
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
    result = transform_skill_content(sample, tool_map)
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

    print("\n=== All tests passed ===")
