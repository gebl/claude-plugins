# /// script
# requires-python = ">=3.12"
# ///
"""Reusable assessment engine for package compatibility analysis.

Scans plugin directories, applies rules from catalog/rules/, and produces
structured compatibility assessments for the neutral catalog.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGINS_DIR = REPO_ROOT / "plugins"
RULES_DIR = REPO_ROOT / "catalog" / "rules"
SUPPRESSIONS_DIR = REPO_ROOT / "catalog" / "security" / "suppressions"

ASSESSMENT_VERSION = "2026-04-03.2"

SKIP_EXTENSIONS = {".json", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".db", ".sqlite", ".woff", ".woff2", ".ttf"}
EXECUTABLE_EXTENSIONS = {".py", ".sh", ".bash", ".zsh", ".js", ".ts", ".rb", ".pl"}
DEPENDENCY_FILENAMES = {"requirements.txt", "pyproject.toml", "package.json", "go.mod", "Cargo.toml", "Gemfile"}


# --- Data structures ---


@dataclass
class Finding:
    code: str
    kind: str  # packaging, portability, harness, risk
    severity: str  # info, warn, error
    path: str
    message: str
    suppressed: bool = False

    def to_dict(self) -> dict[str, str | bool]:
        d: dict[str, str | bool] = {
            "code": self.code,
            "kind": self.kind,
            "severity": self.severity,
            "path": self.path,
            "message": self.message,
        }
        if self.suppressed:
            d["suppressed"] = True
        return d


@dataclass
class AssessmentResult:
    portability_class: str  # agnostic, adaptable, harness-specific, unknown
    status_by_harness: dict[str, str] = field(default_factory=dict)
    support_basis: dict[str, str] = field(default_factory=dict)
    supported_harnesses: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    adaptation_hints: list[str] = field(default_factory=list)
    # Detected structure
    files: dict[str, bool] = field(default_factory=dict)
    package_type: str = "skill-wrapper"
    risk: dict = field(default_factory=dict)
    # Internal tracking
    claude_tool_refs: list[str] = field(default_factory=list)
    claude_home_count: int = 0

    def to_compatibility_dict(self) -> dict:
        return {
            "assessment_version": ASSESSMENT_VERSION,
            "portability_class": self.portability_class,
            "supported_harnesses": self.supported_harnesses,
            "support_basis": self.support_basis,
            "status_by_harness": self.status_by_harness,
            "findings": [f.to_dict() for f in self.findings],
            "adaptation_hints": self.adaptation_hints,
        }


# --- Rule loading ---


def load_rules() -> dict:
    """Load all rule files from catalog/rules/."""
    rules = {}
    for rule_file in RULES_DIR.glob("*.json"):
        rules[rule_file.stem] = json.loads(rule_file.read_text())
    return rules


def load_harness_rules(harness: str) -> dict:
    """Load rules for a specific harness."""
    path = RULES_DIR / f"harness-{harness}.json"
    if path.exists():
        return json.loads(path.read_text())
    return {}


def load_capability_mappings() -> list[dict]:
    """Load capability mappings from transforms.json."""
    transforms_path = RULES_DIR / "transforms.json"
    if transforms_path.exists():
        data = json.loads(transforms_path.read_text())
        return data.get("capability_mappings", [])
    return []


# --- Suppression loading ---


def load_suppressions(package_name: str) -> list[dict]:
    """Load external suppressions for a package."""
    path = SUPPRESSIONS_DIR / f"{package_name}.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    return data.get("suppressions", [])


def matches_suppression(finding: Finding, suppression: dict) -> bool:
    """Check if a finding matches a suppression rule."""
    if finding.code != suppression.get("rule_id", ""):
        # Also check if the suppression rule_id is a prefix match for
        # the finding code (e.g. rule_id "claude-pipe-to-shell" matches
        # assessment code "EXECUTABLE_CODE_PRESENT" only if explicit)
        return False

    supp_path = suppression.get("path", "")
    if supp_path and supp_path not in finding.path:
        return False

    return True


def apply_suppressions(findings: list[Finding], suppressions: list[dict]) -> list[Finding]:
    """Apply suppressions to findings, marking matched ones as suppressed."""
    if not suppressions:
        return findings

    for finding in findings:
        for supp in suppressions:
            if matches_suppression(finding, supp):
                finding.suppressed = True
                break

    return findings


# --- Scanning passes ---


def detect_file_structure(plugin_dir: Path) -> dict[str, bool]:
    """Pass 1: Detect neutral components."""
    has_skill = (plugin_dir / "skills").is_dir()
    return {
        "has_skill": has_skill,
        "has_plugin_manifest": (plugin_dir / ".claude-plugin" / "plugin.json").is_file(),
        "has_hooks": (plugin_dir / "hooks").is_dir(),
        "has_commands": (plugin_dir / "commands").is_dir(),
        "has_agents": (plugin_dir / "agents").is_dir(),
        "has_templates": bool(has_skill and any(plugin_dir.rglob("resources/*"))),
    }


def find_executable_files(plugin_dir: Path) -> list[str]:
    """Find files with executable extensions."""
    return sorted(
        str(f.relative_to(plugin_dir))
        for f in plugin_dir.rglob("*")
        if f.is_file() and f.suffix in EXECUTABLE_EXTENSIONS
    )


def find_dependency_files(plugin_dir: Path) -> list[str]:
    """Find dependency manifests."""
    return sorted(
        str(f.relative_to(plugin_dir))
        for f in plugin_dir.rglob("*")
        if f.is_file() and f.name in DEPENDENCY_FILENAMES
    )


def scan_harness_bindings(plugin_dir: Path, claude_rules: dict) -> tuple[list[Finding], int, list[str]]:
    """Pass 2: Detect harness-specific bindings using rules."""
    findings: list[Finding] = []
    claude_home_count = 0
    claude_tool_refs: set[str] = set()

    # Build patterns from rules
    claude_home_re = re.compile(r"~/\.claude\b")
    plugin_root_re = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}")
    skill_dir_re = re.compile(r"\$\{CLAUDE_SKILL_DIR\}")

    tool_names = set()
    for rule in claude_rules.get("rules", []):
        if rule["code"] == "CLAUDE_TOOL_NAME":
            tool_names = set(rule.get("tool_names", []))

    for f in plugin_dir.rglob("*"):
        if not f.is_file():
            continue
        if f.suffix in SKIP_EXTENSIONS:
            continue
        if f.name.upper().startswith("README"):
            continue

        try:
            text = f.read_text(errors="ignore")
        except Exception:
            continue

        rel = str(f.relative_to(plugin_dir))

        # ~/.claude paths
        matches = claude_home_re.findall(text)
        if matches:
            claude_home_count += len(matches)
            findings.append(Finding(
                code="CLAUDE_HOME_PATH",
                kind="harness",
                severity="error",
                path=rel,
                message=f"References ~/.claude paths ({len(matches)} occurrences)",
            ))

        # ${CLAUDE_PLUGIN_ROOT}
        if plugin_root_re.search(text):
            findings.append(Finding(
                code="CLAUDE_PLUGIN_CONVENTION",
                kind="harness",
                severity="warn",
                path=rel,
                message="Uses ${CLAUDE_PLUGIN_ROOT} variable",
            ))

        # ${CLAUDE_SKILL_DIR}
        if skill_dir_re.search(text):
            findings.append(Finding(
                code="CLAUDE_PLUGIN_CONVENTION",
                kind="harness",
                severity="warn",
                path=rel,
                message="Uses ${CLAUDE_SKILL_DIR} variable",
            ))

        # Claude tool names in markdown files
        if f.name.endswith(".md") and tool_names:
            for tool in tool_names:
                if re.search(rf"\b{tool}\b", text):
                    claude_tool_refs.add(tool)

    if claude_tool_refs:
        findings.append(Finding(
            code="CLAUDE_TOOL_NAME",
            kind="harness",
            severity="info",
            path="(multiple)",
            message=f"References Claude tool names: {', '.join(sorted(claude_tool_refs))}",
        ))

    return findings, claude_home_count, sorted(claude_tool_refs)


def build_packaging_findings(files: dict[str, bool]) -> list[Finding]:
    """Generate packaging-level findings from file structure."""
    findings = []
    mapping = {
        "has_skill": ("HAS_SKILL_MD", "skills/", "Contains skill definitions"),
        "has_plugin_manifest": ("HAS_CLAUDE_PLUGIN_MANIFEST", ".claude-plugin/plugin.json", "Has Claude plugin manifest (convention)"),
        "has_hooks": ("HAS_HOOKS_JSON", "hooks/", "Contains hook definitions"),
        "has_commands": ("HAS_COMMANDS_DIR", "commands/", "Contains slash command definitions"),
        "has_agents": ("HAS_AGENTS_DIR", "agents/", "Contains agent definitions"),
    }
    for key, (code, path, msg) in mapping.items():
        if files.get(key):
            findings.append(Finding(code=code, kind="packaging", severity="info", path=path, message=msg))
    return findings


def build_risk_findings(executables: list[str], dep_files: list[str]) -> list[Finding]:
    """Generate risk-level findings."""
    findings = []
    if executables:
        findings.append(Finding(
            code="EXECUTABLE_CODE_PRESENT",
            kind="risk",
            severity="warn",
            path=", ".join(executables[:3]),
            message=f"Contains {len(executables)} executable file(s)",
        ))
    if dep_files:
        findings.append(Finding(
            code="DEPENDENCY_FILE_PRESENT",
            kind="risk",
            severity="warn",
            path=", ".join(dep_files),
            message="Contains dependency manifest(s)",
        ))
    return findings


# --- Classification (Pass 3) ---


def classify_portability(
    *,
    has_hooks: bool,
    claude_home_count: int,
    claude_tool_refs: list[str],
    has_commands: bool,
    has_agents: bool,
) -> tuple[str, str, str]:
    """Return (portability_class, claude_status, codex_status)."""
    if has_hooks or claude_home_count > 0:
        return "harness-specific", "native", "unsupported"

    if has_commands or has_agents or claude_tool_refs:
        return "adaptable", "native", "blocked"

    return "agnostic", "native", "generated"


def determine_package_type(files: dict[str, bool], has_deps: bool) -> str:
    if files.get("has_hooks") or has_deps or files.get("has_commands") or files.get("has_agents"):
        return "full-plugin"
    return "skill-wrapper"


def compute_tool_risk(tools: list[str]) -> dict:
    if not tools:
        return {"declared_tools": [], "risk_level": "low", "reasons": []}

    high_risk = {"Bash", "Write", "NotebookEdit"}
    medium_risk = {"Edit", "Agent", "WebSearch", "WebFetch"}

    reasons = []
    for t in tools:
        if t in high_risk:
            reasons.append(f"{t}: shell execution or file mutation")
        elif t in medium_risk:
            reasons.append(f"{t}: indirect mutation or external access")

    if sum(1 for t in tools if t in high_risk) > 1:
        level = "high"
    elif any(t in high_risk for t in tools):
        level = "medium"
    elif any(t in medium_risk for t in tools):
        level = "medium"
    else:
        level = "low"

    return {"declared_tools": sorted(tools), "risk_level": level, "reasons": reasons}


def build_adaptation_hints(
    *,
    claude_tool_refs: list[str],
    claude_home_count: int,
    has_hooks: bool,
    has_commands: bool,
    has_agents: bool,
) -> list[str]:
    hints = []
    if claude_tool_refs:
        hints.append("Map Claude tool names to neutral capabilities")
    if claude_home_count > 0:
        hints.append("Replace ~/.claude path references with harness-neutral config")
    if has_hooks:
        hints.append("Hooks require harness-specific lifecycle — consider forking for other harnesses")
    if has_commands:
        hints.append("Slash commands need harness-specific packaging adaptation")
    if has_agents:
        hints.append("Agent definitions need harness-specific format adaptation")
    return hints


# --- Main assessment entry point ---


def assess_package(name: str) -> AssessmentResult:
    """Run full assessment on a single package. Returns structured result."""
    plugin_dir = PLUGINS_DIR / name
    if not plugin_dir.is_dir():
        raise FileNotFoundError(f"Plugin directory not found: {plugin_dir}")

    claude_rules = load_harness_rules("claude")
    suppressions = load_suppressions(name)

    # Pass 1: Detect neutral components
    files = detect_file_structure(plugin_dir)
    executables = find_executable_files(plugin_dir)
    dep_files = find_dependency_files(plugin_dir)

    # Pass 2: Detect harness-specific bindings
    harness_findings, claude_home_count, claude_tool_refs = scan_harness_bindings(plugin_dir, claude_rules)
    packaging_findings = build_packaging_findings(files)
    risk_findings = build_risk_findings(executables, dep_files)

    all_findings = packaging_findings + harness_findings + risk_findings

    # Apply external suppressions
    all_findings = apply_suppressions(all_findings, suppressions)

    # Pass 3: Resolve status per harness
    portability_class, claude_status, codex_status = classify_portability(
        has_hooks=files["has_hooks"],
        claude_home_count=claude_home_count,
        claude_tool_refs=claude_tool_refs,
        has_commands=files["has_commands"],
        has_agents=files["has_agents"],
    )

    support_basis = {
        "claude": "convention",
        "codex": "unsupported" if codex_status == "unsupported" else "unknown",
    }

    supported = ["claude"]
    if codex_status in ("generated", "adapted"):
        supported.append("codex")

    package_type = determine_package_type(files, bool(dep_files))
    tool_risk = compute_tool_risk(claude_tool_refs)

    hints = build_adaptation_hints(
        claude_tool_refs=claude_tool_refs,
        claude_home_count=claude_home_count,
        has_hooks=files["has_hooks"],
        has_commands=files["has_commands"],
        has_agents=files["has_agents"],
    )

    return AssessmentResult(
        portability_class=portability_class,
        status_by_harness={"claude": claude_status, "codex": codex_status},
        support_basis=support_basis,
        supported_harnesses=supported,
        findings=all_findings,
        adaptation_hints=hints,
        files=files,
        package_type=package_type,
        risk={
            "has_executable_code": bool(executables),
            "dependency_files": dep_files,
            "tool_risk": tool_risk,
        },
        claude_tool_refs=claude_tool_refs,
        claude_home_count=claude_home_count,
    )


def update_package_record(name: str, result: AssessmentResult) -> dict:
    """Read an existing catalog record and update its compatibility/files/risk sections."""
    pkg_path = REPO_ROOT / "catalog" / "packages" / f"{name}.json"
    if not pkg_path.exists():
        raise FileNotFoundError(f"Package record not found: {pkg_path}")

    record = json.loads(pkg_path.read_text())

    record["compatibility"] = result.to_compatibility_dict()
    record["files"] = result.files
    record["package_type"] = result.package_type
    record["risk"] = result.risk

    # Update generation state based on new assessment
    codex_status = result.status_by_harness.get("codex", "unknown")
    codex_gen = {
        "enabled": codex_status in ("generated", "adapted"),
        "mode": "none" if codex_status in ("unsupported", "blocked") else codex_status,
    }
    if codex_gen["enabled"]:
        codex_gen["marketplace"] = {
            "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
            "category": "Developer Tools",
        }
    record["generation"]["codex"] = codex_gen

    pkg_path.write_text(json.dumps(record, indent=2) + "\n")
    return record


def list_all_packages() -> list[str]:
    """Return names of all packages in the catalog."""
    pkg_dir = REPO_ROOT / "catalog" / "packages"
    return sorted(p.stem for p in pkg_dir.glob("*.json"))
