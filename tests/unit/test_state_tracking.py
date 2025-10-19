# SPDX-FileCopyrightText: 2025-present U.N. Owen <void@some.where>
#
# SPDX-License-Identifier: MIT
import json
from pathlib import Path
from unittest.mock import Mock, patch

from localargo.manager import ClusterManager


class TestStateTracking:
    """Test suite for state tracking functionality."""

    def test_state_file_creation_on_apply(self, tmp_path):
        """Test state file is created when applying clusters."""
        yaml_content = """
clusters:
  - name: test-cluster
    provider: kind
"""
        manifest_file = tmp_path / "clusters.yaml"
        manifest_file.write_text(yaml_content)

        # Mock provider
        mock_provider = Mock()
        mock_provider.name = "test-cluster"
        mock_provider.create_cluster.return_value = True

        with patch("localargo.manager.get_provider", return_value=Mock(return_value=mock_provider)):
            manager = ClusterManager(str(manifest_file))
            manager.apply()

        # Check state file was created
        state_file = Path(".localargo/state.json")
        assert state_file.exists()

        # Check content
        with open(state_file, encoding="utf-8") as f:
            state = json.load(f)

        assert "clusters" in state
        assert len(state["clusters"]) == 1

        cluster = state["clusters"][0]
        assert cluster["name"] == "test-cluster"
        assert cluster["provider"] == "kind"
        assert cluster["last_action"] == "created"
        assert "created" in cluster
        assert "last_updated" in cluster

    def test_state_file_update_on_delete(self, tmp_path):
        """Test state file is updated when deleting clusters."""
        yaml_content = """
clusters:
  - name: test-cluster
    provider: kind
"""
        manifest_file = tmp_path / "clusters.yaml"
        manifest_file.write_text(yaml_content)

        # Mock provider
        mock_provider = Mock()
        mock_provider.name = "test-cluster"
        mock_provider.delete_cluster.return_value = True

        with patch("localargo.manager.get_provider", return_value=Mock(return_value=mock_provider)):
            manager = ClusterManager(str(manifest_file))
            manager.delete()

        # Check state file was created/updated
        state_file = Path(".localargo/state.json")
        assert state_file.exists()

        # Check content
        with open(state_file, encoding="utf-8") as f:
            state = json.load(f)

        cluster = state["clusters"][0]
        assert cluster["last_action"] == "deleted"

    def test_state_file_multiple_clusters(self, tmp_path):
        """Test state file with multiple clusters."""
        yaml_content = """
clusters:
  - name: cluster1
    provider: kind
  - name: cluster2
    provider: k3s
"""
        manifest_file = tmp_path / "clusters.yaml"
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
            manager.apply()

        # Check state file
        state_file = Path(".localargo/state.json")
        assert state_file.exists()

        with open(state_file, encoding="utf-8") as f:
            state = json.load(f)

        # Check that our test clusters are in the state file (there may be others from previous tests)
        test_clusters = [c for c in state["clusters"] if c["name"] in ["cluster1", "cluster2"]]
        assert len(test_clusters) == 2

        # Check clusters have correct data
        cluster1 = next(c for c in test_clusters if c["name"] == "cluster1")
        cluster2 = next(c for c in test_clusters if c["name"] == "cluster2")

        assert cluster1["provider"] == "kind"
        assert cluster1["last_action"] == "created"
        assert cluster2["provider"] == "k3s"
        assert cluster2["last_action"] == "created"

    def test_state_file_corrupted_recovery(self, tmp_path):
        """Test state file recovery when corrupted."""
        yaml_content = """
clusters:
  - name: test-cluster
    provider: kind
"""
        manifest_file = tmp_path / "clusters.yaml"
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

        with open(state_file, encoding="utf-8") as f:
            state = json.load(f)

        assert state["clusters"][0]["name"] == "test-cluster"

    def test_state_file_directory_creation(self, tmp_path):
        """Test state directory is created if it doesn't exist."""
        yaml_content = """
clusters:
  - name: test-cluster
    provider: kind
"""
        manifest_file = tmp_path / "clusters.yaml"
        manifest_file.write_text(yaml_content)

        # Ensure .localargo directory doesn't exist
        localargo_dir = Path(".localargo")
        if localargo_dir.exists():
            import shutil

            shutil.rmtree(localargo_dir)

        # Mock provider
        mock_provider = Mock()
        mock_provider.name = "test-cluster"
        mock_provider.create_cluster.return_value = True

        with patch("localargo.manager.get_provider", return_value=Mock(return_value=mock_provider)):
            manager = ClusterManager(str(manifest_file))
            manager.apply()

        # Check directory was created
        assert localargo_dir.exists()
        assert localargo_dir.is_dir()

    def test_state_file_existing_cluster_update(self, tmp_path):
        """Test updating existing cluster in state file."""
        yaml_content = """
clusters:
  - name: test-cluster
    provider: kind
"""
        manifest_file = tmp_path / "clusters.yaml"
        manifest_file.write_text(yaml_content)

        # Create initial state file
        state_file = Path(".localargo/state.json")
        state_file.parent.mkdir(exist_ok=True)

        initial_state = {
            "clusters": [
                {
                    "name": "test-cluster",
                    "provider": "kind",
                    "created": 1000,
                    "last_action": "created",
                    "last_updated": 1000,
                }
            ]
        }
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(initial_state, f)

        # Mock provider for delete
        mock_provider = Mock()
        mock_provider.name = "test-cluster"
        mock_provider.delete_cluster.return_value = True

        with patch("localargo.manager.get_provider", return_value=Mock(return_value=mock_provider)):
            manager = ClusterManager(str(manifest_file))
            manager.delete()

        # Check state was updated
        with open(state_file, encoding="utf-8") as f:
            state = json.load(f)

        cluster = state["clusters"][0]
        assert cluster["last_action"] == "deleted"
        assert cluster["last_updated"] > 1000  # Should be newer timestamp

    def test_state_file_preserves_other_clusters(self, tmp_path):
        """Test state file preserves other clusters when updating."""
        yaml_content = """
clusters:
  - name: cluster1
    provider: kind
"""
        manifest_file = tmp_path / "clusters.yaml"
        manifest_file.write_text(yaml_content)

        # Create initial state file with multiple clusters
        state_file = Path(".localargo/state.json")
        state_file.parent.mkdir(exist_ok=True)

        initial_state = {
            "clusters": [
                {
                    "name": "cluster1",
                    "provider": "kind",
                    "created": 1000,
                    "last_action": "created",
                    "last_updated": 1000,
                },
                {
                    "name": "cluster2",
                    "provider": "k3s",
                    "created": 2000,
                    "last_action": "created",
                    "last_updated": 2000,
                },
            ]
        }
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(initial_state, f)

        # Mock provider for delete of cluster1 only
        mock_provider = Mock()
        mock_provider.name = "cluster1"
        mock_provider.delete_cluster.return_value = True

        with patch("localargo.manager.get_provider", return_value=Mock(return_value=mock_provider)):
            manager = ClusterManager(str(manifest_file))
            manager.delete()

        # Check state was updated correctly
        with open(state_file, encoding="utf-8") as f:
            state = json.load(f)

        assert len(state["clusters"]) == 2

        # cluster1 should be updated
        cluster1 = next(c for c in state["clusters"] if c["name"] == "cluster1")
        assert cluster1["last_action"] == "deleted"

        # cluster2 should be unchanged
        cluster2 = next(c for c in state["clusters"] if c["name"] == "cluster2")
        assert cluster2["last_action"] == "created"
        assert cluster2["last_updated"] == 2000
