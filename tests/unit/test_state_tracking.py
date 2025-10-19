"""Tests for state tracking functionality."""

# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>
#
# SPDX-License-Identifier: MIT
import json
import shutil
from pathlib import Path
from unittest.mock import Mock, patch

from localargo.manager import ClusterManager

from ..test_utils import (
    create_manager_with_mocked_provider,
    create_multi_cluster_yaml,
    run_corrupted_state_file_test,
    run_state_file_apply_test,
    run_state_file_delete_test,
    setup_multiple_providers,
    validate_state_file_contains_cluster,
)


class TestStateTracking:
    """Test suite for state tracking functionality."""

    def test_state_file_creation_on_apply(self, create_manifest_file):
        """Test state file is created when applying clusters."""
        run_state_file_apply_test(
            create_manifest_file,
            create_cluster=Mock(return_value=True),
        )

    def test_state_file_update_on_delete(self, create_manifest_file):
        """Test state file is updated when deleting clusters."""
        run_state_file_delete_test(
            create_manifest_file,
            delete_cluster=Mock(return_value=True),
        )

    def test_state_file_multiple_clusters(self, create_manifest_file):
        """Test state file with multiple clusters."""
        yaml_content = create_multi_cluster_yaml()
        manifest_file = create_manifest_file(yaml_content, "multi-clusters.yaml")

        mock_get_provider, _ = setup_multiple_providers(
            {
                "kind": {"create_cluster": Mock(return_value=True)},
                "k3s": {"create_cluster": Mock(return_value=True)},
            }
        )

        with patch("localargo.manager.get_provider", side_effect=mock_get_provider):
            manager = ClusterManager(str(manifest_file))
            manager.apply()

        # Check state file
        state_file = Path(".localargo/state.json")
        validate_state_file_contains_cluster(
            state_file,
            [
                {"name": "cluster1", "provider": "kind", "last_action": "created"},
                {"name": "cluster2", "provider": "k3s", "last_action": "created"},
            ],
        )

    def test_state_file_corrupted_recovery(self, create_manifest_file):
        """Test state file recovery when corrupted."""
        run_corrupted_state_file_test(
            create_manifest_file, create_cluster=Mock(return_value=True)
        )

    def test_state_file_directory_creation(self, create_manifest_file):
        """Test state directory is created if it doesn't exist."""
        manifest_file = create_manifest_file(filename="clusters.yaml")

        # Ensure .localargo directory doesn't exist
        localargo_dir = Path(".localargo")
        if localargo_dir.exists():
            shutil.rmtree(localargo_dir)

        manager, _mock_provider = create_manager_with_mocked_provider(
            manifest_file, create_cluster=Mock(return_value=True)
        )
        manager.apply()

        # Check directory was created
        assert localargo_dir.exists()
        assert localargo_dir.is_dir()

    def test_state_file_existing_cluster_update(self, create_manifest_file):
        """Test updating existing cluster in state file."""
        manifest_file = create_manifest_file(filename="clusters.yaml")

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

        manager, _mock_provider = create_manager_with_mocked_provider(
            manifest_file, delete_cluster=Mock(return_value=True)
        )
        manager.delete()

        # Check state was updated
        with open(state_file, encoding="utf-8") as f:
            state = json.load(f)

        cluster = state["clusters"][0]
        assert cluster["last_action"] == "deleted"
        assert cluster["last_updated"] > 1000  # Should be newer timestamp

    def test_state_file_preserves_other_clusters(self, create_manifest_file):
        """Test state file preserves other clusters when updating."""
        yaml_content = """
clusters:
  - name: cluster1
    provider: kind
"""
        manifest_file = create_manifest_file(yaml_content, "preserve-clusters.yaml")

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

        manager, _mock_provider = create_manager_with_mocked_provider(
            manifest_file, delete_cluster=Mock(return_value=True)
        )
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
