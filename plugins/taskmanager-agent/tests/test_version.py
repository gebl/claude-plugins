"""Tests for version helper and Claude version verification."""

from __future__ import annotations

import json

import pytest

from taskmanager import get_version
from taskmanager.daemon.runner import verify_claude_plugin_version


class TestGetVersion:
    def test_returns_version_string(self):
        version = get_version()
        # Should be a semver-like string
        parts = version.split(".")
        assert len(parts) == 3
        assert all(p.isdigit() for p in parts)

    def test_matches_plugin_json(self, tmp_path):
        """Verify get_version reads from plugin.json correctly."""
        version = get_version()
        from taskmanager import _PLUGIN_JSON

        data = json.loads(_PLUGIN_JSON.read_text())
        assert version == data["version"]


def _write_registry(tmp_path, plugins_dict):
    registry = tmp_path / ".claude" / "plugins" / "installed_plugins.json"
    registry.parent.mkdir(parents=True)
    registry.write_text(json.dumps({"version": 2, "plugins": plugins_dict}))
    return registry


class TestVerifyClaudePluginVersion:
    def test_returns_version_on_success(self, tmp_path, monkeypatch):
        _write_registry(tmp_path, {
            "taskmanager-agent@anvil": [{"version": "0.6.9"}],
        })
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        assert verify_claude_plugin_version() == "0.6.9"

    def test_returns_none_when_registry_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        assert verify_claude_plugin_version() is None

    def test_returns_none_when_plugin_not_in_registry(self, tmp_path, monkeypatch):
        _write_registry(tmp_path, {
            "other-plugin@anvil": [{"version": "1.0.0"}],
        })
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        assert verify_claude_plugin_version() is None

    def test_returns_none_when_entries_empty(self, tmp_path, monkeypatch):
        _write_registry(tmp_path, {
            "taskmanager-agent@anvil": [],
        })
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        assert verify_claude_plugin_version() is None

    def test_returns_none_on_invalid_json(self, tmp_path, monkeypatch):
        registry = tmp_path / ".claude" / "plugins" / "installed_plugins.json"
        registry.parent.mkdir(parents=True)
        registry.write_text("not json")
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        assert verify_claude_plugin_version() is None

    def test_matches_any_marketplace(self, tmp_path, monkeypatch):
        _write_registry(tmp_path, {
            "taskmanager-agent@other-marketplace": [{"version": "1.2.3"}],
        })
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        assert verify_claude_plugin_version() == "1.2.3"
