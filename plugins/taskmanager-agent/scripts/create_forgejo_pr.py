"""Create a pull request on a Forgejo instance.

DEPRECATED: Use create_pr.py instead. This script is kept for backward compatibility.
The URL helpers (parse_repo_url, repo_url_to_https_base) now live in
taskmanager.githost.base but are re-exported here for existing imports.
"""

import sys
from pathlib import Path

# Add project root to path so taskmanager package is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

# Re-export URL helpers for backward compatibility (tests import these)
from taskmanager.githost.base import parse_repo_url, repo_url_to_https_base  # noqa: F401


def main() -> None:
    """Delegate to the platform-agnostic create_pr.py."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "create_pr", Path(__file__).parent / "create_pr.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.main()


if __name__ == "__main__":
    main()
