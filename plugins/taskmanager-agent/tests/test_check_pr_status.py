"""Tests for check_pr_status.py."""

import importlib.util
from pathlib import Path


# Import the script as a module
_script = Path(__file__).parent.parent / "scripts" / "check_pr_status.py"
_spec = importlib.util.spec_from_file_location("check_pr_status", _script)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

_detect_platform = _mod._detect_platform


class TestDetectPlatform:
    def test_github_https(self):
        assert _detect_platform("https://github.com/owner/repo") == "github"

    def test_github_ssh(self):
        assert _detect_platform("git@github.com:owner/repo.git") == "github"

    def test_forgejo_https(self):
        assert _detect_platform("https://forgejo.example.com/owner/repo") == "forgejo"

    def test_forgejo_ssh(self):
        assert (
            _detect_platform("ssh://git@forgejo.example.com:2222/owner/repo.git")
            == "forgejo"
        )

    def test_forgejo_short_ssh(self):
        assert _detect_platform("git@forgejo.example.com:owner/repo.git") == "forgejo"


def test_check_pr_status_has_help(run_script):
    result = run_script("check_pr_status.py", "--help")
    assert result.returncode == 0
    assert "repo-url" in result.stdout
    assert "branch" in result.stdout


def test_check_pr_status_missing_args(run_script):
    result = run_script("check_pr_status.py")
    assert result.returncode != 0
