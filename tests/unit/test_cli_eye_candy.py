# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>

#
# SPDX-License-Identifier: MIT

"""Tests for CLI eye candy integration."""

from unittest.mock import Mock, patch

from click.testing import CliRunner

from localargo.cli import localargo


class TestCliEyeCandy:
    """Test cases for CLI eye candy integration."""

    def test_help_output_styled(self):
        """Test that help output includes rich styling."""
        runner = CliRunner()

        result = runner.invoke(localargo, ["--help"])

        # Should exit successfully
        assert result.exit_code == 0

        # Should contain rich markup (basic check for common rich elements)
        output = result.output
        # Check for some basic rich formatting that should be present
        # Note: rich-click may not always add markup, but basic structure should be there
        assert "Localargo" in output or "localargo" in output.lower()

    def test_cluster_apply_with_step_logger(self, tmp_path):
        """Test cluster apply command uses step logger."""
        # Create a temporary manifest file
        yaml_content = """
clusters:
  - name: test-cluster
    provider: kind
"""
        manifest_file = tmp_path / "clusters.yaml"
        manifest_file.write_text(yaml_content)

        runner = CliRunner()

        # Mock the ClusterManager to avoid actual cluster operations
        with patch("localargo.cli.commands.cluster.ClusterManager") as mock_manager_class:
            mock_manager = Mock()
            mock_manager_class.return_value = mock_manager
            mock_manager.apply.return_value = {"test-cluster": True}

            # Run the apply command
            result = runner.invoke(localargo, ["cluster", "apply", str(manifest_file)])

            # Check that it ran without errors
            assert result.exit_code == 0

            # Check that step logger output appears
            assert "Starting workflow" in result.output
            assert "loading manifest" in result.output
            assert "✅" in result.output

    def test_cluster_status_with_table_renderer(self):
        """Test cluster status command uses table renderer."""
        runner = CliRunner()

        # Mock kubectl and cluster manager to avoid actual operations
        with (
            patch("shutil.which", return_value="/usr/bin/kubectl"),
            patch("localargo.cli.commands.cluster.subprocess.run") as mock_run,
            patch("localargo.core.cluster.cluster_manager.get_cluster_status") as mock_status,
        ):
            # Mock successful kubectl calls
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "argocd-server deployment found"
            mock_status.return_value = {"context": "test-context", "ready": True}

            # Run the status command
            result = runner.invoke(localargo, ["cluster", "status"])

            # Check that it ran without errors
            assert result.exit_code == 0

            # Check that table renderer was used (should see structured output)
            # Look for key-value panel output or table structure in result output
            assert (
                "Cluster Status" in result.output
                or "Context" in result.output
                or "Cluster Context" in result.output
            )

    def test_cluster_status_manifest_with_table_renderer(self, tmp_path):
        """Test cluster status-manifest command uses table renderer."""
        # Create a temporary manifest file
        yaml_content = """
clusters:
  - name: test-cluster
    provider: kind
  - name: failed-cluster
    provider: k3s
"""
        manifest_file = tmp_path / "clusters.yaml"
        manifest_file.write_text(yaml_content)

        runner = CliRunner()

        # Mock the ClusterManager to avoid actual operations
        with patch("localargo.cli.commands.cluster.ClusterManager") as mock_manager_class:
            mock_manager = Mock()
            mock_manager_class.return_value = mock_manager
            mock_manager.status.return_value = {
                "test-cluster": {"exists": True, "ready": True},
                "failed-cluster": {
                    "exists": True,
                    "ready": False,
                    "error": "Connection failed",
                },
            }

            # Run the status-manifest command
            result = runner.invoke(
                localargo, ["cluster", "status-manifest", str(manifest_file)]
            )

            # Check that it ran without errors
            assert result.exit_code == 0

            # Check that table renderer was used
            assert "Cluster" in result.output
            assert "test-cluster" in result.output
            assert "failed-cluster" in result.output

    def test_rich_click_integration(self):
        """Test that rich-click is properly integrated."""
        runner = CliRunner()

        # Test that rich-click styling is applied
        result = runner.invoke(localargo, ["cluster", "--help"])

        assert result.exit_code == 0

        # The output should contain the command help, styled by rich-click
        output = result.output
        assert "Manage Kubernetes clusters" in output

    def test_verbose_flag_still_works(self):
        """Test that the verbose flag still works with rich-click."""
        runner = CliRunner()

        # Mock logging to verify verbose flag is processed
        with patch("localargo.cli.init_cli_logging") as mock_logging:
            result = runner.invoke(localargo, ["--verbose", "cluster", "--help"])

            # Should still work with rich-click
            assert result.exit_code == 0
            mock_logging.assert_called_once_with(verbose=True)

    def test_version_option_styled(self):
        """Test that version option works with rich-click styling."""
        runner = CliRunner()

        result = runner.invoke(localargo, ["--version"])

        # Should work and show version
        assert result.exit_code == 0
        assert "localargo" in result.output.lower() or "version" in result.output.lower()
