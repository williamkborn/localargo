"""Tests for cluster manager functionality."""

# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>
#
# SPDX-License-Identifier: MIT
from unittest.mock import Mock, patch

import pytest

from localargo.manager import ClusterManager, ClusterManagerError

from ..test_utils import (
    create_manager_with_mocked_provider,
    create_multi_cluster_yaml,
    setup_multiple_providers,
)


class TestClusterManager:
    """Test suite for ClusterManager."""

    def test_cluster_manager_init_success(self, create_manifest_file):
        """Test successful cluster manager initialization."""
        manifest_file = create_manifest_file()

        manager = ClusterManager(str(manifest_file))

        assert len(manager.manifest.clusters) == 1
        assert manager.manifest.clusters[0].name == "test-cluster"
        assert len(manager.providers) == 1

    def test_cluster_manager_init_manifest_error(self, tmp_path):
        """Test cluster manager init raises error on manifest failure."""
        manifest_file = tmp_path / "invalid.yaml"
        manifest_file.write_text("invalid: yaml: content")

        with pytest.raises(ClusterManagerError, match="Failed to load manifest"):
            ClusterManager(str(manifest_file))

    def test_apply_success(self, create_manifest_file):
        """Test successful cluster apply operation."""
        manifest_file = create_manifest_file()

        manager, _mock_provider = create_manager_with_mocked_provider(
            manifest_file, create_cluster=Mock(return_value=True)
        )
        results = manager.apply()

        assert results == {"test-cluster": True}

    def test_apply_multiple_clusters(self, create_manifest_file):
        """Test applying multiple clusters."""
        yaml_content = create_multi_cluster_yaml()
        manifest_file = create_manifest_file(yaml_content, "multi-cluster.yaml")

        mock_get_provider, mock_providers = setup_multiple_providers(
            {
                "kind": {"create_cluster": Mock(return_value=True)},
                "k3s": {"create_cluster": Mock(return_value=True)},
            }
        )

        with patch("localargo.manager.get_provider", side_effect=mock_get_provider):
            manager = ClusterManager(str(manifest_file))
            results = manager.apply()

        assert results == {"cluster1": True, "cluster2": True}
        mock_providers[0].create_cluster.assert_called_once()
        mock_providers[1].create_cluster.assert_called_once()

    def test_apply_partial_failure(self, create_manifest_file):
        """Test apply with partial failures."""
        yaml_content = create_multi_cluster_yaml()
        manifest_file = create_manifest_file(yaml_content, "partial-failure.yaml")

        mock_get_provider, _ = setup_multiple_providers(
            {
                "kind": {"create_cluster": Mock(return_value=True)},
                "k3s": {"create_cluster": Mock(return_value=False)},
            }
        )

        with patch("localargo.manager.get_provider", side_effect=mock_get_provider):
            manager = ClusterManager(str(manifest_file))
            results = manager.apply()

        assert results == {"cluster1": True, "cluster2": False}

    def test_apply_provider_exception(self, create_manifest_file):
        """Test apply handles provider exceptions."""
        manifest_file = create_manifest_file()

        manager, _mock_provider = create_manager_with_mocked_provider(
            manifest_file, create_cluster=Mock(side_effect=RuntimeError("Test error"))
        )
        results = manager.apply()

        assert results == {"test-cluster": False}

    def test_delete_success(self, create_manifest_file):
        """Test successful cluster delete operation."""
        manifest_file = create_manifest_file()

        manager, _mock_provider = create_manager_with_mocked_provider(
            manifest_file, delete_cluster=Mock(return_value=True)
        )
        results = manager.delete()

        assert results == {"test-cluster": True}

    def test_status_success(self, create_manifest_file):
        """Test successful cluster status operation."""
        manifest_file = create_manifest_file()

        status_result = {
            "provider": "kind",
            "name": "test-cluster",
            "exists": True,
            "ready": True,
        }
        manager, _mock_provider = create_manager_with_mocked_provider(
            manifest_file,
            get_cluster_status=Mock(return_value=status_result),
        )
        results = manager.status()

        assert results == {"test-cluster": status_result}

    def test_status_provider_exception(self, create_manifest_file):
        """Test status handles provider exceptions."""
        manifest_file = create_manifest_file()

        manager, _mock_provider = create_manager_with_mocked_provider(
            manifest_file,
            get_cluster_status=Mock(side_effect=RuntimeError("Test error")),
        )
        results = manager.status()

        expected_result = {
            "test-cluster": {
                "error": "Test error",
                "exists": False,
                "ready": False,
            }
        }
        assert results == expected_result
