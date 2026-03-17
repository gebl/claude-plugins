"""Create or update a comment."""
import argparse
import json
import sys
from dataclasses import asdict

from taskmanager.backends import get_backend


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or update a comment")
    parser.add_argument("--id", help="Comment ID (for updates)")
    parser.add_argument("--issue-id", help="Issue ID (for new comments)")
    parser.add_argument("--body", required=True, help="Comment body (markdown)")
    args = parser.parse_args()

    try:
        backend = get_backend()
    except (ValueError, FileNotFoundError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        result = backend.save_comment(id=args.id, issue_id=args.issue_id, body=args.body)
        print(json.dumps(asdict(result)))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
