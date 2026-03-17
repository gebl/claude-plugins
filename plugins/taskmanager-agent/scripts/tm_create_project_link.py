"""Create an external link on a project."""
import argparse
import json
import sys
from dataclasses import asdict

from taskmanager.backends import get_backend


def main() -> None:
    parser = argparse.ArgumentParser(description="Create an external link on a project")
    parser.add_argument("--project-id", required=True, help="Project ID")
    parser.add_argument("--label", required=True, help="Link label")
    parser.add_argument("--url", required=True, help="Link URL")
    args = parser.parse_args()

    try:
        backend = get_backend()
    except (ValueError, FileNotFoundError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        result = backend.create_project_link(
            project_id=args.project_id,
            label=args.label,
            url=args.url,
        )
        print(json.dumps(asdict(result)))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
