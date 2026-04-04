# /// script
# requires-python = ">=3.12"
# ///
"""Shallow cross-harness transforms for the plugin marketplace.

Rewrites skill content from Claude-specific tool names and paths to Codex equivalents.
"""

import json
import re
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TRANSFORMS_JSON = REPO_ROOT / "catalog" / "rules" / "transforms.json"

# Claude tools with no Codex equivalent at all
UNSUPPORTED_TOOLS = frozenset(
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
)

# Path variable mappings
PATH_VARS = {
    "${CLAUDE_PLUGIN_ROOT}": "${CODEX_PLUGIN_ROOT}",
    "${CLAUDE_SKILL_DIR}": "${CODEX_SKILL_DIR}",
}


def _load_capability_mappings() -> list[dict]:
    """Load capability_mappings from transforms.json."""
    data = json.loads(TRANSFORMS_JSON.read_text())
    return data["capability_mappings"]


def build_tool_name_map() -> dict[str, str]:
    """Return a dict mapping Claude tool names to Codex tool names.

    For one_to_many mappings, each Claude feature maps positionally to its Codex feature.
    """
    mappings = _load_capability_mappings()
    tool_map: dict[str, str] = {}

    for cap in mappings:
        claude = cap["mappings"].get("claude", {})
        codex = cap["mappings"].get("codex", {})

        claude_features = claude.get("features", [])
        codex_features = codex.get("features", [])
        codex_status = codex.get("status", "")

        if codex_status == "unsupported" or not codex_features:
            continue

        # Positional mapping: Read->read_file, Grep->grep_search, Glob->file_search, etc.
        for i, claude_name in enumerate(claude_features):
            if i < len(codex_features):
                tool_map[claude_name] = codex_features[i]

    return tool_map


def can_adapt_for_codex(tool_refs: list[str]) -> tuple[bool, list[str]]:
    """Check whether all referenced tools can be adapted for Codex.

    Returns (True, []) if every tool has a mapping (exact, approximate, or lossy).
    Returns (False, unsupported_tools) if any tool has no Codex mapping.
    """
    tool_map = build_tool_name_map()
    supported = set(tool_map.keys())

    unsupported = [t for t in tool_refs if t not in supported and t not in UNSUPPORTED_TOOLS]
    truly_unsupported = [t for t in tool_refs if t in UNSUPPORTED_TOOLS]

    missing = truly_unsupported + unsupported
    if not missing:
        return (True, [])
    return (False, missing)


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


def transform_skill_content(content: str, tool_map: dict[str, str]) -> str:
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

    # Replace path variables
    for claude_var, codex_var in PATH_VARS.items():
        result = result.replace(claude_var, codex_var)

    return result


def transform_plugin_for_codex(plugin_name: str, output_dir: Path) -> list[str]:
    """Copy a plugin's skills/ directory to output_dir, applying tool name transforms to .md files.

    Returns list of transformed file paths (relative to output_dir).
    Does NOT copy non-skill content (hooks, commands, agents).
    """
    plugin_dir = REPO_ROOT / "plugins" / plugin_name
    skills_dir = plugin_dir / "skills"

    if not skills_dir.is_dir():
        return []

    tool_map = build_tool_name_map()
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
            transformed_content = transform_skill_content(content, tool_map)
            dest.write_text(transformed_content)
            transformed.append(str(rel))
        else:
            shutil.copy2(src_file, dest)

    return transformed


if __name__ == "__main__":
    print("=== Tool Name Map ===")
    tool_map = build_tool_name_map()
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
