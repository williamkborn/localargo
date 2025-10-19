# SPDX-FileCopyrightText: 2025-present U.N. Owen <void@some.where>
#
# SPDX-License-Identifier: MIT
from __future__ import annotations

from pathlib import Path
from typing import Any

from localargo.providers.registry import get_provider

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

"""Declarative cluster manifest loader and validator."""


class ManifestError(Exception):
    """Base exception for manifest-related errors."""


class ManifestValidationError(ManifestError):
    """Raised when manifest validation fails."""


class ClusterConfig:
    """Configuration for a single cluster."""

    def __init__(self, name: str, provider: str, **kwargs: Any):
        """
        Initialize cluster configuration.

        Args:
            name: Name of the cluster
            provider: Provider name (e.g., 'kind', 'k3s')
            **kwargs: Additional provider-specific configuration
        """
        self.name = name
        self.provider = provider
        self.kwargs = kwargs

    def __repr__(self) -> str:
        return f"ClusterConfig(name={self.name!r}, provider={self.provider!r})"


class ClusterManifest:
    """Cluster manifest containing multiple cluster configurations."""

    def __init__(self, clusters: list[ClusterConfig]):
        """
        Initialize cluster manifest.

        Args:
            clusters: List of cluster configurations
        """
        self.clusters = clusters

    def __repr__(self) -> str:
        return f"ClusterManifest(clusters={self.clusters!r})"


def load_manifest(manifest_path: str | Path) -> ClusterManifest:
    """
    Load cluster manifest from YAML file.

    Args:
        manifest_path: Path to YAML manifest file

    Returns:
        ClusterManifest object

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
        data: Parsed YAML data
        manifest_path: Path to manifest file for error reporting

    Returns:
        ClusterManifest object

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
        cluster_data: Cluster configuration data
        manifest_path: Path to manifest file for error reporting
        index: Cluster index for error reporting

    Returns:
        ClusterConfig object

    Raises:
        ManifestValidationError: If cluster data is invalid
    """
    if not isinstance(cluster_data, dict):
        msg = f"Cluster {index} must be a dictionary"
        raise ManifestValidationError(msg)

    # Required fields
    if "name" not in cluster_data:
        msg = f"Cluster {index} missing required 'name' field"
        raise ManifestValidationError(msg)

    if "provider" not in cluster_data:
        msg = f"Cluster {index} missing required 'provider' field"
        raise ManifestValidationError(msg)

    name = cluster_data["name"]
    provider_name = cluster_data["provider"]

    if not isinstance(name, str):
        msg = f"Cluster {index} 'name' must be a string"
        raise ManifestValidationError(msg)

    if not isinstance(provider_name, str):
        msg = f"Cluster {index} 'provider' must be a string"
        raise ManifestValidationError(msg)

    # Validate provider exists
    try:
        get_provider(provider_name)
    except ValueError as e:
        msg = f"Cluster {index}: {e}"
        raise ManifestValidationError(msg) from e

    # Extract additional kwargs (everything except name and provider)
    kwargs = {k: v for k, v in cluster_data.items() if k not in ("name", "provider")}

    return ClusterConfig(name=name, provider=provider_name, **kwargs)


def validate_manifest(manifest_path: str | Path) -> bool:
    """
    Validate manifest file without loading it.

    Args:
        manifest_path: Path to manifest file

    Returns:
        True if manifest is valid

    Raises:
        ManifestError: If manifest is invalid
    """
    load_manifest(manifest_path)
    return True
