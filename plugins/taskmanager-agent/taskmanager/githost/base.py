"""Git hosting backend protocol and shared URL utilities."""

from __future__ import annotations

import re
from typing import Protocol
from urllib.parse import urlparse


# Matches short SSH format: git@host:owner/repo.git
_SHORT_SSH_RE = re.compile(r"^[\w.-]+@([\w.-]+):(.+)$")


def parse_repo_url(url: str) -> tuple[str, str]:
    """Extract owner and repo name from a git repo URL.

    Handles https://, ssh://, and short SSH (git@host:path) formats.
    """
    short = _SHORT_SSH_RE.match(url)
    if short:
        path = short.group(2)
    else:
        path = urlparse(url).path.strip("/")
    path = path.removesuffix(".git")
    parts = path.strip("/").split("/")
    if len(parts) < 2:
        raise ValueError(f"Cannot parse owner/repo from URL: {url}")
    return parts[0], parts[1]


def repo_url_to_https_base(url: str) -> str:
    """Convert any git repo URL to an HTTPS base URL for API calls.

    Supports:
      - https://host[:port]/...  (port preserved - it's the HTTP port)
      - ssh://[user@]host[:port]/...  (port dropped - SSH port != HTTP port)
      - git@host:owner/repo.git  (short SSH, no port)
    """
    short = _SHORT_SSH_RE.match(url)
    if short:
        return f"https://{short.group(1)}"

    parsed = urlparse(url)
    base = f"https://{parsed.hostname}"
    if parsed.port and parsed.scheme in ("http", "https"):
        base += f":{parsed.port}"
    return base


def detect_platform(repo_url: str) -> str:
    """Determine git hosting platform from repo URL hostname."""
    short_ssh = _SHORT_SSH_RE.match(repo_url)
    hostname = short_ssh.group(1) if short_ssh else urlparse(repo_url).hostname or ""
    if "github.com" in hostname:
        return "github"
    return "forgejo"


def parse_pr_url(url: str) -> tuple[str, str, str, int]:
    """Extract base URL, owner, repo, and PR number from a pull request URL.

    Handles URLs like: https://host[:port]/owner/repo/pulls/123
    Returns (base_url, owner, repo, pr_number).
    """
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.hostname}"
    if parsed.port:
        base += f":{parsed.port}"

    # Path: /owner/repo/pulls/123 or /owner/repo/pull/123
    parts = parsed.path.strip("/").split("/")
    if len(parts) < 4 or parts[2] not in ("pulls", "pull"):
        raise ValueError(f"Cannot parse PR URL: {url}")
    return base, parts[0], parts[1], int(parts[3])


class GitHostBackend(Protocol):
    """Protocol that all git hosting backends must satisfy."""

    def create_pr(
        self,
        repo_url: str,
        head: str,
        base: str,
        title: str,
        body: str,
    ) -> dict:
        """Create a pull request. Returns dict with 'number' and 'html_url'."""
        ...

    def check_pr_status(self, repo_url: str, branch: str) -> dict:
        """Check PR status by branch name.

        Returns dict with keys:
          - state: 'merged' | 'open' | 'closed' | 'not_found'
          - comments: list of {author, body, state}
          - pr_url: str
          - pr_number: int (if found)
        """
        ...

    def check_pr_status_by_url(self, pr_url: str) -> dict:
        """Check PR status by PR URL.

        Returns same dict shape as check_pr_status.
        """
        ...
