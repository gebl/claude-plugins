
import pytest

import taskmanager.config as config_module
from taskmanager.config import load_config, save_config


@pytest.fixture(autouse=True)
def patch_config_path(tmp_path, monkeypatch):
    monkeypatch.setattr(config_module, "CONFIG_PATH", tmp_path / "taskmanager.yaml")


def test_load_config_missing_file_returns_empty_dict():
    result = load_config()
    assert result == {}


def test_save_then_load_roundtrip():
    data = {"team_id": "abc123", "default_project": "my-project"}
    save_config(data)
    loaded = load_config()
    assert loaded == data


def test_save_creates_parent_dirs(tmp_path, monkeypatch):
    deep_path = tmp_path / "a" / "b" / "c" / "taskmanager.yaml"
    monkeypatch.setattr(config_module, "CONFIG_PATH", deep_path)
    save_config({"key": "value"})
    assert deep_path.exists()


def test_save_overwrites_existing():
    save_config({"key": "old"})
    save_config({"key": "new"})
    loaded = load_config()
    assert loaded["key"] == "new"


def test_save_empty_dict():
    save_config({})
    loaded = load_config()
    assert loaded == {}


def test_load_preserves_types():
    data = {
        "string_val": "hello",
        "int_val": 42,
        "list_val": ["a", "b", "c"],
        "nested": {"inner": True},
    }
    save_config(data)
    loaded = load_config()
    assert loaded["string_val"] == "hello"
    assert loaded["int_val"] == 42
    assert loaded["list_val"] == ["a", "b", "c"]
    assert loaded["nested"]["inner"] is True
