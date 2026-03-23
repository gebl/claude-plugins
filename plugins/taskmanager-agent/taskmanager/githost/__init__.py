"""Git hosting backend factory."""

from taskmanager.githost.base import GitHostBackend, detect_platform
from taskmanager.secrets import get_secret_provider


def get_githost_backend(repo_url: str, config: dict | None = None) -> GitHostBackend:
    """Return the appropriate git hosting backend for a repo URL."""
    provider = get_secret_provider(config)
    platform = detect_platform(repo_url)
    if platform == "forgejo":
        from taskmanager.githost.forgejo import ForgejoBackend

        return ForgejoBackend(secret_provider=provider)
    raise ValueError(f"Unsupported git hosting platform: {platform}")
