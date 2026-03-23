"""Check the status of a pull request by branch name or PR URL."""

import argparse
import json
import sys
from pathlib import Path

# Add project root to path so taskmanager package is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from taskmanager.githost import get_githost_backend


def main() -> None:
    parser = argparse.ArgumentParser(description="Check PR status")
    parser.add_argument("--repo-url", help="Full repo URL (SSH or HTTPS)")
    parser.add_argument("--branch", help="Head branch name to find PR for")
    parser.add_argument(
        "--pr-url", help="Direct PR URL (alternative to --repo-url/--branch)"
    )
    args = parser.parse_args()

    if args.pr_url:
        backend = get_githost_backend(args.pr_url)
        result = backend.check_pr_status_by_url(args.pr_url)
    elif args.repo_url and args.branch:
        backend = get_githost_backend(args.repo_url)
        result = backend.check_pr_status(args.repo_url, args.branch)
    else:
        parser.error("Either --pr-url or both --repo-url and --branch are required")

    print(json.dumps(result))


if __name__ == "__main__":
    main()
