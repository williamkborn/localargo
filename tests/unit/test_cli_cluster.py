# SPDX-FileCopyrightText: 2025-present U.N. Owen <void@some.where>
#
# SPDX-License-Identifier: MIT
from unittest.mock import Mock, patch

from click.testing import CliRunner

from localargo.cli.commands.cluster import apply, delete, status_manifest
from localargo.manager import ClusterManager, ClusterManagerError


class TestCLICluster:
    """Test suite for cluster CLI commands."""

    def test_apply_command_success(self, tmp_path):
        """Test apply command with successful cluster creation."""
        yaml_content = """
clusters:
  - name: test-cluster
    provider: kind
"""
        manifest_file = tmp_path / "clusters.yaml"
        manifest_file.write_text(yaml_content)

        # Mock ClusterManager
        mock_manager = Mock(spec=ClusterManager)
        mock_manager.apply.return_value = {"test-cluster": True}

        with patch("localargo.cli.commands.cluster.ClusterManager", return_value=mock_manager):
            runner = CliRunner()
            result = runner.invoke(apply, [str(manifest_file)])

        assert result.exit_code == 0
        # Check that the command ran without error (output format may vary)
        assert result.output == ""  # Click commands don't always output to stdout in tests

    def test_apply_command_partial_success(self, tmp_path):
        """Test apply command with partial success."""
        yaml_content = """
clusters:
  - name: cluster1
    provider: kind
  - name: cluster2
    provider: k3s
"""
        manifest_file = tmp_path / "clusters.yaml"
        manifest_file.write_text(yaml_content)

        # Mock ClusterManager
        mock_manager = Mock(spec=ClusterManager)
        mock_manager.apply.return_value = {"cluster1": True, "cluster2": False}

        with patch("localargo.cli.commands.cluster.ClusterManager", return_value=mock_manager):
            runner = CliRunner()
            result = runner.invoke(apply, [str(manifest_file)])

        assert result.exit_code == 0

    def test_apply_command_manifest_error(self, tmp_path):
        """Test apply command with manifest error."""
        manifest_file = tmp_path / "invalid.yaml"
        manifest_file.write_text("invalid: yaml: content")

        # Mock ClusterManager to raise error on init
        with patch("localargo.cli.commands.cluster.ClusterManager") as mock_class:
            mock_class.side_effect = ClusterManagerError("Invalid manifest")

            runner = CliRunner()
            result = runner.invoke(apply, [str(manifest_file)])

        assert result.exit_code == 1

    def test_apply_command_unexpected_error(self, tmp_path):
        """Test apply command with unexpected error."""
        yaml_content = """
clusters:
  - name: test-cluster
    provider: kind
"""
        manifest_file = tmp_path / "clusters.yaml"
        manifest_file.write_text(yaml_content)

        # Mock ClusterManager to raise unexpected error
        with patch("localargo.cli.commands.cluster.ClusterManager") as mock_class:
            mock_class.side_effect = Exception("Unexpected error")

            runner = CliRunner()
            result = runner.invoke(apply, [str(manifest_file)])

        assert result.exit_code == 1

    def test_delete_command_success(self, tmp_path):
        """Test delete command with successful cluster deletion."""
        yaml_content = """
clusters:
  - name: test-cluster
    provider: kind
"""
        manifest_file = tmp_path / "clusters.yaml"
        manifest_file.write_text(yaml_content)

        # Mock ClusterManager
        mock_manager = Mock(spec=ClusterManager)
        mock_manager.delete.return_value = {"test-cluster": True}

        with patch("localargo.cli.commands.cluster.ClusterManager", return_value=mock_manager):
            runner = CliRunner()
            result = runner.invoke(delete, [str(manifest_file)])

        assert result.exit_code == 0

    def test_delete_command_manifest_error(self, tmp_path):
        """Test delete command with manifest error."""
        manifest_file = tmp_path / "invalid.yaml"
        manifest_file.write_text("invalid: yaml: content")

        # Mock ClusterManager to raise error on init
        with patch("localargo.cli.commands.cluster.ClusterManager") as mock_class:
            mock_class.side_effect = ClusterManagerError("Invalid manifest")

            runner = CliRunner()
            result = runner.invoke(delete, [str(manifest_file)])

        assert result.exit_code == 1

    def test_status_command_ready_cluster(self, tmp_path):
        """Test status command with ready cluster."""
        yaml_content = """
clusters:
  - name: test-cluster
    provider: kind
"""
        manifest_file = tmp_path / "clusters.yaml"
        manifest_file.write_text(yaml_content)

        # Mock ClusterManager
        mock_manager = Mock(spec=ClusterManager)
        mock_manager.status.return_value = {
            "test-cluster": {
                "provider": "kind",
                "name": "test-cluster",
                "exists": True,
                "ready": True,
            }
        }

        with patch("localargo.cli.commands.cluster.ClusterManager", return_value=mock_manager):
            runner = CliRunner()
            result = runner.invoke(status_manifest, [str(manifest_file)])

        assert result.exit_code == 0

    def test_status_command_not_ready_cluster(self, tmp_path):
        """Test status command with not ready cluster."""
        yaml_content = """
clusters:
  - name: test-cluster
    provider: kind
"""
        manifest_file = tmp_path / "clusters.yaml"
        manifest_file.write_text(yaml_content)

        # Mock ClusterManager
        mock_manager = Mock(spec=ClusterManager)
        mock_manager.status.return_value = {
            "test-cluster": {
                "provider": "kind",
                "name": "test-cluster",
                "exists": True,
                "ready": False,
            }
        }

        with patch("localargo.cli.commands.cluster.ClusterManager", return_value=mock_manager):
            runner = CliRunner()
            result = runner.invoke(status_manifest, [str(manifest_file)])

        assert result.exit_code == 0

    def test_status_command_missing_cluster(self, tmp_path):
        """Test status command with missing cluster."""
        yaml_content = """
clusters:
  - name: test-cluster
    provider: kind
"""
        manifest_file = tmp_path / "clusters.yaml"
        manifest_file.write_text(yaml_content)

        # Mock ClusterManager
        mock_manager = Mock(spec=ClusterManager)
        mock_manager.status.return_value = {
            "test-cluster": {
                "provider": "kind",
                "name": "test-cluster",
                "exists": False,
                "ready": False,
            }
        }

        with patch("localargo.cli.commands.cluster.ClusterManager", return_value=mock_manager):
            runner = CliRunner()
            result = runner.invoke(status_manifest, [str(manifest_file)])

        assert result.exit_code == 0

    def test_status_command_with_error(self, tmp_path):
        """Test status command with cluster error."""
        yaml_content = """
clusters:
  - name: test-cluster
    provider: kind
"""
        manifest_file = tmp_path / "clusters.yaml"
        manifest_file.write_text(yaml_content)

        # Mock ClusterManager
        mock_manager = Mock(spec=ClusterManager)
        mock_manager.status.return_value = {
            "test-cluster": {
                "error": "Connection failed",
                "exists": False,
                "ready": False,
            }
        }

        with patch("localargo.cli.commands.cluster.ClusterManager", return_value=mock_manager):
            runner = CliRunner()
            result = runner.invoke(status_manifest, [str(manifest_file)])

        assert result.exit_code == 0

    def test_status_command_multiple_clusters(self, tmp_path):
        """Test status command with multiple clusters."""
        yaml_content = """
clusters:
  - name: cluster1
    provider: kind
  - name: cluster2
    provider: k3s
"""
        manifest_file = tmp_path / "clusters.yaml"
        manifest_file.write_text(yaml_content)

        # Mock ClusterManager
        mock_manager = Mock(spec=ClusterManager)
        mock_manager.status.return_value = {
            "cluster1": {
                "provider": "kind",
                "name": "cluster1",
                "exists": True,
                "ready": True,
            },
            "cluster2": {
                "provider": "k3s",
                "name": "cluster2",
                "exists": True,
                "ready": False,
            },
        }

        with patch("localargo.cli.commands.cluster.ClusterManager", return_value=mock_manager):
            runner = CliRunner()
            result = runner.invoke(status_manifest, [str(manifest_file)])

        assert result.exit_code == 0

    def test_status_command_manifest_error(self, tmp_path):
        """Test status command with manifest error."""
        manifest_file = tmp_path / "invalid.yaml"
        manifest_file.write_text("invalid: yaml: content")

        # Mock ClusterManager to raise error on init
        with patch("localargo.cli.commands.cluster.ClusterManager") as mock_class:
            mock_class.side_effect = ClusterManagerError("Invalid manifest")

            runner = CliRunner()
            result = runner.invoke(status_manifest, [str(manifest_file)])

        assert result.exit_code == 1

    def test_apply_command_default_manifest(self):
        """Test apply command with default manifest path."""
        # Mock ClusterManager
        mock_manager = Mock(spec=ClusterManager)
        mock_manager.apply.return_value = {}

        with patch("localargo.cli.commands.cluster.ClusterManager", return_value=mock_manager):
            runner = CliRunner()
            result = runner.invoke(apply)

        assert result.exit_code == 0
        # Should use default "clusters.yaml"
        assert mock_manager.apply.called

    def test_delete_command_default_manifest(self):
        """Test delete command with default manifest path."""
        # Mock ClusterManager
        mock_manager = Mock(spec=ClusterManager)
        mock_manager.delete.return_value = {}

        with patch("localargo.cli.commands.cluster.ClusterManager", return_value=mock_manager):
            runner = CliRunner()
            result = runner.invoke(delete)

        assert result.exit_code == 0
        # Should use default "clusters.yaml"
        assert mock_manager.delete.called

    def test_status_command_default_manifest(self):
        """Test status command with default manifest path."""
        # Mock ClusterManager
        mock_manager = Mock(spec=ClusterManager)
        mock_manager.status.return_value = {}

        with patch("localargo.cli.commands.cluster.ClusterManager", return_value=mock_manager):
            runner = CliRunner()
            result = runner.invoke(status_manifest)

        assert result.exit_code == 0
        # Should use default "clusters.yaml"
        assert mock_manager.status.called
