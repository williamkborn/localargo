# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Declarative cluster manifest loader and validator."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from localargo.providers.registry import get_provider

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]


class ManifestError(Exception):
    """Base exception for manifest-related errors."""


class ManifestValidationError(ManifestError):
    """Raised when manifest validation fails."""


@dataclass
class ClusterConfig:
    """Configuration for a single cluster."""

    name: str
    provider: str
    kwargs: dict[str, Any] = field(default_factory=dict)

    def __init__(self, name: str, provider: str, **kwargs: Any) -> None:
        self.name = name
        self.provider = provider
        self.kwargs = kwargs

    def __repr__(self) -> str:
        kwargs_str = f", kwargs={self.kwargs!r}" if self.kwargs else ""
        return f"ClusterConfig(name={self.name!r}, provider={self.provider!r}{kwargs_str})"


@dataclass
class ClusterManifest:
    """Cluster manifest containing multiple cluster configurations."""

    clusters: list[ClusterConfig]


def load_manifest(manifest_path: str | Path) -> ClusterManifest:
    """
    Load cluster manifest from YAML file.

    Args:
        manifest_path (str | Path): Path to YAML manifest file

    Returns:
        ClusterManifest: Loaded cluster manifest object

    Raises:
        ManifestError: If manifest cannot be loaded or is invalid
    """
    manifest_path = Path(manifest_path)

    if not manifest_path.exists():
        msg = f"Manifest file not found: {manifest_path}"
        raise ManifestError(msg)

    if yaml is None:
        msg = "PyYAML is required to load manifests. Install with: pip install PyYAML"
        raise ManifestError(msg)

    try:
        with open(manifest_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception as e:
        msg = f"Failed to parse manifest file {manifest_path}: {e}"
        raise ManifestError(msg) from e

    return _parse_manifest_data(data)


def _parse_manifest_data(data: Any) -> ClusterManifest:
    """
    Parse manifest data and validate structure.

    Args:
        data (Any): Parsed YAML data

    Returns:
        ClusterManifest: Validated cluster manifest object

    Raises:
        ManifestValidationError: If data structure is invalid
    """
    if not isinstance(data, dict):
        msg = f"Manifest must be a dictionary, got {type(data)}"
        raise ManifestValidationError(msg)

    if "clusters" not in data:
        msg = "Manifest must contain 'clusters' key"
        raise ManifestValidationError(msg)

    clusters_data = data["clusters"]
    if not isinstance(clusters_data, list):
        msg = "Manifest 'clusters' must be a list"
        raise ManifestValidationError(msg)

    clusters = []
    for i, cluster_data in enumerate(clusters_data):
        try:
            cluster = _parse_cluster_data(cluster_data, i)
            clusters.append(cluster)
        except ManifestValidationError as e:
            msg = f"Error in cluster {i}: {e}"
            raise ManifestValidationError(msg) from e

    return ClusterManifest(clusters)


def _parse_cluster_data(cluster_data: Any, index: int) -> ClusterConfig:
    """
    Parse individual cluster configuration.

    Args:
        cluster_data (Any): Cluster configuration data
        index (int): Cluster index for error reporting

    Returns:
        ClusterConfig: Parsed cluster configuration object
    """
    _validate_cluster_data_type(cluster_data, index)
    _validate_required_fields(cluster_data, index)

    name = cluster_data["name"]
    provider_name = cluster_data["provider"]

    _validate_field_types(name, provider_name, index)
    _validate_provider_exists(provider_name, index)

    kwargs = _extract_additional_kwargs(cluster_data)

    return ClusterConfig(name=name, provider=provider_name, **kwargs)


def _validate_cluster_data_type(cluster_data: Any, index: int) -> None:
    """Validate that cluster data is a dictionary."""
    if not isinstance(cluster_data, dict):
        msg = f"Cluster {index} must be a dictionary"
        raise ManifestValidationError(msg)


def _validate_required_fields(cluster_data: dict[str, Any], index: int) -> None:
    """Validate that required fields are present."""
    if "name" not in cluster_data:
        msg = f"Cluster {index} missing required 'name' field"
        raise ManifestValidationError(msg)

    if "provider" not in cluster_data:
        msg = f"Cluster {index} missing required 'provider' field"
        raise ManifestValidationError(msg)


def _validate_field_types(name: Any, provider_name: Any, index: int) -> None:
    """Validate that name and provider fields are strings."""
    if not isinstance(name, str):
        msg = f"Cluster {index} 'name' must be a string"
        raise ManifestValidationError(msg)

    if not isinstance(provider_name, str):
        msg = f"Cluster {index} 'provider' must be a string"
        raise ManifestValidationError(msg)


def _validate_provider_exists(provider_name: str, index: int) -> None:
    """Validate that the provider exists."""
    try:
        get_provider(provider_name)
    except ValueError as e:
        msg = f"Cluster {index}: {e}"
        raise ManifestValidationError(msg) from e


def _extract_additional_kwargs(cluster_data: dict[str, Any]) -> dict[str, Any]:
    """Extract additional kwargs excluding name and provider."""
    return {k: v for k, v in cluster_data.items() if k not in ("name", "provider")}


def validate_manifest(manifest_path: str | Path) -> bool:
    """
    Validate manifest file without loading it.

    Args:
        manifest_path (str | Path): Path to manifest file

    Returns:
        bool: True if manifest is valid
    """
    load_manifest(manifest_path)
    return True
