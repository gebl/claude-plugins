"""One-time script to backfill catalog/packages/ from existing metadata sources."""

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGINS_DIR = REPO_ROOT / "plugins"
CATALOG_DIR = REPO_ROOT / "catalog" / "packages"

ASSESSMENT_VERSION = "2026-04-03.1"

# Claude tool names that indicate harness coupling
CLAUDE_TOOLS = {
    "Read", "Write", "Edit", "Bash", "Grep", "Glob", "Agent",
    "AskUserQuestion", "WebSearch", "WebFetch", "TodoRead", "TodoWrite",
    "NotebookEdit", "TaskCreate", "TaskUpdate", "EnterPlanMode",
}

CLAUDE_HOME_RE = re.compile(r"~/\.claude\b")
CLAUDE_PLUGIN_ROOT_RE = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}")
CLAUDE_SKILL_DIR_RE = re.compile(r"\$\{CLAUDE_SKILL_DIR\}")

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


def scan_text_files(plugin_dir: Path) -> dict:
    """Scan all text files for harness-specific references."""
    findings = []
    claude_home_count = 0
    claude_tool_refs = set()

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

        # Check ~/.claude paths
        matches = CLAUDE_HOME_RE.findall(text)
        if matches:
            claude_home_count += len(matches)
            findings.append({
                "code": "CLAUDE_HOME_PATH",
                "kind": "harness",
                "severity": "error",
                "path": rel,
                "message": f"References ~/.claude paths ({len(matches)} occurrences)",
            })

        # Check ${CLAUDE_PLUGIN_ROOT}
        if CLAUDE_PLUGIN_ROOT_RE.search(text):
            findings.append({
                "code": "CLAUDE_PLUGIN_CONVENTION",
                "kind": "harness",
                "severity": "warn",
                "path": rel,
                "message": "Uses ${CLAUDE_PLUGIN_ROOT} variable",
            })

        # Check ${CLAUDE_SKILL_DIR}
        if CLAUDE_SKILL_DIR_RE.search(text):
            findings.append({
                "code": "CLAUDE_PLUGIN_CONVENTION",
                "kind": "harness",
                "severity": "warn",
                "path": rel,
                "message": "Uses ${CLAUDE_SKILL_DIR} variable",
            })

        # Check for Claude tool names in SKILL.md frontmatter or body
        if f.name.endswith(".md"):
            for tool in CLAUDE_TOOLS:
                # Match tool names that look like tool references, not prose
                pattern = rf"\b{tool}\b"
                if re.search(pattern, text):
                    claude_tool_refs.add(tool)

    if claude_tool_refs:
        findings.append({
            "code": "CLAUDE_TOOL_NAME",
            "kind": "harness",
            "severity": "info",
            "path": "(multiple)",
            "message": f"References Claude tool names: {', '.join(sorted(claude_tool_refs))}",
        })

    return {
        "findings": findings,
        "claude_home_count": claude_home_count,
        "claude_tool_refs": sorted(claude_tool_refs),
    }


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


def classify_package(
    *,
    has_hooks: bool,
    claude_home_count: int,
    claude_tool_refs: list[str],
    has_commands: bool,
    has_agents: bool,
    has_inline_hooks: bool,
) -> tuple[str, str, str, str]:
    """Return (portability_class, claude_status, codex_status, copilot_status)."""
    # Hook-driven or has ~/.claude paths -> harness-specific
    if has_hooks or has_inline_hooks or claude_home_count > 0:
        return "harness-specific", "native", "unsupported", "unsupported"

    # Has commands or agents (Claude-specific packaging concepts)
    if has_commands or has_agents:
        # Commands/agents exist in both harnesses conceptually, but
        # the packaging format differs. Adaptable if no other blockers.
        if not claude_tool_refs:
            return "adaptable", "native", "blocked", "blocked"
        return "adaptable", "native", "blocked", "blocked"

    # Pure skill with Claude tool names -> adaptable (tool names can be mapped)
    if claude_tool_refs:
        return "adaptable", "native", "blocked", "blocked"

    # Pure markdown skill, no harness coupling -> agnostic
    return "agnostic", "native", "generated", "generated"


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
) -> dict:
    plugin_dir = PLUGINS_DIR / name

    # File structure detection
    has_skill = (plugin_dir / "skills").is_dir()
    has_manifest = (plugin_dir / ".claude-plugin" / "plugin.json").is_file()
    has_hooks = (plugin_dir / "hooks").is_dir()
    has_commands = (plugin_dir / "commands").is_dir()
    has_agents = (plugin_dir / "agents").is_dir()
    has_templates = any(plugin_dir.rglob("resources/*")) if (plugin_dir / "skills").is_dir() else False

    executables = find_executable_files(plugin_dir)
    dep_files = find_dependency_files(plugin_dir)
    scan = scan_text_files(plugin_dir)

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
        has_hooks=has_hooks,
        claude_home_count=scan["claude_home_count"],
        claude_tool_refs=scan["claude_tool_refs"],
        has_commands=has_commands,
        has_agents=has_agents,
        has_inline_hooks=has_inline_hooks,
    )

    package_type = determine_package_type(has_hooks, has_commands, has_agents, bool(dep_files))
    tool_risk = compute_tool_risk(scan["claude_tool_refs"])

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

    # Support basis
    support_basis = {
        "claude": "convention",  # .claude-plugin is convention-only per plan
        "codex": "unsupported" if codex_status == "unsupported" else "unknown",
        "copilot": "generated" if copilot_status == "generated" else "unsupported" if copilot_status == "unsupported" else "unknown",
    }

    # Codex generation config
    codex_gen = {
        "enabled": codex_status in ("generated", "adapted"),
        "mode": "none" if codex_status in ("unsupported", "blocked") else codex_status,
    }
    if codex_gen["enabled"]:
        codex_gen["marketplace"] = {
            "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
            "category": "Developer Tools",
        }

    copilot_gen = {
        "enabled": copilot_status in ("generated", "adapted"),
        "mode": "none" if copilot_status in ("unsupported", "blocked") else copilot_status,
    }
    if copilot_gen["enabled"]:
        copilot_gen["install"] = {"target_dir": ".agents/skills"}

    # Adaptation hints
    hints = []
    if scan["claude_tool_refs"]:
        hints.append("Map Claude tool names to neutral capabilities")
    if scan["claude_home_count"] > 0:
        hints.append("Replace ~/.claude path references with harness-neutral config")
    if has_hooks:
        hints.append("Hooks require harness-specific lifecycle — consider forking for other harnesses")
    if has_inline_hooks:
        hints.append("Inline skill hooks are harness-specific and should remain blocked outside Claude-style runtimes")
    if has_commands:
        hints.append("Slash commands need harness-specific packaging adaptation")
    if has_agents:
        hints.append("Agent definitions need harness-specific format adaptation")

    # Supported harnesses list
    supported = ["claude"]
    if codex_status in ("generated", "adapted"):
        supported.append("codex")
    if copilot_status in ("generated", "adapted"):
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
        "canonical_harness": "claude",
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
            "claude": {
                "enabled": True,
                "mode": "native",
            },
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

    # Index plugin manifests
    manifests = {}
    for plugin_dir in PLUGINS_DIR.iterdir():
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

        record = build_package_record(name, info, mp_entry, manifest)

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
