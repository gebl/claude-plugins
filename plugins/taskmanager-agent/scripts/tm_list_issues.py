"""List issues from the task backend."""
import argparse
import json
import sys
from dataclasses import asdict

from taskmanager.backends import get_backend


def main() -> None:
    parser = argparse.ArgumentParser(description="List issues from the task backend")
    parser.add_argument("--status", help="Filter by status name")
    parser.add_argument("--project", help="Filter by project name")
    args = parser.parse_args()

    try:
        backend = get_backend()
    except (ValueError, FileNotFoundError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        result = backend.list_issues(status=args.status, project=args.project)
        print(json.dumps([asdict(r) for r in result]))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
