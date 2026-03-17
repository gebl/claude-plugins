"""Create a document, optionally attached to a project."""
import argparse
import json
import sys
from dataclasses import asdict

from taskmanager.backends import get_backend


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a document, optionally attached to a project")
    parser.add_argument("--title", required=True, help="Document title")
    parser.add_argument("--content", required=True, help="Document content (markdown)")
    parser.add_argument("--project", help="Project ID to attach the document to")
    args = parser.parse_args()

    try:
        backend = get_backend()
    except (ValueError, FileNotFoundError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        result = backend.create_document(
            title=args.title,
            content=args.content,
            project=args.project,
        )
        print(json.dumps(asdict(result)))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
