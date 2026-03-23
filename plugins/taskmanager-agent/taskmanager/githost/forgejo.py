"""Forgejo git hosting backend."""

from __future__ import annotations

import sys

import httpx

from taskmanager.githost.base import (
    parse_pr_url,
    parse_repo_url,
    repo_url_to_https_base,
)
from taskmanager.secrets import EnvSecretProvider, SecretProvider


class ForgejoBackend:
    """Git hosting backend for Forgejo/Gitea instances."""

    def __init__(
        self,
        token: str | None = None,
        secret_provider: SecretProvider | None = None,
        token_env: str = "FORGEJO_TOKEN",
    ) -> None:
        provider = secret_provider or EnvSecretProvider()
        self._token = token or provider.get(token_env, "")
        if not self._token:
            print(
                f"Error: {token_env} environment variable is not set", file=sys.stderr
            )
            sys.exit(1)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"token {self._token}",
            "Content-Type": "application/json",
        }

    def create_pr(
        self,
        repo_url: str,
        head: str,
        base: str,
        title: str,
        body: str,
    ) -> dict:
        """Create a pull request on a Forgejo instance."""
        base_url = repo_url_to_https_base(repo_url)
        owner, repo = parse_repo_url(repo_url)

        response = httpx.post(
            f"{base_url}/api/v1/repos/{owner}/{repo}/pulls",
            json={"title": title, "head": head, "base": base, "body": body},
            headers=self._headers(),
        )
        response.raise_for_status()
        data = response.json()
        return {"number": data["number"], "html_url": data["html_url"]}

    def check_pr_status(self, repo_url: str, branch: str) -> dict:
        """Check PR status on a Forgejo instance."""
        base_url = repo_url_to_https_base(repo_url)
        owner, repo = parse_repo_url(repo_url)
        headers = self._headers()

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
        pr_state = "merged" if pr.get("merged") else pr["state"]

        # Fetch formal reviews
        reviews_resp = httpx.get(
            f"{base_url}/api/v1/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
            headers=headers,
        )
        reviews_resp.raise_for_status()
        reviews = reviews_resp.json()

        comments = [
            {
                "author": r.get("user", {}).get("login", "unknown"),
                "body": r.get("body", ""),
                "state": r.get("state", ""),
                "source": "review",
            }
            for r in reviews
            if r.get("body")
        ]

        # Fetch regular PR comments (PRs are issues in Forgejo)
        issue_comments_resp = httpx.get(
            f"{base_url}/api/v1/repos/{owner}/{repo}/issues/{pr_number}/comments",
            headers=headers,
        )
        issue_comments_resp.raise_for_status()
        issue_comments = issue_comments_resp.json()

        comments.extend(
            {
                "author": c.get("user", {}).get("login", "unknown"),
                "body": c.get("body", ""),
                "state": "",
                "source": "comment",
            }
            for c in issue_comments
            if c.get("body")
        )

        return {
            "state": pr_state,
            "comments": comments,
            "pr_url": pr_url,
            "pr_number": pr_number,
        }

    def check_pr_status_by_url(self, pr_url: str) -> dict:
        """Check PR status by direct PR URL."""
        base_url, owner, repo, pr_number = parse_pr_url(pr_url)
        headers = self._headers()

        resp = httpx.get(
            f"{base_url}/api/v1/repos/{owner}/{repo}/pulls/{pr_number}",
            headers=headers,
        )
        if resp.status_code == 404:
            return {"state": "not_found", "comments": [], "pr_url": pr_url}
        resp.raise_for_status()

        pr = resp.json()
        pr_state = "merged" if pr.get("merged") else pr["state"]

        # Fetch formal reviews
        reviews_resp = httpx.get(
            f"{base_url}/api/v1/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
            headers=headers,
        )
        reviews_resp.raise_for_status()
        reviews = reviews_resp.json()

        comments = [
            {
                "author": r.get("user", {}).get("login", "unknown"),
                "body": r.get("body", ""),
                "state": r.get("state", ""),
                "source": "review",
            }
            for r in reviews
            if r.get("body")
        ]

        # Fetch regular PR comments
        issue_comments_resp = httpx.get(
            f"{base_url}/api/v1/repos/{owner}/{repo}/issues/{pr_number}/comments",
            headers=headers,
        )
        issue_comments_resp.raise_for_status()
        issue_comments = issue_comments_resp.json()

        comments.extend(
            {
                "author": c.get("user", {}).get("login", "unknown"),
                "body": c.get("body", ""),
                "state": "",
                "source": "comment",
            }
            for c in issue_comments
            if c.get("body")
        )

        return {
            "state": pr_state,
            "comments": comments,
            "pr_url": pr_url,
            "pr_number": pr_number,
        }
