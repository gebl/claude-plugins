"""Create a pull request on the detected git hosting platform."""

import argparse
import json
import sys
from pathlib import Path

# Add project root to path so taskmanager package is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from taskmanager.githost import get_githost_backend


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a pull request")
    parser.add_argument("--repo-url", required=True, help="Full repo URL")
    parser.add_argument("--branch", required=True, help="Head branch name")
    parser.add_argument("--title", required=True, help="PR title")
    parser.add_argument("--body", default="", help="PR body (markdown)")
    parser.add_argument("--base", default="main", help="Base branch (default: main)")
    args = parser.parse_args()

    backend = get_githost_backend(args.repo_url)
    result = backend.create_pr(
        repo_url=args.repo_url,
        head=args.branch,
        base=args.base,
        title=args.title,
        body=args.body,
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
