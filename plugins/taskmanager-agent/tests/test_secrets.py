"""Tests for the pluggable secret provider module."""

from __future__ import annotations

import pytest

from taskmanager.secrets import EnvSecretProvider, SecretProvider, get_secret_provider


class TestSecretProviderProtocol:
    def test_env_provider_is_secret_provider(self):
        assert isinstance(EnvSecretProvider(), SecretProvider)

    def test_custom_provider_satisfies_protocol(self):
        class DictProvider:
            def __init__(self, data: dict[str, str]) -> None:
                self._data = data

            def get(self, key: str, default: str = "") -> str:
                return self._data.get(key, default)

        provider = DictProvider({"MY_KEY": "my_value"})
        assert isinstance(provider, SecretProvider)


class TestEnvSecretProvider:
    def test_reads_from_environment(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("TEST_SECRET_KEY", "secret123")
        provider = EnvSecretProvider()
        assert provider.get("TEST_SECRET_KEY") == "secret123"

    def test_returns_default_when_missing(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("NONEXISTENT_KEY", raising=False)
        provider = EnvSecretProvider()
        assert provider.get("NONEXISTENT_KEY", "fallback") == "fallback"

    def test_returns_empty_string_default(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("NONEXISTENT_KEY", raising=False)
        provider = EnvSecretProvider()
        assert provider.get("NONEXISTENT_KEY") == ""


class TestGetSecretProvider:
    def test_default_returns_env_provider(self):
        provider = get_secret_provider()
        assert isinstance(provider, EnvSecretProvider)

    def test_none_config_returns_env_provider(self):
        provider = get_secret_provider(None)
        assert isinstance(provider, EnvSecretProvider)

    def test_empty_config_returns_env_provider(self):
        provider = get_secret_provider({})
        assert isinstance(provider, EnvSecretProvider)

    def test_explicit_env_returns_env_provider(self):
        provider = get_secret_provider({"secrets": {"provider": "env"}})
        assert isinstance(provider, EnvSecretProvider)

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown secret provider: vault"):
            get_secret_provider({"secrets": {"provider": "vault"}})


class TestLinearBackendWithProvider:
    def test_uses_injected_provider(self):
        from taskmanager.backends.linear import LinearBackend

        class StubProvider:
            def get(self, key: str, default: str = "") -> str:
                if key == "TASKMANAGER_AGENT_LINEAR_TOKEN":
                    return "injected-token"
                return default

        backend = LinearBackend(
            config={"linear": {"token_env": "TASKMANAGER_AGENT_LINEAR_TOKEN"}},
            secret_provider=StubProvider(),
        )
        assert backend._token == "injected-token"

    def test_token_param_takes_precedence(self):
        from taskmanager.backends.linear import LinearBackend

        class StubProvider:
            def get(self, key: str, default: str = "") -> str:
                return "provider-token"

        backend = LinearBackend(
            config={},
            token="explicit-token",
            secret_provider=StubProvider(),
        )
        assert backend._token == "explicit-token"


class TestForgejoBackendWithProvider:
    def test_uses_injected_provider(self):
        from taskmanager.githost.forgejo import ForgejoBackend

        class StubProvider:
            def get(self, key: str, default: str = "") -> str:
                if key == "TASKMANAGER_AGENT_FORGEJO_TOKEN":
                    return "forgejo-injected"
                return default

        backend = ForgejoBackend(secret_provider=StubProvider())
        assert backend._token == "forgejo-injected"

    def test_custom_token_env(self):
        from taskmanager.githost.forgejo import ForgejoBackend

        class StubProvider:
            def get(self, key: str, default: str = "") -> str:
                if key == "MY_TASKMANAGER_AGENT_FORGEJO_TOKEN":
                    return "custom-env-token"
                return default

        backend = ForgejoBackend(
            secret_provider=StubProvider(),
            token_env="MY_TASKMANAGER_AGENT_FORGEJO_TOKEN",
        )
        assert backend._token == "custom-env-token"
