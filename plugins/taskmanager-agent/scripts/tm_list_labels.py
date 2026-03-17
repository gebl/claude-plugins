"""List labels by scope (issue or project)."""
import argparse
import json
import sys
from dataclasses import asdict

from taskmanager.backends import get_backend


def main() -> None:
    parser = argparse.ArgumentParser(description="List labels by scope")
    parser.add_argument("--scope", required=True, choices=["issue", "project"], help="Label scope: issue or project")
    args = parser.parse_args()

    try:
        backend = get_backend()
    except (ValueError, FileNotFoundError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        if args.scope == "issue":
            result = backend.list_issue_labels()
        else:
            result = backend.list_project_labels()
        print(json.dumps([asdict(r) for r in result]))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
