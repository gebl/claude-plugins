"""SessionStart hook — creates a new session row in the database."""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import db


def get_git_info(cwd: str) -> tuple[str | None, str | None]:
    """Derive git repo URL and branch from cwd. Returns (repo, branch)."""
    try:
        branch = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        repo = subprocess.run(
            ["git", "-C", cwd, "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5,
        )
        return (
            repo.stdout.strip() if repo.returncode == 0 else None,
            branch.stdout.strip() if branch.returncode == 0 else None,
        )
    except Exception:
        return None, None


def main() -> None:
    data = json.load(sys.stdin)

    session_id = data.get("session_id")
    if not session_id:
        return

    cwd = data.get("cwd", "")
    git_repo, git_branch = get_git_info(cwd) if cwd else (None, None)

    db.upsert_session(
        session_id=session_id,
        model=data.get("model"),
        cwd=cwd,
        git_repo=git_repo,
        git_branch=git_branch,
        permission_mode=data.get("permission_mode"),
        session_source=data.get("source"),
        started_at=db.now_iso(),
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
