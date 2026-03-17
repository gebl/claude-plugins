"""List comments for an issue."""
import argparse
import json
import sys
from dataclasses import asdict

from taskmanager.backends import get_backend


def main() -> None:
    parser = argparse.ArgumentParser(description="List comments for an issue")
    parser.add_argument("issue_id", help="Issue ID")
    args = parser.parse_args()

    try:
        backend = get_backend()
    except (ValueError, FileNotFoundError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        result = backend.list_comments(args.issue_id)
        print(json.dumps([asdict(r) for r in result]))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
