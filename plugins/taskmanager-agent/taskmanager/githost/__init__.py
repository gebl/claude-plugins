"""Git hosting backend factory."""

from taskmanager.githost.base import GitHostBackend, detect_platform


def get_githost_backend(repo_url: str) -> GitHostBackend:
    """Return the appropriate git hosting backend for a repo URL."""
    platform = detect_platform(repo_url)
    if platform == "forgejo":
        from taskmanager.githost.forgejo import ForgejoBackend

        return ForgejoBackend()
    raise ValueError(f"Unsupported git hosting platform: {platform}")
