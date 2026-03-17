"""Backend factory."""

from taskmanager.backends.base import TaskBackend


def get_backend() -> TaskBackend:
    """Instantiate the configured backend."""
    from taskmanager.config import load_config

    config = load_config()
    backend_name = config.get("backend", "linear")
    if backend_name == "linear":
        from taskmanager.backends.linear import LinearBackend

        return LinearBackend(config)
    raise ValueError(f"Unknown backend: {backend_name}")
