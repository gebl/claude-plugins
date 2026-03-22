"""Check the status of a pull request by branch name."""

import argparse
import json
import sys
from pathlib import Path

# Add project root to path so taskmanager package is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from taskmanager.githost import get_githost_backend


def main() -> None:
    parser = argparse.ArgumentParser(description="Check PR status by branch name")
    parser.add_argument(
        "--repo-url", required=True, help="Full repo URL (SSH or HTTPS)"
    )
    parser.add_argument(
        "--branch", required=True, help="Head branch name to find PR for"
    )
    args = parser.parse_args()

    backend = get_githost_backend(args.repo_url)
    result = backend.check_pr_status(args.repo_url, args.branch)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
