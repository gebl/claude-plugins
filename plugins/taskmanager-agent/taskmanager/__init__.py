"""taskmanager — backend-agnostic task management agent."""

from __future__ import annotations

import json
from pathlib import Path

_PLUGIN_JSON = Path(__file__).resolve().parent.parent / ".claude-plugin" / "plugin.json"


def get_version() -> str:
    """Read the plugin version from .claude-plugin/plugin.json."""
    data = json.loads(_PLUGIN_JSON.read_text())
    return data["version"]
