"""Test utilities and helper functions for reducing code duplication."""

import json
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

from localargo.manager import ClusterManager


def create_manager_with_mocked_provider(
    manifest_file: Path,
    provider_name: str = "kind",
    mock_provider: Mock | None = None,
    **provider_kwargs: Any,
) -> tuple[ClusterManager, Mock]:
    """Create a ClusterManager with a mocked provider.

    Args:
        manifest_file (Path): Path to the manifest file
        provider_name (str): Name of the provider to mock (default: "kind")
        mock_provider (Mock | None): Pre-configured mock provider (optional)
        **provider_kwargs (Any): Additional kwargs for create_mock_provider

    Returns:
        tuple[ClusterManager, Mock]: (ClusterManager instance, mock_provider)
    """
    if mock_provider is None:
        mock_provider = create_mock_provider(provider_name=provider_name, **provider_kwargs)

    with patch(
        "localargo.manager.get_provider", return_value=Mock(return_value=mock_provider)
    ):
        manager = ClusterManager(str(manifest_file))

    return manager, mock_provider


def create_mock_provider(provider_name: str = "kind", **kwargs: Any) -> Mock:
    """Create a mock provider with specified attributes.

    Args:
        provider_name (str): Name of the provider
        **kwargs (Any): Additional attributes to set on the mock

    Returns:
        Mock: Mock provider instance
    """
    mock_provider = Mock()
    mock_provider.name = provider_name

    # Set any additional attributes passed in kwargs
    for key, value in kwargs.items():
        setattr(mock_provider, key, value)

    return mock_provider


def setup_multiple_providers(
    provider_configs: dict[str, dict[str, Any]],
) -> tuple[Any, list[Mock]]:
    """Set up multiple mock providers for testing.

    Args:
        provider_configs (dict[str, dict[str, Any]]): Dict mapping provider names
            to provider configs. Example: {"kind": {"create_cluster": Mock(return_value=True)}}

    Returns:
        tuple[Any, list[Mock]]: (mock_get_provider function, list of mock providers)
    """
    mock_providers = {}
    for provider_name, config in provider_configs.items():
        mock_providers[provider_name] = create_mock_provider(provider_name, **config)

    def mock_get_provider(provider_name):
        return Mock(return_value=mock_providers.get(provider_name, Mock()))

    return mock_get_provider, list(mock_providers.values())


def validate_state_file_contains_cluster(
    state_file_path: Path,
    expected_clusters: list[dict[str, Any]],
    *,
    check_timestamps: bool = True,
) -> None:
    """Validate that state file contains expected cluster information.

    Args:
        state_file_path (Path): Path to the state file
        expected_clusters (list[dict[str, Any]]): List of dicts with expected cluster data
        check_timestamps (bool): Whether to check for timestamp fields
    """
    assert state_file_path.exists()

    with open(state_file_path, encoding="utf-8") as f:
        state = json.load(f)

    assert "clusters" in state

    for expected_cluster in expected_clusters:
        # Find the cluster in state
        cluster = None
        for c in state["clusters"]:
            if c["name"] == expected_cluster["name"]:
                cluster = c
                break

        assert cluster is not None, f"Cluster {expected_cluster['name']} not found in state"

        # Check expected fields
        for key, expected_value in expected_cluster.items():
            assert (
                cluster[key] == expected_value
            ), f"Cluster {expected_cluster['name']}: {key} != {expected_value}"

        # Check timestamps if requested
        if check_timestamps:
            assert "created" in cluster
            assert "last_updated" in cluster


def get_test_cluster_from_state(
    state_file_path: Path, cluster_name: str
) -> dict[str, Any] | None:
    """Get a specific cluster from the state file.

    Args:
        state_file_path (Path): Path to the state file
        cluster_name (str): Name of the cluster to find

    Returns:
        dict[str, Any] | None: Cluster data from state file
    """
    assert state_file_path.exists()

    with open(state_file_path, encoding="utf-8") as f:
        state = json.load(f)

    for cluster in state["clusters"]:
        if cluster["name"] == cluster_name:
            return cluster

    return None


def create_multi_cluster_yaml(cluster_configs: list[dict[str, str]] | None = None) -> str:
    """Create YAML content for multiple clusters.

    Args:
        cluster_configs (list[dict[str, str]] | None): List of dicts with cluster configuration.
                        If None, uses default two-cluster setup.

    Returns:
        str: YAML content string
    """
    if cluster_configs is None:
        cluster_configs = [
            {"name": "cluster1", "provider": "kind"},
            {"name": "cluster2", "provider": "k3s"},
        ]

    yaml_lines = ["clusters:"]
    for config in cluster_configs:
        yaml_lines.append(f"  - name: {config['name']}")
        yaml_lines.append(f"    provider: {config['provider']}")

    return "\n".join(yaml_lines)


def run_state_file_test(
    create_manifest_file: Any,
    operation: Any,
    expected_clusters: list[dict[str, Any]],
    **provider_kwargs: Any,
) -> tuple[ClusterManager, Mock]:
    """Helper function to run common state file tests.

    Args:
        create_manifest_file (Any): Fixture to create manifest file
        operation (Any): Function that takes (manager, mock_provider) and performs the operation
        expected_clusters (list[dict[str, Any]]): List of expected cluster data in state file
        **provider_kwargs (Any): Additional kwargs for provider mocking

    Returns:
        tuple[ClusterManager, Mock]: (manager, mock_provider) for additional assertions if needed
    """
    manifest_file = create_manifest_file()

    manager, mock_provider = create_manager_with_mocked_provider(
        manifest_file, **provider_kwargs
    )

    operation(manager, mock_provider)

    # Check state file was created and contains expected data
    state_file = Path(".localargo/state.json")
    validate_state_file_contains_cluster(state_file, expected_clusters)

    return manager, mock_provider


def run_corrupted_state_file_test(
    create_manifest_file: Any, **provider_kwargs: Any
) -> tuple[ClusterManager, Mock]:
    """Helper function to test state file recovery when corrupted.

    Args:
        create_manifest_file (Any): Fixture to create manifest file
        **provider_kwargs (Any): Additional kwargs for provider mocking

    Returns:
        tuple[ClusterManager, Mock]: (manager, mock_provider) for additional assertions if needed
    """
    manifest_file = create_manifest_file()

    # Create corrupted state file
    state_file = Path(".localargo/state.json")
    state_file.parent.mkdir(exist_ok=True)
    state_file.write_text("invalid json content", encoding="utf-8")

    manager, mock_provider = create_manager_with_mocked_provider(
        manifest_file, **provider_kwargs
    )
    manager.apply()

    # Should still work and create valid state file
    validate_state_file_contains_cluster(
        state_file, [{"name": "test-cluster"}], check_timestamps=False
    )

    return manager, mock_provider


def run_state_file_apply_test(
    create_manifest_file: Any,
    expected_clusters: list[dict[str, Any]] | None = None,
    **provider_kwargs: Any,
) -> tuple[ClusterManager, Mock]:
    """Helper function to test state file creation/update on apply operations.

    Args:
        create_manifest_file (Any): Fixture to create manifest file
        expected_clusters (list[dict[str, Any]] | None): List of expected cluster data.
            Defaults to single test-cluster.
        **provider_kwargs (Any): Additional kwargs for provider mocking

    Returns:
        tuple[ClusterManager, Mock]: (manager, mock_provider) for additional assertions if needed
    """
    if expected_clusters is None:
        expected_clusters = [
            {"name": "test-cluster", "provider": "kind", "last_action": "created"}
        ]

    def operation(manager, _mock_provider):
        manager.apply()

    return run_state_file_test(
        create_manifest_file, operation, expected_clusters, **provider_kwargs
    )


def run_state_file_delete_test(
    create_manifest_file: Any,
    expected_clusters: list[dict[str, Any]] | None = None,
    **provider_kwargs: Any,
) -> tuple[ClusterManager, Mock]:
    """Helper function to test state file update on delete operations.

    Args:
        create_manifest_file (Any): Fixture to create manifest file
        expected_clusters (list[dict[str, Any]] | None): List of expected cluster data.
            Defaults to single test-cluster.
        **provider_kwargs (Any): Additional kwargs for provider mocking

    Returns:
        tuple[ClusterManager, Mock]: (manager, mock_provider) for additional assertions if needed
    """
    if expected_clusters is None:
        expected_clusters = [{"name": "test-cluster", "last_action": "deleted"}]

    def operation(manager, _mock_provider):
        manager.delete()

    return run_state_file_test(
        create_manifest_file, operation, expected_clusters, **provider_kwargs
    )
