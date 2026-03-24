"""Tests for taskmanager.githost module."""

import re
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from taskmanager.githost.base import (
    detect_platform,
    parse_pr_url,
    parse_repo_url,
    repo_url_to_https_base,
)
from taskmanager.githost import get_githost_backend
from taskmanager.githost.forgejo import ForgejoBackend


class TestParseRepoUrl:
    def test_https_url(self):
        assert parse_repo_url("https://forgejo.example.com/Anvil/blog.git") == (
            "Anvil",
            "blog",
        )

    def test_https_url_no_git_suffix(self):
        assert parse_repo_url("https://forgejo.example.com/Anvil/blog") == (
            "Anvil",
            "blog",
        )

    def test_https_url_with_port(self):
        assert parse_repo_url("https://forgejo.example.com:3000/Org/repo.git") == (
            "Org",
            "repo",
        )

    def test_ssh_url(self):
        assert parse_repo_url(
            "ssh://git@forgejo.example.com:2222/Anvil/claude-plugins.git"
        ) == (
            "Anvil",
            "claude-plugins",
        )

    def test_ssh_url_no_port(self):
        assert parse_repo_url("ssh://git@forgejo.example.com/Anvil/repo.git") == (
            "Anvil",
            "repo",
        )

    def test_short_ssh(self):
        assert parse_repo_url("git@forgejo.example.com:Anvil/repo.git") == (
            "Anvil",
            "repo",
        )

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
        assert repo_url_to_https_base(
            "ssh://git@forgejo.example.com:2222/Anvil/repo.git"
        ) == ("https://forgejo.example.com")

    def test_ssh_no_port(self):
        assert repo_url_to_https_base(
            "ssh://git@forgejo.example.com/Anvil/repo.git"
        ) == ("https://forgejo.example.com")

    def test_short_ssh(self):
        assert (
            repo_url_to_https_base("git@forgejo.example.com:Anvil/repo.git")
            == "https://forgejo.example.com"
        )


class TestDetectPlatform:
    def test_github_https(self):
        assert detect_platform("https://github.com/owner/repo") == "github"

    def test_github_ssh(self):
        assert detect_platform("git@github.com:owner/repo.git") == "github"

    def test_forgejo_https(self):
        assert detect_platform("https://forgejo.example.com/owner/repo") == "forgejo"

    def test_forgejo_ssh(self):
        assert (
            detect_platform("ssh://git@forgejo.example.com:2222/owner/repo.git")
            == "forgejo"
        )

    def test_forgejo_short_ssh(self):
        assert detect_platform("git@forgejo.example.com:owner/repo.git") == "forgejo"


class TestGetGithostBackend:
    def test_forgejo_url_returns_forgejo_backend(self):
        with patch.dict("os.environ", {"TASKMANAGER_AGENT_FORGEJO_TOKEN": "test-token"}):
            backend = get_githost_backend("https://forgejo.example.com/Org/repo")
            assert isinstance(backend, ForgejoBackend)

    def test_unsupported_platform_raises(self):
        with pytest.raises(ValueError, match="Unsupported"):
            get_githost_backend("https://github.com/owner/repo")

    def test_forgejo_ssh_returns_forgejo_backend(self):
        with patch.dict("os.environ", {"TASKMANAGER_AGENT_FORGEJO_TOKEN": "test-token"}):
            backend = get_githost_backend("git@forgejo.example.com:Org/repo.git")
            assert isinstance(backend, ForgejoBackend)


class TestForgejoBackend:
    def test_create_pr(self, httpx_mock):
        httpx_mock.add_response(
            url="https://forgejo.example.com/api/v1/repos/Org/repo/pulls",
            method="POST",
            json={
                "number": 42,
                "html_url": "https://forgejo.example.com/Org/repo/pulls/42",
            },
        )
        backend = ForgejoBackend(token="test-token")
        result = backend.create_pr(
            repo_url="https://forgejo.example.com/Org/repo",
            head="feature-branch",
            base="main",
            title="Test PR",
            body="Test body",
        )
        assert result == {
            "number": 42,
            "html_url": "https://forgejo.example.com/Org/repo/pulls/42",
        }

    def test_check_pr_status_not_found(self, httpx_mock):
        httpx_mock.add_response(
            url=re.compile(
                r"https://forgejo\.example\.com/api/v1/repos/Org/repo/pulls\b"
            ),
            method="GET",
            json=[],
        )
        backend = ForgejoBackend(token="test-token")
        result = backend.check_pr_status(
            "https://forgejo.example.com/Org/repo", "no-branch"
        )
        assert result["state"] == "not_found"
        assert result["comments"] == []

    def test_check_pr_status_open_with_reviews(self, httpx_mock):
        httpx_mock.add_response(
            url=re.compile(
                r"https://forgejo\.example\.com/api/v1/repos/Org/repo/pulls\?"
            ),
            method="GET",
            json=[
                {
                    "number": 10,
                    "html_url": "https://forgejo.example.com/Org/repo/pulls/10",
                    "state": "open",
                    "merged": False,
                }
            ],
        )
        httpx_mock.add_response(
            url=re.compile(
                r"https://forgejo\.example\.com/api/v1/repos/Org/repo/pulls/10/reviews"
            ),
            method="GET",
            json=[
                {
                    "user": {"login": "reviewer"},
                    "body": "Looks good",
                    "state": "APPROVED",
                },
                {"user": {"login": "bot"}, "body": "", "state": "COMMENTED"},
            ],
        )
        httpx_mock.add_response(
            url=re.compile(
                r"https://forgejo\.example\.com/api/v1/repos/Org/repo/issues/10/comments"
            ),
            method="GET",
            json=[],
        )
        backend = ForgejoBackend(token="test-token")
        result = backend.check_pr_status(
            "https://forgejo.example.com/Org/repo", "feature"
        )
        assert result["state"] == "open"
        assert result["pr_number"] == 10
        assert len(result["comments"]) == 1
        assert result["comments"][0]["author"] == "reviewer"
        assert result["comments"][0]["source"] == "review"

    def test_check_pr_status_open_with_issue_comments(self, httpx_mock):
        httpx_mock.add_response(
            url=re.compile(
                r"https://forgejo\.example\.com/api/v1/repos/Org/repo/pulls\?"
            ),
            method="GET",
            json=[
                {
                    "number": 10,
                    "html_url": "https://forgejo.example.com/Org/repo/pulls/10",
                    "state": "open",
                    "merged": False,
                }
            ],
        )
        httpx_mock.add_response(
            url=re.compile(
                r"https://forgejo\.example\.com/api/v1/repos/Org/repo/pulls/10/reviews"
            ),
            method="GET",
            json=[],
        )
        httpx_mock.add_response(
            url=re.compile(
                r"https://forgejo\.example\.com/api/v1/repos/Org/repo/issues/10/comments"
            ),
            method="GET",
            json=[
                {
                    "user": {"login": "gabe"},
                    "body": "Please fix the error handling here",
                },
            ],
        )
        backend = ForgejoBackend(token="test-token")
        result = backend.check_pr_status(
            "https://forgejo.example.com/Org/repo", "feature"
        )
        assert result["state"] == "open"
        assert len(result["comments"]) == 1
        assert result["comments"][0]["author"] == "gabe"
        assert result["comments"][0]["source"] == "comment"

    def test_check_pr_status_merged(self, httpx_mock):
        httpx_mock.add_response(
            url=re.compile(
                r"https://forgejo\.example\.com/api/v1/repos/Org/repo/pulls\?"
            ),
            method="GET",
            json=[
                {
                    "number": 5,
                    "html_url": "https://forgejo.example.com/Org/repo/pulls/5",
                    "state": "closed",
                    "merged": True,
                }
            ],
        )
        httpx_mock.add_response(
            url=re.compile(
                r"https://forgejo\.example\.com/api/v1/repos/Org/repo/pulls/5/reviews"
            ),
            method="GET",
            json=[],
        )
        httpx_mock.add_response(
            url=re.compile(
                r"https://forgejo\.example\.com/api/v1/repos/Org/repo/issues/5/comments"
            ),
            method="GET",
            json=[],
        )
        backend = ForgejoBackend(token="test-token")
        result = backend.check_pr_status(
            "https://forgejo.example.com/Org/repo", "merged-branch"
        )
        assert result["state"] == "merged"

    def test_check_pr_status_by_url_open(self, httpx_mock):
        httpx_mock.add_response(
            url="https://forgejo.example.com/api/v1/repos/Org/repo/pulls/42",
            method="GET",
            json={
                "number": 42,
                "html_url": "https://forgejo.example.com/Org/repo/pulls/42",
                "state": "open",
                "merged": False,
            },
        )
        httpx_mock.add_response(
            url=re.compile(
                r"https://forgejo\.example\.com/api/v1/repos/Org/repo/pulls/42/reviews"
            ),
            method="GET",
            json=[
                {"user": {"login": "gabe"}, "body": "Needs work", "state": "COMMENT"},
            ],
        )
        httpx_mock.add_response(
            url=re.compile(
                r"https://forgejo\.example\.com/api/v1/repos/Org/repo/issues/42/comments"
            ),
            method="GET",
            json=[],
        )
        backend = ForgejoBackend(token="test-token")
        result = backend.check_pr_status_by_url(
            "https://forgejo.example.com/Org/repo/pulls/42"
        )
        assert result["state"] == "open"
        assert result["pr_number"] == 42
        assert len(result["comments"]) == 1
        assert result["comments"][0]["author"] == "gabe"

    def test_check_pr_status_by_url_merged(self, httpx_mock):
        httpx_mock.add_response(
            url="https://forgejo.example.com/api/v1/repos/Org/repo/pulls/10",
            method="GET",
            json={
                "number": 10,
                "html_url": "https://forgejo.example.com/Org/repo/pulls/10",
                "state": "closed",
                "merged": True,
            },
        )
        httpx_mock.add_response(
            url=re.compile(
                r"https://forgejo\.example\.com/api/v1/repos/Org/repo/pulls/10/reviews"
            ),
            method="GET",
            json=[],
        )
        httpx_mock.add_response(
            url=re.compile(
                r"https://forgejo\.example\.com/api/v1/repos/Org/repo/issues/10/comments"
            ),
            method="GET",
            json=[],
        )
        backend = ForgejoBackend(token="test-token")
        result = backend.check_pr_status_by_url(
            "https://forgejo.example.com/Org/repo/pulls/10"
        )
        assert result["state"] == "merged"

    def test_check_pr_status_by_url_not_found(self, httpx_mock):
        httpx_mock.add_response(
            url="https://forgejo.example.com/api/v1/repos/Org/repo/pulls/999",
            method="GET",
            status_code=404,
        )
        backend = ForgejoBackend(token="test-token")
        result = backend.check_pr_status_by_url(
            "https://forgejo.example.com/Org/repo/pulls/999"
        )
        assert result["state"] == "not_found"


class TestParsePrUrl:
    def test_standard_url(self):
        base, owner, repo, number = parse_pr_url(
            "https://forgejo.example.com/Org/repo/pulls/42"
        )
        assert base == "https://forgejo.example.com"
        assert owner == "Org"
        assert repo == "repo"
        assert number == 42

    def test_url_with_port(self):
        base, owner, repo, number = parse_pr_url(
            "https://forgejo.example.com:3000/Org/repo/pulls/7"
        )
        assert base == "https://forgejo.example.com:3000"
        assert owner == "Org"
        assert repo == "repo"
        assert number == 7

    def test_github_pull_singular(self):
        base, owner, repo, number = parse_pr_url(
            "https://github.com/owner/project/pull/123"
        )
        assert base == "https://github.com"
        assert owner == "owner"
        assert repo == "project"
        assert number == 123

    def test_invalid_url_raises(self):
        with pytest.raises(ValueError, match="Cannot parse PR URL"):
            parse_pr_url("https://example.com/not-a-pr")
