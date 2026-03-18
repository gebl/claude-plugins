# Fix Plugin Bootstrap: Lockfile + Verification

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `tm-health` run cleanly on a fresh session by fixing the package install and verification.

**Architecture:** The dev repo's `uv.lock` is already correct (`editable`), but the cached plugin copy has a stale lockfile (`virtual`). Two code fixes needed: (1) Fix the verification command in `tm-health.md` so it tests the way scripts actually run (via a script file, not `python -c` which masks the bug via CWD). (2) Harden the SessionStart hook with a post-sync smoke test. After code changes, update the cached plugin copy.

**Tech Stack:** uv, Python packaging (hatchling), shell

---

## Root Cause

When `uv.lock` has `source = { virtual = "." }`, `uv sync` installs dependencies but NOT the project itself. Scripts fail with `ModuleNotFoundError` because `sys.path` doesn't include the project root when running `python scripts/foo.py`.

The verification in Step 0 of `tm-health.md` uses `python -c "from taskmanager..."` which passes by accident — `-c` mode adds CWD to `sys.path[0]`, so `taskmanager/` is found as a directory in CWD. This false positive hides the real failure.

---

### Task 1: Fix verification command in tm-health.md

**Files:**
- Modify: `commands/tm-health.md` (Step 0, verification command at line ~48)

- [ ] **Step 1: Update the verification command**

In `commands/tm-health.md`, Step 0 item 3, change the verification from:

```bash
${CLAUDE_PLUGIN_ROOT}/.venv/bin/python -c "from taskmanager.backends import get_backend; print('OK')"
```

to:

```bash
${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_get_user.py --help
```

This tests the actual import path that scripts use (`sys.path[0]` = `scripts/` directory), so a broken install cannot pass by accident.

Also update the failure message to match: "If this fails after `uv sync` succeeded, the `taskmanager` package was not installed — check that `uv.lock` contains `source = { editable = \".\" }` for the taskmanager-agent entry."

- [ ] **Step 2: Verify tm-health.md is coherent**

Read the updated Step 0 section and confirm the three sub-steps (check uv, run uv sync, verify) still flow logically.

- [ ] **Step 3: Commit**

```bash
git add commands/tm-health.md
git commit -m "Fix tm-health Step 0 verification to catch install failures"
```

---

### Task 2: Harden SessionStart hook verification

**Files:**
- Modify: `.claude-plugin/hooks.json`

- [ ] **Step 1: Update the hook command**

The current hook runs `uv sync --frozen --quiet` and swallows failures. Add a post-sync verification that tests the actual import path:

```json
"command": "if ! command -v uv >/dev/null 2>&1; then echo 'ERROR: taskmanager-agent requires uv (Python package manager). Install it: curl -LsSf https://astral.sh/uv/install.sh | sh — then restart your session.'; exit 1; fi && cd ${CLAUDE_PLUGIN_ROOT} && uv sync --frozen --quiet 2>&1 && ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python ${CLAUDE_PLUGIN_ROOT}/scripts/tm_get_user.py --help >/dev/null 2>&1 || echo 'WARNING: taskmanager-agent: Python environment setup incomplete. Run /tm-health to repair.'"
```

Key change: after `uv sync` succeeds, run `tm_get_user.py --help` as a smoke test. If either step fails, emit a warning.

- [ ] **Step 2: Test the hook command manually**

Run the full command from a shell to verify it works:

```bash
cd /home/gabe/Projects/taskmanager-agent && if ! command -v uv >/dev/null 2>&1; then echo 'ERROR'; exit 1; fi && uv sync --frozen --quiet 2>&1 && .venv/bin/python scripts/tm_get_user.py --help >/dev/null 2>&1 || echo 'WARNING: incomplete'
```

Expected: silent success (no output).

- [ ] **Step 3: Commit**

```bash
git add .claude-plugin/hooks.json
git commit -m "Add post-sync smoke test to SessionStart hook"
```

---

### Task 3: Update tm-health Step 0 to use `uv sync` (not `--frozen`) for repair resilience

**Files:**
- Modify: `commands/tm-health.md` (Step 0, item 2)

- [ ] **Step 1: Change `uv sync --frozen` to `uv sync` in Step 0 item 2**

The SessionStart hook uses `--frozen` for speed (no lockfile resolution). But tm-health is the *repair* path — if the lockfile is stale, `--frozen` will fail. Change Step 0 item 2 from:

```bash
cd ${CLAUDE_PLUGIN_ROOT} && uv sync --frozen
```

to:

```bash
cd ${CLAUDE_PLUGIN_ROOT} && uv sync
```

This allows tm-health to self-heal even if dependencies changed.

- [ ] **Step 2: Commit**

```bash
git add commands/tm-health.md
git commit -m "Use uv sync without --frozen in tm-health repair path"
```

---

### Task 4: Update cached plugin copy

- [ ] **Step 1: Copy updated files to the cache**

```bash
cp uv.lock commands/tm-health.md .claude-plugin/hooks.json to the cache at:
~/.claude/plugins/cache/anvil/taskmanager-agent/0.1.0/
```

Specifically:
```bash
CACHE=~/.claude/plugins/cache/anvil/taskmanager-agent/0.1.0
cp uv.lock "$CACHE/uv.lock"
cp commands/tm-health.md "$CACHE/commands/tm-health.md"
cp .claude-plugin/hooks.json "$CACHE/.claude-plugin/hooks.json"
```

- [ ] **Step 2: Clean the cached venv and re-sync**

```bash
rm -rf "$CACHE/.venv"
cd "$CACHE" && uv sync --frozen
```

- [ ] **Step 3: Verify scripts work from the cache**

```bash
$CACHE/.venv/bin/python $CACHE/scripts/tm_get_user.py --help
```

Expected: help text printed, exit 0.
