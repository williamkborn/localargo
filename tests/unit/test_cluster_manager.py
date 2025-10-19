# SPDX-FileCopyrightText: 2025-present U.N. Owen <void@some.where>
#
# SPDX-License-Identifier: MIT
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from localargo.manager import ClusterManager, ClusterManagerError


class TestClusterManager:
    """Test suite for ClusterManager."""

    def test_cluster_manager_init_success(self, tmp_path):
        """Test successful cluster manager initialization."""
        yaml_content = """
clusters:
  - name: test-cluster
    provider: kind
"""
        manifest_file = tmp_path / "test.yaml"
        manifest_file.write_text(yaml_content)

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

    def test_apply_success(self, tmp_path):
        """Test successful cluster apply operation."""
        yaml_content = """
clusters:
  - name: test-cluster
    provider: kind
"""
        manifest_file = tmp_path / "test.yaml"
        manifest_file.write_text(yaml_content)

        # Mock provider
        mock_provider = Mock()
        mock_provider.name = "test-cluster"
        mock_provider.create_cluster.return_value = True

        with patch("localargo.manager.get_provider", return_value=Mock(return_value=mock_provider)):
            manager = ClusterManager(str(manifest_file))
            results = manager.apply()

        assert results == {"test-cluster": True}
        mock_provider.create_cluster.assert_called_once()

    def test_apply_multiple_clusters(self, tmp_path):
        """Test applying multiple clusters."""
        yaml_content = """
clusters:
  - name: cluster1
    provider: kind
  - name: cluster2
    provider: k3s
"""
        manifest_file = tmp_path / "test.yaml"
        manifest_file.write_text(yaml_content)

        # Mock providers
        mock_provider1 = Mock()
        mock_provider1.name = "cluster1"
        mock_provider1.create_cluster.return_value = True

        mock_provider2 = Mock()
        mock_provider2.name = "cluster2"
        mock_provider2.create_cluster.return_value = True

        def mock_get_provider(provider_name):
            if provider_name == "kind":
                return Mock(return_value=mock_provider1)
            if provider_name == "k3s":
                return Mock(return_value=mock_provider2)
            return Mock()

        with patch("localargo.manager.get_provider", side_effect=mock_get_provider):
            manager = ClusterManager(str(manifest_file))
            results = manager.apply()

        assert results == {"cluster1": True, "cluster2": True}
        mock_provider1.create_cluster.assert_called_once()
        mock_provider2.create_cluster.assert_called_once()

    def test_apply_partial_failure(self, tmp_path):
        """Test apply with partial failures."""
        yaml_content = """
clusters:
  - name: cluster1
    provider: kind
  - name: cluster2
    provider: k3s
"""
        manifest_file = tmp_path / "test.yaml"
        manifest_file.write_text(yaml_content)

        # Mock providers - one succeeds, one fails
        mock_provider1 = Mock()
        mock_provider1.name = "cluster1"
        mock_provider1.create_cluster.return_value = True

        mock_provider2 = Mock()
        mock_provider2.name = "cluster2"
        mock_provider2.create_cluster.return_value = False

        def mock_get_provider(provider_name):
            if provider_name == "kind":
                return Mock(return_value=mock_provider1)
            if provider_name == "k3s":
                return Mock(return_value=mock_provider2)
            return Mock()

        with patch("localargo.manager.get_provider", side_effect=mock_get_provider):
            manager = ClusterManager(str(manifest_file))
            results = manager.apply()

        assert results == {"cluster1": True, "cluster2": False}

    def test_apply_provider_exception(self, tmp_path):
        """Test apply handles provider exceptions."""
        yaml_content = """
clusters:
  - name: test-cluster
    provider: kind
"""
        manifest_file = tmp_path / "test.yaml"
        manifest_file.write_text(yaml_content)

        # Mock provider that raises exception
        mock_provider = Mock()
        mock_provider.name = "test-cluster"
        mock_provider.create_cluster.side_effect = Exception("Test error")

        with patch("localargo.manager.get_provider", return_value=Mock(return_value=mock_provider)):
            manager = ClusterManager(str(manifest_file))
            results = manager.apply()

        assert results == {"test-cluster": False}

    def test_delete_success(self, tmp_path):
        """Test successful cluster delete operation."""
        yaml_content = """
clusters:
  - name: test-cluster
    provider: kind
"""
        manifest_file = tmp_path / "test.yaml"
        manifest_file.write_text(yaml_content)

        # Mock provider
        mock_provider = Mock()
        mock_provider.name = "test-cluster"
        mock_provider.delete_cluster.return_value = True

        with patch("localargo.manager.get_provider", return_value=Mock(return_value=mock_provider)):
            manager = ClusterManager(str(manifest_file))
            results = manager.delete()

        assert results == {"test-cluster": True}
        mock_provider.delete_cluster.assert_called_once()

    def test_status_success(self, tmp_path):
        """Test successful cluster status operation."""
        yaml_content = """
clusters:
  - name: test-cluster
    provider: kind
"""
        manifest_file = tmp_path / "test.yaml"
        manifest_file.write_text(yaml_content)

        # Mock provider
        mock_provider = Mock()
        mock_provider.name = "test-cluster"
        mock_provider.get_cluster_status.return_value = {
            "provider": "kind",
            "name": "test-cluster",
            "exists": True,
            "ready": True,
        }

        with patch("localargo.manager.get_provider", return_value=Mock(return_value=mock_provider)):
            manager = ClusterManager(str(manifest_file))
            results = manager.status()

        assert results == {
            "test-cluster": {
                "provider": "kind",
                "name": "test-cluster",
                "exists": True,
                "ready": True,
            }
        }

    def test_status_provider_exception(self, tmp_path):
        """Test status handles provider exceptions."""
        yaml_content = """
clusters:
  - name: test-cluster
    provider: kind
"""
        manifest_file = tmp_path / "test.yaml"
        manifest_file.write_text(yaml_content)

        # Mock provider that raises exception
        mock_provider = Mock()
        mock_provider.name = "test-cluster"
        mock_provider.get_cluster_status.side_effect = Exception("Test error")

        with patch("localargo.manager.get_provider", return_value=Mock(return_value=mock_provider)):
            manager = ClusterManager(str(manifest_file))
            results = manager.status()

        expected_result = {
            "test-cluster": {
                "error": "Test error",
                "exists": False,
                "ready": False,
            }
        }
        assert results == expected_result

    def test_state_file_update_on_success(self, tmp_path):
        """Test state file is updated on successful operations."""
        yaml_content = """
clusters:
  - name: test-cluster
    provider: kind
"""
        manifest_file = tmp_path / "test.yaml"
        manifest_file.write_text(yaml_content)

        # Mock provider
        mock_provider = Mock()
        mock_provider.name = "test-cluster"
        mock_provider.create_cluster.return_value = True

        with patch("localargo.manager.get_provider", return_value=Mock(return_value=mock_provider)):
            manager = ClusterManager(str(manifest_file))
            manager.apply()

        # Check state file was created and contains expected data
        state_file = Path(".localargo/state.json")
        assert state_file.exists()

        import json

        with open(state_file, encoding="utf-8") as f:
            state = json.load(f)

        # Find our test cluster in the state (there may be others from previous tests)
        test_cluster = None
        for cluster in state["clusters"]:
            if cluster["name"] == "test-cluster":
                test_cluster = cluster
                break

        assert test_cluster is not None
        assert test_cluster["provider"] == "kind"
        assert test_cluster["last_action"] == "created"
        assert "created" in test_cluster
        assert "last_updated" in test_cluster

    def test_state_file_update_on_delete(self, tmp_path):
        """Test state file is updated on delete operations."""
        yaml_content = """
clusters:
  - name: test-cluster
    provider: kind
"""
        manifest_file = tmp_path / "test.yaml"
        manifest_file.write_text(yaml_content)

        # Mock provider
        mock_provider = Mock()
        mock_provider.name = "test-cluster"
        mock_provider.delete_cluster.return_value = True

        with patch("localargo.manager.get_provider", return_value=Mock(return_value=mock_provider)):
            manager = ClusterManager(str(manifest_file))
            manager.delete()

        # Check state file was updated
        state_file = Path(".localargo/state.json")
        assert state_file.exists()

        import json

        with open(state_file, encoding="utf-8") as f:
            state = json.load(f)

        # Find our test cluster
        test_cluster = None
        for cluster in state["clusters"]:
            if cluster["name"] == "test-cluster":
                test_cluster = cluster
                break

        assert test_cluster is not None
        assert test_cluster["last_action"] == "deleted"

    def test_state_file_corrupted_recovery(self, tmp_path):
        """Test state file recovery when corrupted."""
        yaml_content = """
clusters:
  - name: test-cluster
    provider: kind
"""
        manifest_file = tmp_path / "test.yaml"
        manifest_file.write_text(yaml_content)

        # Create corrupted state file
        state_file = Path(".localargo/state.json")
        state_file.parent.mkdir(exist_ok=True)
        state_file.write_text("invalid json content")

        # Mock provider
        mock_provider = Mock()
        mock_provider.name = "test-cluster"
        mock_provider.create_cluster.return_value = True

        with patch("localargo.manager.get_provider", return_value=Mock(return_value=mock_provider)):
            manager = ClusterManager(str(manifest_file))
            manager.apply()

        # Should still work and create valid state file
        assert state_file.exists()

        import json

        with open(state_file, encoding="utf-8") as f:
            state = json.load(f)

        assert state["clusters"][0]["name"] == "test-cluster"
