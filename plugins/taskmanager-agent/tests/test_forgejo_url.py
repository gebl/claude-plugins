"""Tests for URL parsing in create_forgejo_pr.py."""

import importlib.util
from pathlib import Path

import pytest

# Import the script as a module
_script = Path(__file__).parent.parent / "scripts" / "create_forgejo_pr.py"
_spec = importlib.util.spec_from_file_location("create_forgejo_pr", _script)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

parse_repo_url = _mod.parse_repo_url
repo_url_to_https_base = _mod.repo_url_to_https_base


class TestParseRepoUrl:
    def test_https_url(self):
        assert parse_repo_url("https://forgejo.example.com/Anvil/blog.git") == ("Anvil", "blog")

    def test_https_url_no_git_suffix(self):
        assert parse_repo_url("https://forgejo.example.com/Anvil/blog") == ("Anvil", "blog")

    def test_https_url_with_port(self):
        assert parse_repo_url("https://forgejo.example.com:3000/Org/repo.git") == ("Org", "repo")

    def test_ssh_url(self):
        assert parse_repo_url("ssh://git@forgejo.example.com:2222/Anvil/claude-plugins.git") == (
            "Anvil",
            "claude-plugins",
        )

    def test_ssh_url_no_port(self):
        assert parse_repo_url("ssh://git@forgejo.example.com/Anvil/repo.git") == ("Anvil", "repo")

    def test_short_ssh(self):
        assert parse_repo_url("git@forgejo.example.com:Anvil/repo.git") == ("Anvil", "repo")

    def test_short_ssh_no_git_suffix(self):
        assert parse_repo_url("git@forgejo.example.com:Anvil/repo") == ("Anvil", "repo")

    def test_invalid_url_raises(self):
        with pytest.raises(ValueError, match="Cannot parse"):
            parse_repo_url("https://forgejo.example.com/lonely")


class TestRepoUrlToHttpsBase:
    def test_https_no_port(self):
        assert (
            repo_url_to_https_base("https://forgejo.example.com/Org/repo")
            == "https://forgejo.example.com"
        )

    def test_https_with_port(self):
        assert repo_url_to_https_base("https://forgejo.example.com:3000/Org/repo") == (
            "https://forgejo.example.com:3000"
        )

    def test_ssh_with_port_drops_port(self):
        assert repo_url_to_https_base("ssh://git@forgejo.example.com:2222/Anvil/repo.git") == (
            "https://forgejo.example.com"
        )

    def test_ssh_no_port(self):
        assert repo_url_to_https_base("ssh://git@forgejo.example.com/Anvil/repo.git") == (
            "https://forgejo.example.com"
        )

    def test_short_ssh(self):
        assert (
            repo_url_to_https_base("git@forgejo.example.com:Anvil/repo.git")
            == "https://forgejo.example.com"
        )
