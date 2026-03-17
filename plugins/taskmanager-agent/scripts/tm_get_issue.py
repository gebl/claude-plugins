"""Get a single issue by ID."""
import argparse
import json
import sys
from dataclasses import asdict

from taskmanager.backends import get_backend


def main() -> None:
    parser = argparse.ArgumentParser(description="Get a single issue by ID")
    parser.add_argument("issue_id", help="Issue ID")
    parser.add_argument("--relations", action="store_true", help="Include related issues")
    args = parser.parse_args()

    try:
        backend = get_backend()
    except (ValueError, FileNotFoundError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        result = backend.get_issue(args.issue_id, include_relations=args.relations)
        print(json.dumps(asdict(result)))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
