"""Create a new repository on a Forgejo instance."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from taskmanager.githost.forgejo import ForgejoBackend


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a Forgejo repository")
    parser.add_argument("--name", required=True, help="Repository name")
    parser.add_argument("--description", default="", help="Repository description")
    parser.add_argument(
        "--private",
        action="store_true",
        default=True,
        help="Create as private (default)",
    )
    parser.add_argument("--public", action="store_true", help="Create as public")
    parser.add_argument(
        "--forgejo-url",
        default=None,
        help="Forgejo base URL (defaults to FORGEJO_URL env var)",
    )
    parser.add_argument(
        "--org",
        default=None,
        help="Organization name (creates under org instead of user)",
    )
    parser.add_argument(
        "--auto-init", action="store_true", help="Initialize with README"
    )
    parser.add_argument(
        "--default-branch", default="main", help="Default branch name (default: main)"
    )
    args = parser.parse_args()

    import os

    forgejo_url = args.forgejo_url or os.environ.get("FORGEJO_URL", "")
    if not forgejo_url:
        print(
            "Error: --forgejo-url or FORGEJO_URL environment variable required",
            file=sys.stderr,
        )
        sys.exit(1)

    backend = ForgejoBackend()
    private = not args.public

    import httpx

    payload = {
        "name": args.name,
        "description": args.description,
        "private": private,
        "auto_init": args.auto_init,
        "default_branch": args.default_branch,
    }

    if args.org:
        api_url = f"{forgejo_url}/api/v1/orgs/{args.org}/repos"
    else:
        api_url = f"{forgejo_url}/api/v1/user/repos"

    try:
        response = httpx.post(
            api_url,
            json=payload,
            headers=backend._headers(),
        )
        response.raise_for_status()
        data = response.json()

        result = {
            "name": data["name"],
            "full_name": data["full_name"],
            "html_url": data["html_url"],
            "ssh_url": data["ssh_url"],
            "clone_url": data["clone_url"],
            "private": data["private"],
            "default_branch": data.get("default_branch", args.default_branch),
        }
        print(json.dumps(result))
    except httpx.HTTPStatusError as e:
        print(f"Error: {e.response.status_code} — {e.response.text}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
