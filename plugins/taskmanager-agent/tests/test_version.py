"""Tests for version helper and Claude version verification."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

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


class TestVerifyClaudePluginVersion:
    def test_returns_version_on_success(self):
        with patch("taskmanager.daemon.runner.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="0.6.9\n", stderr=""
            )
            result = verify_claude_plugin_version()
            assert result == "0.6.9"

    def test_returns_none_on_nonzero_exit(self):
        with patch("taskmanager.daemon.runner.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr="error"
            )
            result = verify_claude_plugin_version()
            assert result is None

    def test_returns_none_on_timeout(self):
        with patch("taskmanager.daemon.runner.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=60)
            result = verify_claude_plugin_version()
            assert result is None

    def test_returns_none_when_claude_not_found(self):
        with patch("taskmanager.daemon.runner.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            result = verify_claude_plugin_version()
            assert result is None

    def test_strips_whitespace(self):
        with patch("taskmanager.daemon.runner.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="  1.2.3  \n", stderr=""
            )
            result = verify_claude_plugin_version()
            assert result == "1.2.3"
