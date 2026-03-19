"""Check the status of a pull request by branch name."""

import argparse
import json
import os
import subprocess
import sys

import httpx

# Reuse URL helpers from create_forgejo_pr
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from create_forgejo_pr import parse_repo_url, repo_url_to_https_base


def _detect_platform(repo_url: str) -> str:
    """Determine platform from repo URL hostname."""
    from urllib.parse import urlparse
    import re

    short_ssh = re.match(r"^[\w.-]+@([\w.-]+):", repo_url)
    hostname = short_ssh.group(1) if short_ssh else urlparse(repo_url).hostname or ""
    if "github.com" in hostname:
        return "github"
    return "forgejo"


def _check_forgejo(repo_url: str, branch: str) -> dict:
    """Check PR status on a Forgejo instance."""
    token = os.environ.get("FORGEJO_TOKEN", "")
    if not token:
        print("Error: FORGEJO_TOKEN environment variable is not set", file=sys.stderr)
        sys.exit(1)

    base_url = repo_url_to_https_base(repo_url)
    owner, repo = parse_repo_url(repo_url)
    headers = {"Authorization": f"token {token}", "Content-Type": "application/json"}

    # Find PR by head branch
    resp = httpx.get(
        f"{base_url}/api/v1/repos/{owner}/{repo}/pulls",
        params={"state": "all", "head": branch, "limit": 1},
        headers=headers,
    )
    resp.raise_for_status()
    pulls = resp.json()

    if not pulls:
        return {"state": "not_found", "comments": [], "pr_url": ""}

    pr = pulls[0]
    pr_number = pr["number"]
    pr_url = pr["html_url"]
    state = "merged" if pr.get("merged") else pr["state"]

    # Fetch review comments
    comments_resp = httpx.get(
        f"{base_url}/api/v1/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
        headers=headers,
    )
    comments_resp.raise_for_status()
    reviews = comments_resp.json()

    comments = [
        {
            "author": r.get("user", {}).get("login", "unknown"),
            "body": r.get("body", ""),
            "state": r.get("state", ""),
        }
        for r in reviews
        if r.get("body")
    ]

    return {
        "state": state,
        "comments": comments,
        "pr_url": pr_url,
        "pr_number": pr_number,
    }


def _check_github(repo_url: str, branch: str) -> dict:
    """Check PR status on GitHub using gh CLI."""
    owner, repo = parse_repo_url(repo_url)

    result = subprocess.run(
        [
            "gh",
            "pr",
            "list",
            "--repo",
            f"{owner}/{repo}",
            "--head",
            branch,
            "--state",
            "all",
            "--json",
            "number,state,url,reviews,merged",
            "--limit",
            "1",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Error: gh pr list failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    pulls = json.loads(result.stdout)
    if not pulls:
        return {"state": "not_found", "comments": [], "pr_url": ""}

    pr = pulls[0]
    state = "merged" if pr.get("merged") else pr["state"].lower()
    comments = [
        {
            "author": r.get("author", {}).get("login", "unknown"),
            "body": r.get("body", ""),
            "state": r.get("state", ""),
        }
        for r in pr.get("reviews", [])
        if r.get("body")
    ]

    return {
        "state": state,
        "comments": comments,
        "pr_url": pr["url"],
        "pr_number": pr["number"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Check PR status by branch name")
    parser.add_argument(
        "--repo-url", required=True, help="Full repo URL (SSH or HTTPS)"
    )
    parser.add_argument(
        "--branch", required=True, help="Head branch name to find PR for"
    )
    args = parser.parse_args()

    platform = _detect_platform(args.repo_url)

    if platform == "github":
        result = _check_github(args.repo_url, args.branch)
    else:
        result = _check_forgejo(args.repo_url, args.branch)

    print(json.dumps(result))


if __name__ == "__main__":
    main()
