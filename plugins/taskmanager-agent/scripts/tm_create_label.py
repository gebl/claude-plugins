"""Create a label (issue or project scope)."""
import argparse
import json
import sys
from dataclasses import asdict

from taskmanager.backends import get_backend


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a label for issues or projects")
    parser.add_argument("--name", required=True, help="Label name")
    parser.add_argument("--color", required=True, help="Label color (hex)")
    parser.add_argument("--scope", required=True, choices=["issue", "project"], help="Label scope: issue or project")
    parser.add_argument("--description", default="", help="Label description (project labels only)")
    args = parser.parse_args()

    try:
        backend = get_backend()
    except (ValueError, FileNotFoundError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        if args.scope == "issue":
            result = backend.create_issue_label(name=args.name, color=args.color)
        else:
            result = backend.create_project_label(
                name=args.name,
                color=args.color,
                description=args.description,
            )
        print(json.dumps(asdict(result)))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
