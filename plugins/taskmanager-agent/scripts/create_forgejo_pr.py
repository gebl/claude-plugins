"""Create a pull request on a Forgejo instance."""

import argparse
import json
import os
import re
import sys
from urllib.parse import urlparse

import httpx

# Matches short SSH format: git@host:owner/repo.git
_SHORT_SSH_RE = re.compile(r"^[\w.-]+@([\w.-]+):(.+)$")


def parse_repo_url(url: str) -> tuple[str, str]:
    """Extract owner and repo name from a Forgejo/Gitea repo URL.

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
      - https://host[:port]/...
      - ssh://[user@]host[:port]/...
      - git@host:owner/repo.git  (short SSH)
    """
    short = _SHORT_SSH_RE.match(url)
    if short:
        return f"https://{short.group(1)}"

    parsed = urlparse(url)
    base = f"https://{parsed.hostname}"
    if parsed.port:
        base += f":{parsed.port}"
    return base


def main() -> None:
    token = os.environ.get("FORGEJO_TOKEN", "")
    if not token:
        print("Error: FORGEJO_TOKEN environment variable is not set", file=sys.stderr)
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Create a Forgejo pull request")
    parser.add_argument("--repo-url", required=True, help="Full repo URL")
    parser.add_argument("--branch", required=True, help="Head branch name")
    parser.add_argument("--title", required=True, help="PR title")
    parser.add_argument("--body", default="", help="PR body (markdown)")
    parser.add_argument("--base", default="main", help="Base branch (default: main)")
    args = parser.parse_args()

    base_url = repo_url_to_https_base(args.repo_url)

    try:
        owner, repo = parse_repo_url(args.repo_url)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    response = httpx.post(
        f"{base_url}/api/v1/repos/{owner}/{repo}/pulls",
        json={"title": args.title, "head": args.branch, "base": args.base, "body": args.body},
        headers={"Authorization": f"token {token}", "Content-Type": "application/json"},
    )
    response.raise_for_status()
    data = response.json()
    print(json.dumps({"number": data["number"], "html_url": data["html_url"]}))


if __name__ == "__main__":
    main()
