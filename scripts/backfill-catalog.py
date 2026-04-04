"""One-time script to backfill catalog/packages/ from existing metadata sources."""

import json
import re
import sys
import warnings
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from transforms import can_adapt_for_harness  # noqa: E402

CATALOG_DIR = REPO_ROOT / "catalog" / "packages"

ASSESSMENT_VERSION = "2026-04-03.1"

NATIVE_HARNESSES = frozenset({"claude", "codex", "copilot"})
DEFAULT_NATIVE_HARNESS = "claude"

# Tool names recognised as harness-coupled, keyed by harness
HARNESS_TOOLS: dict[str, set[str]] = {
    "claude": {
        "Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent",
        "AskUserQuestion", "WebSearch", "WebFetch", "TodoRead", "TodoWrite",
        "NotebookEdit", "TaskCreate", "TaskUpdate", "EnterPlanMode",
    },
    "codex": {
        "read_file", "write_file", "edit_file", "shell",
        "grep_search", "file_search", "spawn_agent", "assistant_message",
    },
    "copilot": {
        "view", "edit", "create", "bash", "grep", "glob", "task", "ask_user",
    },
}

# Regexes for harness-specific home-directory paths
HARNESS_HOME_RE: dict[str, re.Pattern] = {
    "claude":  re.compile(r"~/\.claude\b"),
    "codex":   re.compile(r"~/\.codex\b"),
    "copilot": re.compile(r"~/\.github\b"),
}

HARNESS_HOME_LABEL: dict[str, str] = {
    "claude":  "~/.claude",
    "codex":   "~/.codex",
    "copilot": "~/.github",
}

# Regexes for harness path-variable conventions
HARNESS_PATH_VAR_RES: dict[str, list[re.Pattern]] = {
    "claude":  [re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}"), re.compile(r"\$\{CLAUDE_SKILL_DIR\}")],
    "codex":   [re.compile(r"\$\{CODEX_PLUGIN_ROOT\}"),  re.compile(r"\$\{CODEX_SKILL_DIR\}")],
    "copilot": [re.compile(r"\$\{COPILOT_SKILL_ROOT\}"), re.compile(r"\$\{COPILOT_SKILL_DIR\}")],
}

HARNESS_PATH_VAR_LABELS: dict[str, list[str]] = {
    "claude":  ["${CLAUDE_PLUGIN_ROOT}", "${CLAUDE_SKILL_DIR}"],
    "codex":   ["${CODEX_PLUGIN_ROOT}", "${CODEX_SKILL_DIR}"],
    "copilot": ["${COPILOT_SKILL_ROOT}", "${COPILOT_SKILL_DIR}"],
}

# Keep old name as alias for backward compatibility within this file
CLAUDE_TOOLS = HARNESS_TOOLS["claude"]
CLAUDE_HOME_RE = HARNESS_HOME_RE["claude"]
CLAUDE_PLUGIN_ROOT_RE = HARNESS_PATH_VAR_RES["claude"][0]
CLAUDE_SKILL_DIR_RE = HARNESS_PATH_VAR_RES["claude"][1]

EXECUTABLE_EXTENSIONS = {".py", ".sh", ".js", ".ts", ".rb", ".pl"}
DEPENDENCY_FILES = {"requirements.txt", "pyproject.toml", "package.json", "go.mod", "Cargo.toml"}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def find_executable_files(plugin_dir: Path) -> list[str]:
    results = []
    for f in plugin_dir.rglob("*"):
        if f.is_file() and f.suffix in EXECUTABLE_EXTENSIONS:
            results.append(str(f.relative_to(plugin_dir)))
    return sorted(results)


def find_dependency_files(plugin_dir: Path) -> list[str]:
    results = []
    for f in plugin_dir.rglob("*"):
        if f.is_file() and f.name in DEPENDENCY_FILES:
            results.append(str(f.relative_to(plugin_dir)))
    return sorted(results)


def scan_text_files(plugin_dir: Path, native_harness: str = DEFAULT_NATIVE_HARNESS) -> dict:
    """Scan all text files for harness-specific references.

    Returns findings plus ``native_tool_refs`` and ``home_path_count`` keyed
    to the declared *native_harness* so that callers remain harness-agnostic.
    Legacy keys ``claude_tool_refs`` / ``claude_home_count`` are also included
    for backward compatibility when ``native_harness`` is ``"claude"``.
    """
    findings = []
    home_path_count = 0
    native_tool_refs: set[str] = set()

    home_re = HARNESS_HOME_RE[native_harness]
    path_var_res = HARNESS_PATH_VAR_RES[native_harness]
    path_var_labels = HARNESS_PATH_VAR_LABELS[native_harness]
    tool_names = HARNESS_TOOLS[native_harness]

    harness_upper = native_harness.upper()

    for f in plugin_dir.rglob("*"):
        if not f.is_file():
            continue
        if f.suffix in {".json", ".png", ".jpg", ".gif", ".ico", ".db", ".sqlite"}:
            continue
        # Skip README/docs — install instructions referencing paths are not
        # the same as the skill itself depending on those paths.
        if f.name.upper().startswith("README"):
            continue
        try:
            text = f.read_text(errors="ignore")
        except Exception:
            continue

        rel = str(f.relative_to(plugin_dir))

        # Check harness-specific home paths (e.g. ~/.claude, ~/.codex)
        matches = home_re.findall(text)
        if matches:
            home_path_count += len(matches)
            label = HARNESS_HOME_LABEL[native_harness]
            findings.append({
                "code": f"{harness_upper}_HOME_PATH",
                "kind": "harness",
                "severity": "error",
                "path": rel,
                "message": f"References {label} paths ({len(matches)} occurrences)",
            })

        # Check harness path-variable conventions
        for pv_re, pv_label in zip(path_var_res, path_var_labels, strict=True):
            if pv_re.search(text):
                findings.append({
                    "code": f"{harness_upper}_PLUGIN_CONVENTION",
                    "kind": "harness",
                    "severity": "warn",
                    "path": rel,
                    "message": f"Uses {pv_label} variable",
                })

        # Check for harness tool names in skill files
        if f.name.endswith(".md"):
            for tool in tool_names:
                if re.search(rf"\b{re.escape(tool)}\b", text):
                    native_tool_refs.add(tool)

    if native_tool_refs:
        harness_label = f"{native_harness.title()} tool"
        findings.append({
            "code": f"{harness_upper}_TOOL_NAME",
            "kind": "harness",
            "severity": "info",
            "path": "(multiple)",
            "message": f"References {harness_label} names: {', '.join(sorted(native_tool_refs))}",
        })

    result = {
        "findings": findings,
        "home_path_count": home_path_count,
        "native_tool_refs": sorted(native_tool_refs),
    }
    # Legacy aliases for callers that haven't been updated
    if native_harness == "claude":
        result["claude_home_count"] = home_path_count
        result["claude_tool_refs"] = result["native_tool_refs"]
    return result


def extract_tool_references(text: str, tool_names: set[str]) -> set[str]:
    """Extract likely tool references from skill text, avoiding generic prose false positives."""
    refs: set[str] = set()
    if not tool_names:
        return refs

    if text.startswith("---\n"):
        _, _, remainder = text.partition("---\n")
        frontmatter, sep, body = remainder.partition("\n---")
        if sep:
            in_allowed_tools = False
            for line in frontmatter.splitlines():
                if line.startswith("allowed-tools:"):
                    in_allowed_tools = True
                    continue
                if in_allowed_tools:
                    if not line.startswith("  - "):
                        in_allowed_tools = False
                        continue
                    tool = line.removeprefix("  - ").strip()
                    if tool in tool_names:
                        refs.add(tool)
            text = body

    patterns = [
        r"`{tool}`",
        r"\b(?:Use|Call|Run|Invoke)\s+`?{tool}`?\b",
        r"\b`?{tool}`?\s+tool\b",
        r"\btools?\s+(?:such as|like)\s+`?{tool}`?\b",
    ]
    for tool in tool_names:
        for pattern in patterns:
            if re.search(pattern.format(tool=re.escape(tool)), text):
                refs.add(tool)
                break

    return refs


def detect_native_harness(plugin_dir: Path, declared: str | None = None) -> str:
    """Determine the native harness for a plugin.

    Priority: declared (from sources.json) > content signals > default ("claude").
    Emits a warning when falling back to the default.
    """
    if declared and declared in NATIVE_HARNESSES:
        return declared
    if declared and declared not in NATIVE_HARNESSES:
        warnings.warn(
            f"{plugin_dir.name}: unknown native_harness {declared!r}; "
            f"falling back to {DEFAULT_NATIVE_HARNESS!r}",
            stacklevel=2,
        )

    # Content-signal detection: only use path vars and home paths — strong,
    # unambiguous signals. Tool names are too generic (especially copilot's
    # lowercase names like "edit", "view", "bash") and cause false positives.
    scores: dict[str, int] = dict.fromkeys(NATIVE_HARNESSES, 0)

    for f in plugin_dir.rglob("*"):
        if not f.is_file():
            continue
        if f.suffix in {".json", ".png", ".jpg", ".gif", ".ico", ".db", ".sqlite"}:
            continue
        if f.name.upper().startswith("README"):
            continue
        try:
            text = f.read_text(errors="ignore")
        except Exception:
            continue

        for harness in NATIVE_HARNESSES:
            # Path vars are strong signals
            for pv_re in HARNESS_PATH_VAR_RES[harness]:
                if pv_re.search(text):
                    scores[harness] += 5

            # Home paths are strong signals
            if HARNESS_HOME_RE[harness].search(text):
                scores[harness] += 5

    # Find harness with highest score, requiring at least one signal
    best, best_score = max(scores.items(), key=lambda kv: kv[1])
    if best_score > 0 and best != DEFAULT_NATIVE_HARNESS:
        return best

    if best_score == 0:
        warnings.warn(
            f"{plugin_dir.name}: no native harness signals found; "
            f"defaulting to {DEFAULT_NATIVE_HARNESS!r}",
            stacklevel=2,
        )
    return DEFAULT_NATIVE_HARNESS


def classify_package(
    *,
    native_harness: str = DEFAULT_NATIVE_HARNESS,
    has_hooks: bool,
    home_path_count: int,
    native_tool_refs: list[str],
    has_commands: bool,
    has_agents: bool,
    has_inline_hooks: bool,
) -> tuple[str, str, str, str]:
    """Return (portability_class, claude_status, codex_status, copilot_status).

    ``native_tool_refs`` contains tool names in the *native_harness* format.
    For claude-native skills these are Claude tool names; for codex-native they
    are codex tool names, etc.
    """
    all_harnesses = ["claude", "codex", "copilot"]
    other_harnesses = [h for h in all_harnesses if h != native_harness]

    # Hooks, inline hooks, and home-path references make a skill harness-specific
    # (these are currently modelled only for claude-native skills)
    if has_hooks or has_inline_hooks or home_path_count > 0:
        statuses = {native_harness: "native"}
        for h in other_harnesses:
            statuses[h] = "unsupported"
        return ("harness-specific", statuses["claude"], statuses["codex"], statuses["copilot"])

    # Commands/agents exist in both harnesses conceptually but packaging differs
    if has_commands or has_agents:
        statuses = {native_harness: "native"}
        for h in other_harnesses:
            statuses[h] = "blocked"
        return ("adaptable", statuses["claude"], statuses["codex"], statuses["copilot"])

    if native_tool_refs:
        statuses = {native_harness: "native"}
        for h in other_harnesses:
            adaptable, _ = can_adapt_for_harness(
                native_tool_refs, source_harness=native_harness, target_harness=h,
            )
            statuses[h] = "generated" if adaptable else "blocked"
        return ("adaptable", statuses["claude"], statuses["codex"], statuses["copilot"])

    # Pure markdown skill, no harness coupling -> agnostic
    statuses = {native_harness: "native"}
    for h in other_harnesses:
        statuses[h] = "generated"
    return ("agnostic", statuses["claude"], statuses["codex"], statuses["copilot"])


def determine_package_type(
    has_hooks: bool, has_commands: bool, has_agents: bool, has_deps: bool,
) -> str:
    if has_hooks or has_deps or has_commands or has_agents:
        return "full-plugin"
    return "skill-wrapper"


def compute_tool_risk(tools: list[str]) -> dict:
    if not tools:
        return {"declared_tools": [], "risk_level": "low", "reasons": []}

    reasons = []
    high_risk_tools = {"Bash", "Write", "NotebookEdit"}
    medium_risk_tools = {"Edit", "Agent", "WebSearch", "WebFetch"}

    for t in tools:
        if t in high_risk_tools:
            reasons.append(f"{t}: shell execution or file mutation")
        elif t in medium_risk_tools:
            reasons.append(f"{t}: indirect mutation or external access")

    has_high = any(t in high_risk_tools for t in tools)
    has_medium = any(t in medium_risk_tools for t in tools)

    if has_high:
        level = "high" if len([t for t in tools if t in high_risk_tools]) > 1 else "medium"
    elif has_medium:
        level = "medium"
    else:
        level = "low"

    return {"declared_tools": sorted(tools), "risk_level": level, "reasons": reasons}


def build_package_record(
    name: str,
    source_info: dict,
    marketplace_entry: dict,
    plugin_manifest: dict,
    native_harness: str = DEFAULT_NATIVE_HARNESS,
) -> dict:
    plugin_dir = REPO_ROOT / f"plugins-{native_harness}" / name

    # File structure detection
    has_skill = (plugin_dir / "skills").is_dir()
    has_manifest = (plugin_dir / ".claude-plugin" / "plugin.json").is_file()
    has_hooks = (plugin_dir / "hooks").is_dir()
    has_commands = (plugin_dir / "commands").is_dir()
    has_agents = (plugin_dir / "agents").is_dir()
    has_templates = any(plugin_dir.rglob("resources/*")) if (plugin_dir / "skills").is_dir() else False

    executables = find_executable_files(plugin_dir)
    dep_files = find_dependency_files(plugin_dir)
    scan = scan_text_files(plugin_dir, native_harness)

    has_inline_hooks = False
    for skill_md in plugin_dir.rglob("SKILL.md"):
        try:
            text = skill_md.read_text(errors="ignore")
        except Exception:
            continue
        if text.startswith("---\n"):
            _, _, remainder = text.partition("---\n")
            frontmatter, sep, _body = remainder.partition("\n---")
            if sep and re.search(r"(?m)^hooks\s*:", frontmatter):
                has_inline_hooks = True
                scan["findings"].append({
                    "code": "INLINE_SKILL_HOOKS",
                    "kind": "harness",
                    "severity": "error",
                    "path": str(skill_md.relative_to(plugin_dir)),
                    "message": "Uses inline skill hooks/frontmatter not supported as a neutral portable skill feature",
                })

    portability_class, claude_status, codex_status, copilot_status = classify_package(
        native_harness=native_harness,
        has_hooks=has_hooks,
        home_path_count=scan["home_path_count"],
        native_tool_refs=scan["native_tool_refs"],
        has_commands=has_commands,
        has_agents=has_agents,
        has_inline_hooks=has_inline_hooks,
    )

    package_type = determine_package_type(has_hooks, has_commands, has_agents, bool(dep_files))
    tool_risk = compute_tool_risk(scan["native_tool_refs"])

    # Determine upstream type
    upstream_type = source_info.get("upstream_type", "plugin")

    # Build authors from marketplace or manifest
    authors = []
    for source in [marketplace_entry, plugin_manifest]:
        author = source.get("author")
        if author and isinstance(author, dict):
            entry = {"name": author["name"]}
            if "email" in author:
                entry["email"] = author["email"]
            if "url" in author:
                entry["url"] = author["url"]
            authors = [entry]
            break

    # Description — prefer marketplace, fall back to manifest
    description = marketplace_entry.get("description", plugin_manifest.get("description", ""))
    if description == "|":
        description = ""

    # Version
    version = marketplace_entry.get("version", plugin_manifest.get("version", "0.0.0"))

    # Verification state from sources.json (Codex's per-skill format)
    verification_data = source_info.get("verification", {})
    skills_verified = verification_data.get("skills", {})

    # Support basis — native harness is always "native", others depend on status
    def _support_basis(harness: str, status: str) -> str:
        if harness == native_harness:
            return "native"
        if status == "generated":
            return "generated"
        if status == "unsupported":
            return "unsupported"
        if harness == "claude":
            return "convention"
        return "unknown"

    support_basis = {
        "claude": _support_basis("claude", claude_status),
        "codex": _support_basis("codex", codex_status),
        "copilot": _support_basis("copilot", copilot_status),
    }

    def _gen_config(harness: str, status: str) -> dict:
        if harness == native_harness:
            return {"enabled": True, "mode": "native"}
        enabled = status in ("generated", "adapted")
        cfg: dict = {
            "enabled": enabled,
            "mode": "none" if status in ("unsupported", "blocked") else status,
        }
        if enabled:
            if harness == "codex":
                cfg["marketplace"] = {
                    "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                    "category": "Developer Tools",
                }
            elif harness == "copilot":
                cfg["install"] = {"target_dir": ".github/skills"}
        return cfg

    codex_gen = _gen_config("codex", codex_status)
    copilot_gen = _gen_config("copilot", copilot_status)
    claude_gen = _gen_config("claude", claude_status)

    # Adaptation hints
    hints = []
    if scan["native_tool_refs"]:
        hints.append(f"Map {native_harness.title()} tool names to neutral capabilities")
    if scan["home_path_count"] > 0:
        label = HARNESS_HOME_LABEL[native_harness]
        hints.append(f"Replace {label} path references with harness-neutral config")
    if has_hooks:
        hints.append("Hooks require harness-specific lifecycle — consider forking for other harnesses")
    if has_inline_hooks:
        hints.append("Inline skill hooks are harness-specific and should remain blocked outside Claude-style runtimes")
    if has_commands:
        hints.append("Slash commands need harness-specific packaging adaptation")
    if has_agents:
        hints.append("Agent definitions need harness-specific format adaptation")

    # Supported harnesses list
    supported = [native_harness]
    if native_harness != "claude" and claude_status in ("generated", "adapted", "native"):
        supported.append("claude")
    if native_harness != "codex" and codex_status in ("generated", "adapted"):
        supported.append("codex")
    if native_harness != "copilot" and copilot_status in ("generated", "adapted"):
        supported.append("copilot")

    # Findings for packaging
    packaging_findings = []
    if has_skill:
        packaging_findings.append({
            "code": "HAS_SKILL_MD", "kind": "packaging", "severity": "info",
            "path": "skills/", "message": "Contains skill definitions",
        })
    if has_manifest:
        packaging_findings.append({
            "code": "HAS_CLAUDE_PLUGIN_MANIFEST", "kind": "packaging", "severity": "info",
            "path": ".claude-plugin/plugin.json", "message": "Has Claude plugin manifest (convention)",
        })
    if has_hooks:
        packaging_findings.append({
            "code": "HAS_HOOKS_JSON", "kind": "packaging", "severity": "info",
            "path": "hooks/", "message": "Contains hook definitions",
        })
    if has_commands:
        packaging_findings.append({
            "code": "HAS_COMMANDS_DIR", "kind": "packaging", "severity": "info",
            "path": "commands/", "message": "Contains slash command definitions",
        })
    if has_agents:
        packaging_findings.append({
            "code": "HAS_AGENTS_DIR", "kind": "packaging", "severity": "info",
            "path": "agents/", "message": "Contains agent definitions",
        })

    # Risk findings
    risk_findings = []
    if executables:
        risk_findings.append({
            "code": "EXECUTABLE_CODE_PRESENT", "kind": "risk", "severity": "warn",
            "path": ", ".join(executables[:3]),
            "message": f"Contains {len(executables)} executable file(s)",
        })
    if dep_files:
        risk_findings.append({
            "code": "DEPENDENCY_FILE_PRESENT", "kind": "risk", "severity": "warn",
            "path": ", ".join(dep_files),
            "message": "Contains dependency manifest(s)",
        })

    all_findings = packaging_findings + scan["findings"] + risk_findings

    return {
        "name": name,
        "version": version,
        "description": description,
        "authors": authors if authors else None,
        "upstream": {
            "repo": source_info["upstream_repo"],
            "path": source_info["upstream_path"],
            "ref": source_info["upstream_ref"],
            "type": upstream_type,
            "last_synced_commit": source_info["last_synced_commit"],
            "last_checked": source_info["last_checked"],
        },
        "source_model": "upstream-mirror",
        "canonical_harness": native_harness,
        "package_type": package_type,
        "files": {
            "has_skill": has_skill,
            "has_plugin_manifest": has_manifest,
            "has_hooks": has_hooks,
            "has_commands": has_commands,
            "has_agents": has_agents,
            "has_templates": has_templates,
        },
        "risk": {
            "has_executable_code": bool(executables),
            "dependency_files": dep_files,
            "tool_risk": tool_risk,
        },
        "compatibility": {
            "assessment_version": ASSESSMENT_VERSION,
            "portability_class": portability_class,
            "supported_harnesses": supported,
            "support_basis": support_basis,
            "status_by_harness": {
                "claude": claude_status,
                "codex": codex_status,
                "copilot": copilot_status,
            },
            "findings": all_findings,
            "adaptation_hints": hints if hints else [],
        },
        "generation": {
            "claude": claude_gen,
            "codex": codex_gen,
            "copilot": copilot_gen,
        },
        "verification": {
            "reviewed": all(skills_verified.values()) if skills_verified else False,
            "skills": skills_verified,
        },
    }


def main() -> None:
    sources = load_json(REPO_ROOT / "sources.json")
    marketplace = load_json(REPO_ROOT / ".claude-plugin" / "marketplace.json")

    # Index marketplace entries by name
    mp_by_name = {}
    for entry in marketplace.get("plugins", []):
        mp_by_name[entry["name"]] = entry

    # Index plugin manifests from all harness-partitioned plugin dirs
    manifests = {}
    for plugins_dir in REPO_ROOT.glob("plugins-*"):
        if not plugins_dir.is_dir():
            continue
        for plugin_dir in plugins_dir.iterdir():
            if not plugin_dir.is_dir():
                continue
            manifest_path = plugin_dir / ".claude-plugin" / "plugin.json"
            if manifest_path.is_file():
                manifests[plugin_dir.name] = load_json(manifest_path)

    CATALOG_DIR.mkdir(parents=True, exist_ok=True)

    count = 0
    for name, info in sources["plugins"].items():
        mp_entry = mp_by_name.get(name, {})
        manifest = manifests.get(name, {})

        # Determine native harness:
        # 1. Declared in sources.json wins
        # 2. Infer from which plugins-{harness}/ dir the plugin lives in
        # 3. Content detection (path vars, home paths) as final fallback
        declared = info.get("native_harness")
        dir_implied: str | None = None
        plugin_dir: Path | None = None
        for h in NATIVE_HARNESSES:
            candidate = REPO_ROOT / f"plugins-{h}" / name
            if candidate.is_dir():
                plugin_dir = candidate
                dir_implied = h
                break
        if plugin_dir is None:
            plugin_dir = REPO_ROOT / f"plugins-{DEFAULT_NATIVE_HARNESS}" / name
            dir_implied = DEFAULT_NATIVE_HARNESS
        native_harness = detect_native_harness(plugin_dir, declared or dir_implied)

        record = build_package_record(name, info, mp_entry, manifest, native_harness)

        # Remove None authors
        if record["authors"] is None:
            del record["authors"]

        out_path = CATALOG_DIR / f"{name}.json"
        out_path.write_text(json.dumps(record, indent=2) + "\n")
        print(f"  {name}: {record['compatibility']['portability_class']} "
              f"(claude={record['compatibility']['status_by_harness']['claude']}, "
              f"codex={record['compatibility']['status_by_harness']['codex']})")
        count += 1

    print(f"\nBackfilled {count} packages to {CATALOG_DIR}")


if __name__ == "__main__":
    main()
