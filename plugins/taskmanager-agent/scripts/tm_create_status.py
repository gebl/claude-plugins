"""Create a workflow status for a team."""
import argparse
import json
import sys
from dataclasses import asdict

from taskmanager.backends import get_backend


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a workflow status for a team")
    parser.add_argument("--team-id", required=True, help="Team ID")
    parser.add_argument("--name", required=True, help="Status name")
    parser.add_argument("--type", required=True, dest="status_type", help="Status type (backlog, unstarted, started, completed, canceled)")
    parser.add_argument("--color", required=True, help="Status color (hex)")
    args = parser.parse_args()

    try:
        backend = get_backend()
    except (ValueError, FileNotFoundError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        result = backend.create_status(
            team_id=args.team_id,
            name=args.name,
            type=args.status_type,
            color=args.color,
        )
        print(json.dumps(asdict(result)))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
