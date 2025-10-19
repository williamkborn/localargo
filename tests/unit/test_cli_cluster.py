"""Tests for CLI cluster commands."""

# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>
#
# SPDX-License-Identifier: MIT
import base64
import subprocess
from unittest.mock import patch

from click.testing import CliRunner

from localargo.cli.commands.cluster import delete, init, password, status


class TestCLICluster:
    """Test suite for cluster CLI commands."""

    def test_init_command_success(self):
        """Test init command with successful cluster creation."""
        with patch(
            "localargo.core.cluster.cluster_manager.create_cluster", return_value=True
        ) as mock_create:
            runner = CliRunner()
            result = runner.invoke(init, ["--provider", "kind", "--name", "test-cluster"])

        assert result.exit_code == 0
        # Verify that create_cluster was called with correct arguments
        mock_create.assert_called_once_with("kind", "test-cluster")

    def test_init_command_failure(self):
        """Test init command with cluster creation failure."""
        with patch(
            "localargo.core.cluster.cluster_manager.create_cluster", return_value=False
        ) as mock_create:
            runner = CliRunner()
            result = runner.invoke(init, ["--provider", "kind", "--name", "test-cluster"])

        assert result.exit_code == 0  # Command succeeds but logs failure
        mock_create.assert_called_once_with("kind", "test-cluster")

    def test_init_command_with_k3s_provider(self):
        """Test init command with k3s provider."""
        with patch(
            "localargo.core.cluster.cluster_manager.create_cluster", return_value=True
        ) as mock_create:
            runner = CliRunner()
            result = runner.invoke(init, ["--provider", "k3s", "--name", "test-cluster"])

        assert result.exit_code == 0
        mock_create.assert_called_once_with("k3s", "test-cluster")

    def test_delete_command_success(self):
        """Test delete command with successful cluster deletion."""
        with patch(
            "localargo.core.cluster.cluster_manager.delete_cluster", return_value=True
        ) as mock_delete:
            runner = CliRunner()
            result = runner.invoke(delete, ["test-cluster", "--provider", "kind"])

        assert result.exit_code == 0
        mock_delete.assert_called_once_with("kind", "test-cluster")

    def test_delete_command_failure(self):
        """Test delete command with cluster deletion failure."""
        with patch(
            "localargo.core.cluster.cluster_manager.delete_cluster", return_value=False
        ) as mock_delete:
            runner = CliRunner()
            result = runner.invoke(delete, ["test-cluster", "--provider", "kind"])

        assert result.exit_code == 1
        mock_delete.assert_called_once_with("kind", "test-cluster")

    def test_delete_command_with_k3s_provider(self):
        """Test delete command with k3s provider."""
        with patch(
            "localargo.core.cluster.cluster_manager.delete_cluster", return_value=True
        ) as mock_delete:
            runner = CliRunner()
            result = runner.invoke(delete, ["test-cluster", "--provider", "k3s"])

        assert result.exit_code == 0
        mock_delete.assert_called_once_with("k3s", "test-cluster")

    def test_delete_command_exception_handling(self):
        """Test delete command with exception during deletion."""
        with patch(
            "localargo.core.cluster.cluster_manager.delete_cluster",
            side_effect=Exception("Test error"),
        ) as mock_delete:
            runner = CliRunner()
            result = runner.invoke(delete, ["test-cluster", "--provider", "kind"])

        assert result.exit_code == 1
        mock_delete.assert_called_once_with("kind", "test-cluster")

    def test_status_command_with_context(self):
        """Test status command with specific context."""
        runner = CliRunner()
        result = runner.invoke(status, ["--context", "kind-test"])

        assert result.exit_code == 0
        assert "Cluster Context" in result.output
        assert "kind-test" in result.output

    def test_status_command_without_context(self):
        """Test status command without specific context."""
        runner = CliRunner()
        result = runner.invoke(status, [])

        assert result.exit_code == 0
        assert "Cluster Context" in result.output

    def test_status_command_with_argocd_installed(self):
        """Test status command when ArgoCD is installed."""
        runner = CliRunner()
        result = runner.invoke(status, [])

        assert result.exit_code == 0
        assert "ArgoCD Status" in result.output

    def test_password_command_success(self):
        """Test password command with successful password retrieval."""
        runner = CliRunner()

        # Mock the subprocess call to return a fake base64 encoded password
        fake_password = "fake-password"
        fake_b64_password = base64.b64encode(fake_password.encode()).decode()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = fake_b64_password
            mock_run.return_value.stderr = ""

            result = runner.invoke(password, ["test-cluster"])

        assert result.exit_code == 0
        # The command should run successfully without errors

    def test_password_command_failure(self):
        """Test password command when kubectl fails."""
        runner = CliRunner()

        # Mock subprocess.run to simulate a kubectl failure
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, "kubectl", "NotFound")

            result = runner.invoke(password, ["nonexistent-cluster"])

        # The command should exit with an error code
        assert result.exit_code != 0
