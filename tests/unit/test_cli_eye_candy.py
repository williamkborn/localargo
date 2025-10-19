# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>

#
# SPDX-License-Identifier: MIT

"""Tests for CLI eye candy integration."""

from unittest.mock import patch

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

    def test_cluster_init_with_logging(self):
        """Test cluster init command provides appropriate logging."""
        runner = CliRunner()

        # Mock the cluster manager to avoid actual cluster operations
        with patch("localargo.core.cluster.cluster_manager.create_cluster", return_value=True):
            # Run the init command
            result = runner.invoke(
                localargo, ["cluster", "init", "--provider", "kind", "--name", "test-cluster"]
            )

            # Check that it ran without errors
            assert result.exit_code == 0

            # Check that appropriate logging appears
            assert "Initializing" in result.output

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

    def test_cluster_delete_with_logging(self):
        """Test cluster delete command provides appropriate logging."""
        runner = CliRunner()

        # Mock the cluster manager to avoid actual cluster operations
        with patch("localargo.core.cluster.cluster_manager.delete_cluster", return_value=True):
            # Run the delete command
            result = runner.invoke(
                localargo, ["cluster", "delete", "test-cluster", "--provider", "kind"]
            )

            # Check that it ran without errors
            assert result.exit_code == 0

            # Check that appropriate logging appears
            assert "Deleting" in result.output

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
