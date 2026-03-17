"""Create a pull request on a Forgejo instance."""
import argparse
import json
import os
import sys
from urllib.parse import urlparse

import httpx


def parse_repo_url(url: str) -> tuple[str, str]:
    """Extract owner and repo name from a Forgejo/Gitea repo URL."""
    path = urlparse(url).path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    parts = path.split("/")
    if len(parts) < 2:
        raise ValueError(f"Cannot parse owner/repo from URL: {url}")
    return parts[0], parts[1]


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

    parsed = urlparse(args.repo_url)
    base_url = f"{parsed.scheme}://{parsed.hostname}"
    if parsed.port:
        base_url += f":{parsed.port}"

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
