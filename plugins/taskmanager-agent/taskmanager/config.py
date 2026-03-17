from pathlib import Path

import yaml

CONFIG_PATH = Path.home() / ".claude" / "taskmanager.yaml"


def load_config() -> dict:
    """Load config from disk. Returns empty dict if file doesn't exist."""
    if not CONFIG_PATH.exists():
        return {}
    return yaml.safe_load(CONFIG_PATH.read_text()) or {}


def save_config(config: dict) -> None:
    """Write config to disk."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(yaml.dump(config, default_flow_style=False, sort_keys=False))
