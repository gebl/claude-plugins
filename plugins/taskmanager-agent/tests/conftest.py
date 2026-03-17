import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
VENV_PYTHON = Path(__file__).parent.parent / "venv" / "bin" / "python"


@pytest.fixture
def run_script():
    """Run a Python script from the scripts/ directory."""

    def _run(name: str, *args: str, env_override: dict | None = None) -> subprocess.CompletedProcess:
        python = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable
        env = {**os.environ, **(env_override or {})}
        return subprocess.run(
            [python, str(SCRIPTS_DIR / name), *args],
            capture_output=True,
            text=True,
            env=env,
        )

    return _run
