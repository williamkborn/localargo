"""Tests for K3s provider functionality."""

# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>
#
# SPDX-License-Identifier: MIT
# pylint: disable=protected-access
from subprocess import CalledProcessError
from unittest.mock import patch

import pytest

from localargo.providers.base import (
    ClusterCreationError,
    ClusterOperationError,
    ProviderNotAvailableError,
)
from localargo.providers.k3s import K3sProvider, build_k3s_server_command


class TestK3sProvider:
    """Test suite for K3sProvider."""

    def test_provider_name(self):
        """Test that provider_name returns 'k3s'."""
        provider = K3sProvider(name="test")
        assert provider.provider_name == "k3s"

    def test_init_creates_temp_kubeconfig(self):
        """Test that __init__ creates a temporary kubeconfig file."""
        with patch("tempfile.mkstemp") as mock_mkstemp:
            mock_mkstemp.return_value = (3, "/tmp/test-kubeconfig.yaml")

            provider = K3sProvider(name="test")

            assert provider._kubeconfig_path == "/tmp/test-kubeconfig.yaml"
            mock_mkstemp.assert_called_once_with(suffix=".yaml")

    def test_is_available_with_k3s_present(self):
        """Test is_available returns True when k3s is found and works."""
        provider = K3sProvider(name="test")
        assert provider.is_available() is True

    def test_is_available_with_k3s_not_found(self):
        """Test is_available returns False when k3s is not found."""
        # Mock shutil.which to return None for k3s
        with patch("shutil.which", return_value=None):
            provider = K3sProvider(name="test")
            assert provider.is_available() is False

    def test_is_available_with_k3s_command_failure(self, mock_subprocess_run):
        """Test is_available returns False when k3s command fails."""
        mock_subprocess_run.side_effect = CalledProcessError(1, "k3s")

        provider = K3sProvider(name="test")
        assert provider.is_available() is False

    def test_create_cluster_success(self, mock_subprocess_popen):
        """Test successful cluster creation."""
        provider = K3sProvider(name="demo")
        provider._kubeconfig_path = "/tmp/test-kubeconfig.yaml"

        # Mock the private methods
        with (
            patch.object(provider, "_wait_for_cluster_ready") as mock_wait,
            patch.object(provider, "_configure_kubectl_context") as mock_configure,
        ):
            result = provider.create_cluster()

            assert result is True
            mock_wait.assert_called_once()
            mock_configure.assert_called_once()

            # Verify the k3s server command was started
            mock_subprocess_popen.assert_called_once()
            call_args = mock_subprocess_popen.call_args
            expected_cmd = build_k3s_server_command("/tmp/test-kubeconfig.yaml")
            assert call_args[0][0] == expected_cmd

            # Verify environment variables
            env = call_args[1]["env"]
            assert env["K3S_KUBECONFIG_OUTPUT"] == "/tmp/test-kubeconfig.yaml"
            assert env["K3S_CLUSTER_NAME"] == "demo"

    def test_create_cluster_not_available_raises_error(self):
        """Test create_cluster raises ProviderNotAvailableError when k3s not available."""
        with patch("shutil.which", return_value=None):
            provider = K3sProvider(name="demo")

            with pytest.raises(ProviderNotAvailableError, match="k3s is not installed"):
                provider.create_cluster()

    def test_create_cluster_command_failure_raises_error(self):
        """Test create_cluster raises ClusterCreationError when Popen fails."""
        provider = K3sProvider(name="demo")

        with (
            patch.object(provider, "is_available", return_value=True),
            patch("subprocess.Popen", side_effect=Exception("Popen failed")),
            pytest.raises(ClusterCreationError, match="Unexpected error creating k3s cluster"),
        ):
            provider.create_cluster()

    def test_delete_cluster_raises_operation_error(self):
        """Test delete_cluster raises ClusterOperationError with guidance."""
        provider = K3sProvider(name="demo")

        with pytest.raises(ClusterOperationError) as exc_info:
            provider.delete_cluster()

        assert "k3s cluster 'demo' deletion must be done manually" in str(exc_info.value)
        assert "sudo systemctl stop k3s" in str(exc_info.value)

    def test_delete_cluster_with_custom_name_raises_operation_error(self):
        """Test delete_cluster with custom name raises ClusterOperationError."""
        provider = K3sProvider(name="demo")

        with pytest.raises(ClusterOperationError) as exc_info:
            provider.delete_cluster(name="custom-cluster")

        assert "k3s cluster 'custom-cluster' deletion must be done manually" in str(
            exc_info.value
        )

    def test_get_cluster_status_with_kubeconfig_exists_and_ready(self, mock_subprocess_run):
        """Test cluster status when kubeconfig exists and cluster is ready."""
        provider = K3sProvider(name="demo")
        provider._kubeconfig_path = "/tmp/test-kubeconfig.yaml"

        with patch("pathlib.Path.exists", return_value=True):
            status = provider.get_cluster_status()

            expected_status = {
                "provider": "k3s",
                "name": "demo",
                "exists": True,
                "context": "demo",
                "ready": True,
                "kubeconfig": "/tmp/test-kubeconfig.yaml",
            }
            assert status == expected_status

            # Verify kubectl command was called
            mock_subprocess_run.assert_called_once_with(
                [
                    "kubectl",
                    "--kubeconfig",
                    "/tmp/test-kubeconfig.yaml",
                    "cluster-info",
                ],
                capture_output=True,
                text=True,
                check=True,
            )

    def test_get_cluster_status_with_kubeconfig_not_exists(self, mock_subprocess_run):
        """Test cluster status when kubeconfig doesn't exist."""
        provider = K3sProvider(name="demo")
        provider._kubeconfig_path = "/tmp/test-kubeconfig.yaml"

        with patch("pathlib.Path.exists", return_value=False):
            status = provider.get_cluster_status()

            expected_status = {
                "provider": "k3s",
                "name": "demo",
                "exists": False,
                "context": "demo",
                "ready": False,
                "kubeconfig": "/tmp/test-kubeconfig.yaml",
            }
            assert status == expected_status

            # kubectl should not be called
            mock_subprocess_run.assert_not_called()

    def test_get_cluster_status_with_kubeconfig_exists_but_not_ready(self):
        """Test cluster status when kubeconfig exists but kubectl fails."""
        provider = K3sProvider(name="demo")
        provider._kubeconfig_path = "/tmp/test-kubeconfig.yaml"

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("subprocess.run", side_effect=CalledProcessError(1, "kubectl")),
        ):
            status = provider.get_cluster_status()

            expected_status = {
                "provider": "k3s",
                "name": "demo",
                "exists": True,
                "context": "demo",
                "ready": False,
                "kubeconfig": "/tmp/test-kubeconfig.yaml",
            }
            assert status == expected_status

    def test_get_cluster_status_with_custom_name(self):
        """Test cluster status retrieval with custom cluster name."""
        provider = K3sProvider(name="demo")
        provider._kubeconfig_path = "/tmp/test-kubeconfig.yaml"

        with patch("pathlib.Path.exists", return_value=False):
            status = provider.get_cluster_status(name="custom-cluster")

            expected_status = {
                "provider": "k3s",
                "name": "custom-cluster",
                "exists": False,
                "context": "custom-cluster",
                "ready": False,
                "kubeconfig": "/tmp/test-kubeconfig.yaml",
            }
            assert status == expected_status

    def test_get_cluster_status_explicit_patch(self):
        """Test cluster status retrieval using explicit subprocess patching."""
        provider = K3sProvider(name="demo")
        provider._kubeconfig_path = "/tmp/test-kubeconfig.yaml"

        with (
            patch("localargo.providers.k3s.subprocess.run") as mock_run,
            patch("pathlib.Path.exists", return_value=True),
        ):
            mock_run.return_value.returncode = 0
            status = provider.get_cluster_status()

            expected_status = {
                "provider": "k3s",
                "name": "demo",
                "exists": True,
                "context": "demo",
                "ready": True,
                "kubeconfig": "/tmp/test-kubeconfig.yaml",
            }
            assert status == expected_status

            # Verify kubectl command was called
            mock_run.assert_called_once_with(
                [
                    "kubectl",
                    "--kubeconfig",
                    "/tmp/test-kubeconfig.yaml",
                    "cluster-info",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
