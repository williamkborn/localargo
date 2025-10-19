"""Tests for CLI cluster commands."""

# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>
#
# SPDX-License-Identifier: MIT
from unittest.mock import patch

from click.testing import CliRunner

from localargo.cli.commands.cluster import apply, delete, status_manifest
from localargo.manager import ClusterManagerError

from ..test_utils import create_multi_cluster_yaml


class TestCLICluster:
    """Test suite for cluster CLI commands."""

    def test_apply_command_success(self, create_manifest_file, create_mock_cluster_manager):
        """Test apply command with successful cluster creation."""
        manifest_file = create_manifest_file()

        mock_manager = create_mock_cluster_manager({"test-cluster": True})

        with patch("localargo.cli.commands.cluster.ClusterManager", return_value=mock_manager):
            runner = CliRunner()
            result = runner.invoke(apply, [str(manifest_file)])

        assert result.exit_code == 0
        # Check that the command ran without error and step logger was used
        assert "Starting workflow" in result.output
        assert "loading manifest" in result.output
        assert "✅" in result.output  # Step logger success indicators

    def test_apply_command_partial_success(
        self, create_manifest_file, create_mock_cluster_manager
    ):
        """Test apply command with partial success."""
        yaml_content = create_multi_cluster_yaml()
        manifest_file = create_manifest_file(yaml_content)

        mock_manager = create_mock_cluster_manager({"cluster1": True, "cluster2": False})

        with patch("localargo.cli.commands.cluster.ClusterManager", return_value=mock_manager):
            runner = CliRunner()
            result = runner.invoke(apply, [str(manifest_file)])

        assert result.exit_code == 0

    def test_apply_command_unexpected_error(self, create_manifest_file):
        """Test apply command with unexpected error."""
        manifest_file = create_manifest_file()

        with patch("localargo.cli.commands.cluster.ClusterManager") as mock_class:
            mock_class.side_effect = Exception("Unexpected error")

            runner = CliRunner()
            result = runner.invoke(apply, [str(manifest_file)])

        assert result.exit_code == 1

    def test_delete_command_success(self, create_manifest_file, create_mock_cluster_manager):
        """Test delete command with successful cluster deletion."""
        manifest_file = create_manifest_file()

        mock_manager = create_mock_cluster_manager({"test-cluster": True})

        with patch("localargo.cli.commands.cluster.ClusterManager", return_value=mock_manager):
            runner = CliRunner()
            result = runner.invoke(delete, [str(manifest_file)])

        assert result.exit_code == 0

    def test_delete_command_manifest_error(self, create_manifest_file):
        """Test delete command with manifest error."""
        manifest_file = create_manifest_file("invalid: yaml: content", "invalid.yaml")

        with patch("localargo.cli.commands.cluster.ClusterManager") as mock_class:
            mock_class.side_effect = ClusterManagerError("Failed to load manifest")

            runner = CliRunner()
            result = runner.invoke(delete, [str(manifest_file)])

        assert result.exit_code == 1

    def test_status_command_success(self, create_manifest_file, create_mock_cluster_manager):
        """Test status command with successful cluster status."""
        manifest_file = create_manifest_file()

        mock_manager = create_mock_cluster_manager(
            {
                "test-cluster": {
                    "provider": "kind",
                    "name": "test-cluster",
                    "exists": True,
                    "ready": True,
                }
            }
        )

        with patch("localargo.cli.commands.cluster.ClusterManager", return_value=mock_manager):
            runner = CliRunner()
            result = runner.invoke(status_manifest, [str(manifest_file)])

        assert result.exit_code == 0

    def test_status_command_not_ready_cluster(
        self, create_manifest_file, create_mock_cluster_manager
    ):
        """Test status command with not ready cluster."""
        manifest_file = create_manifest_file()

        mock_manager = create_mock_cluster_manager(
            {
                "test-cluster": {
                    "provider": "kind",
                    "name": "test-cluster",
                    "exists": True,
                    "ready": False,
                }
            }
        )

        with patch("localargo.cli.commands.cluster.ClusterManager", return_value=mock_manager):
            runner = CliRunner()
            result = runner.invoke(status_manifest, [str(manifest_file)])

        assert result.exit_code == 0

    def test_status_command_missing_cluster(
        self, create_manifest_file, create_mock_cluster_manager
    ):
        """Test status command with missing cluster."""
        manifest_file = create_manifest_file()

        mock_manager = create_mock_cluster_manager(
            {
                "test-cluster": {
                    "provider": "kind",
                    "name": "test-cluster",
                    "exists": False,
                    "ready": False,
                }
            }
        )

        with patch("localargo.cli.commands.cluster.ClusterManager", return_value=mock_manager):
            runner = CliRunner()
            result = runner.invoke(status_manifest, [str(manifest_file)])

        assert result.exit_code == 0

    def test_status_command_with_error(
        self, create_manifest_file, create_mock_cluster_manager
    ):
        """Test status command with cluster error."""
        manifest_file = create_manifest_file()

        mock_manager = create_mock_cluster_manager(
            {
                "test-cluster": {
                    "error": "Connection failed",
                    "exists": False,
                    "ready": False,
                }
            }
        )

        with patch("localargo.cli.commands.cluster.ClusterManager", return_value=mock_manager):
            runner = CliRunner()
            result = runner.invoke(status_manifest, [str(manifest_file)])

        assert result.exit_code == 0

    def test_status_command_multiple_clusters(
        self, create_manifest_file, create_mock_cluster_manager
    ):
        """Test status command with multiple clusters."""
        yaml_content = create_multi_cluster_yaml()
        manifest_file = create_manifest_file(yaml_content)

        mock_manager = create_mock_cluster_manager(
            {
                "cluster1": {
                    "provider": "kind",
                    "name": "cluster1",
                    "exists": True,
                    "ready": True,
                },
                "cluster2": {
                    "provider": "k3s",
                    "name": "cluster2",
                    "exists": False,
                    "ready": False,
                },
            }
        )

        with patch("localargo.cli.commands.cluster.ClusterManager", return_value=mock_manager):
            runner = CliRunner()
            result = runner.invoke(status_manifest, [str(manifest_file)])

        assert result.exit_code == 0
