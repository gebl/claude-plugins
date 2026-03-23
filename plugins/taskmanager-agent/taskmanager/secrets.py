"""Pluggable secret provider abstraction."""

from __future__ import annotations

import os
from typing import Protocol, runtime_checkable


@runtime_checkable
class SecretProvider(Protocol):
    """Protocol for retrieving secrets by key."""

    def get(self, key: str, default: str = "") -> str: ...


class EnvSecretProvider:
    """Retrieves secrets from environment variables."""

    def get(self, key: str, default: str = "") -> str:
        return os.environ.get(key, default)


def get_secret_provider(config: dict | None = None) -> SecretProvider:
    """Factory that returns a SecretProvider based on config.

    Reads ``config["secrets"]["provider"]`` to select the implementation.
    Defaults to ``"env"`` when the key is absent.
    """
    provider_name = (config or {}).get("secrets", {}).get("provider", "env")
    if provider_name == "env":
        return EnvSecretProvider()
    raise ValueError(f"Unknown secret provider: {provider_name}")
