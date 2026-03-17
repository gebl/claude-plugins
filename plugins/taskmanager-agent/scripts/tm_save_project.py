"""Create a new project."""
import argparse
import json
import sys
from dataclasses import asdict

from taskmanager.backends import get_backend


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a new project")
    parser.add_argument("--name", required=True, help="Project name")
    parser.add_argument("--team", required=True, help="Team ID")
    parser.add_argument("--description", default="", help="Project description")
    parser.add_argument("--labels", nargs="+", help="Project label IDs")
    args = parser.parse_args()

    try:
        backend = get_backend()
    except (ValueError, FileNotFoundError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        result = backend.save_project(
            name=args.name,
            team=args.team,
            description=args.description,
            labels=args.labels,
        )
        print(json.dumps(asdict(result)))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
