"""YAML-backed persistent config store for LocalArgo.

Supports default path at ~/.localargo/config.yaml and override via
LOCALARGO_CONFIG environment variable. Provides simple load/save helpers
and a small class wrapper to interact with nested dict-like configs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_RELATIVE = Path(".localargo/config.yaml")
ENV_OVERRIDE = "LOCALARGO_CONFIG"


def _resolve_config_path() -> Path:
    """Resolve the config file path honoring the environment override."""
    env_path = os.getenv(ENV_OVERRIDE)
    if env_path:
        return Path(env_path).expanduser()
    return Path.home() / DEFAULT_CONFIG_RELATIVE


def load_config() -> dict[str, Any]:
    """Load configuration from disk; return empty dict if missing or empty."""
    path = _resolve_config_path()
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            return {}
        return data


def save_config(config: dict[str, Any]) -> Path:
    """Persist configuration to disk, creating parent directory as needed."""
    path = _resolve_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, sort_keys=True)
    return path


@dataclass
class ConfigStore:
    """Small dict-like wrapper for LocalArgo config with persistence helpers."""

    data: dict[str, Any] = field(default_factory=load_config)

    def get(self, key: str, default: Any | None = None) -> Any | None:
        """Return the value for key if present, else default."""
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a configuration key to the provided value."""
        self.data[key] = value

    def save(self) -> Path:
        """Persist current configuration to disk and return the file path."""
        return save_config(self.data)
