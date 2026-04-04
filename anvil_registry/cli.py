"""Console entry points for repo-local registry scripts."""

from __future__ import annotations

import runpy
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"


def _run(script_name: str) -> None:
    runpy.run_path(str(SCRIPTS_DIR / script_name), run_name="__main__")


def assess_package() -> None:
    _run("assess-package.py")


def assess() -> None:
    _run("assess.py")


def backfill_catalog() -> None:
    _run("backfill-catalog.py")


def catalog() -> None:
    _run("catalog.py")


def generate_claude() -> None:
    _run("generate-claude.py")


def generate_codex() -> None:
    _run("generate-codex.py")


def generate_copilot() -> None:
    _run("generate-copilot.py")


def generate_marketplace() -> None:
    _run("generate-marketplace.py")


def sync_check() -> None:
    _run("sync-check.py")


def sync_claude() -> None:
    _run("sync-claude.py")


def sync_codex() -> None:
    _run("sync-codex.py")


def sync_copilot() -> None:
    _run("sync-copilot.py")


def validate_generated() -> None:
    _run("validate-generated.py")
