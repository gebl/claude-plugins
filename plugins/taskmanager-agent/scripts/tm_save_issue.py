"""Create or update an issue."""

import argparse
import json
import sys
from dataclasses import asdict

from taskmanager.backends import get_backend


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or update an issue")
    parser.add_argument("--id", help="Issue ID (for updates)")
    parser.add_argument("--title", help="Issue title")
    parser.add_argument("--team", help="Team ID")
    parser.add_argument("--state", help="State ID")
    parser.add_argument("--labels", nargs="+", help="Label IDs")
    parser.add_argument(
        "--priority",
        type=int,
        help="Priority (0=None, 1=Urgent, 2=High, 3=Normal, 4=Low)",
    )
    parser.add_argument("--description", help="Issue description (markdown)")
    parser.add_argument("--project", help="Project ID")
    parser.add_argument("--parent-id", help="Parent issue ID")
    parser.add_argument("--assignee", help="Assignee user ID")
    parser.add_argument(
        "--links", help='JSON array of links: [{"url":"...","label":"..."}]'
    )
    args = parser.parse_args()

    links = None
    if args.links:
        try:
            links = json.loads(args.links)
        except json.JSONDecodeError as e:
            print(f"Error: invalid --links JSON: {e}", file=sys.stderr)
            sys.exit(1)

    try:
        backend = get_backend()
    except (ValueError, FileNotFoundError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        result = backend.save_issue(
            id=args.id,
            title=args.title,
            team=args.team,
            state=args.state,
            labels=args.labels,
            priority=args.priority,
            description=args.description,
            project=args.project,
            parent_id=args.parent_id,
            assignee=args.assignee,
            links=links,
        )
        print(json.dumps(asdict(result)))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
