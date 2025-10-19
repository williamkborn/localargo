"""Tests for YAML config store."""

from __future__ import annotations

from localargo.config.store import ConfigStore, _resolve_config_path, load_config, save_config


def test_resolve_config_default(monkeypatch, tmp_path):
    """Default path should resolve under HOME when no override set."""
    # Ensure no env override
    monkeypatch.delenv("LOCALARGO_CONFIG", raising=False)
    # Simulate home
    monkeypatch.setenv("HOME", str(tmp_path))
    path = _resolve_config_path()
    assert path == tmp_path / ".localargo/config.yaml"


def test_resolve_config_env_override(monkeypatch, tmp_path):
    """Environment override should take precedence over HOME default."""
    override = tmp_path / "custom.yaml"
    monkeypatch.setenv("LOCALARGO_CONFIG", str(override))
    path = _resolve_config_path()
    assert path == override


def test_load_returns_empty_when_missing(monkeypatch, tmp_path):
    """Loading from a missing file should return an empty dict."""
    monkeypatch.setenv("LOCALARGO_CONFIG", str(tmp_path / "missing.yaml"))
    assert load_config() == {}


def test_save_then_load_round_trip(monkeypatch, tmp_path):
    """Saving and then loading should round-trip the same data."""
    cfg_path = tmp_path / "cfg.yaml"
    monkeypatch.setenv("LOCALARGO_CONFIG", str(cfg_path))

    data = {"default_provider": "kind", "ui": {"color": True}}
    path_written = save_config(data)
    assert path_written == cfg_path
    assert cfg_path.exists()

    loaded = load_config()
    assert loaded == data


def test_config_store_set_and_save(monkeypatch, tmp_path):
    """ConfigStore set/save should persist values to disk."""
    cfg_path = tmp_path / "store.yaml"
    monkeypatch.setenv("LOCALARGO_CONFIG", str(cfg_path))

    store = ConfigStore()
    store.set("default_provider", "k3s")
    out_path = store.save()
    assert out_path == cfg_path

    # Verify persisted
    assert load_config()["default_provider"] == "k3s"
