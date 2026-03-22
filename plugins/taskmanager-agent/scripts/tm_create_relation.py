"""Create a 'blocks' relation between two issues."""

import argparse
import json
import sys

from taskmanager.backends import get_backend


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a blocks relation between issues")
    parser.add_argument("--issue-id", required=True, help="Issue ID that blocks the other")
    parser.add_argument("--blocks", required=True, help="Issue ID that is blocked")
    args = parser.parse_args()

    try:
        backend = get_backend()
    except (ValueError, FileNotFoundError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        result = backend.create_relation(args.issue_id, args.blocks)
        print(json.dumps(result))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
