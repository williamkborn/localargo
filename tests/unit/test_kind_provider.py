"""Tests for Kind provider functionality."""

# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>
#
# SPDX-License-Identifier: MIT
from subprocess import CalledProcessError
from unittest.mock import MagicMock, patch

import pytest

from localargo.providers.base import (
    ClusterCreationError,
    ClusterOperationError,
    ProviderNotAvailableError,
)
from localargo.providers.kind import KindProvider


class TestKindProvider:
    """Test suite for KindProvider."""

    def test_provider_name(self):
        """Test that provider_name returns 'kind'."""
        provider = KindProvider(name="test")
        assert provider.provider_name == "kind"

    def test_is_available_with_kind_present(self):
        """Test is_available returns True when kind is found and works."""
        provider = KindProvider(name="test")
        assert provider.is_available() is True

    def test_is_available_with_kind_not_found(self):
        """Test is_available returns False when kind is not found."""
        # Mock shutil.which to return None for kind
        with patch("shutil.which", return_value=None):
            provider = KindProvider(name="test")
            assert provider.is_available() is False

    def test_is_available_with_kind_command_failure(self, mock_subprocess_run):
        """Test is_available returns False when kind command fails."""
        mock_subprocess_run.side_effect = CalledProcessError(1, "kind")

        provider = KindProvider(name="test")
        assert provider.is_available() is False

    def test_is_available_with_kubectl_not_found(self):
        """Test is_available returns False when kubectl is not found."""

        def mock_which(cmd):
            return {
                "kind": "/usr/local/bin/kind",
                "kubectl": None,
                "helm": "/usr/local/bin/helm",
            }.get(cmd)

        with (
            patch("shutil.which", side_effect=mock_which),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value.stdout = "kind v0.20.0"
            provider = KindProvider(name="test")
            assert provider.is_available() is False

    def test_is_available_with_helm_not_found(self):
        """Test is_available returns False when helm is not found."""

        def mock_which(cmd):
            return {
                "kind": "/usr/local/bin/kind",
                "kubectl": "/usr/local/bin/kubectl",
                "helm": None,
            }.get(cmd)

        with (
            patch("shutil.which", side_effect=mock_which),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value.stdout = "kind v0.20.0"
            provider = KindProvider(name="test")
            assert provider.is_available() is False

    def test_create_cluster_success(self, mock_subprocess_run):
        """Test successful cluster creation."""
        provider = KindProvider(name="demo")

        # Mock the installation methods
        with (
            patch.object(provider, "_wait_for_cluster_ready"),
            patch.object(provider, "_install_nginx_ingress"),
            patch.object(provider, "_install_argocd"),
        ):
            result = provider.create_cluster()

            assert result is True

            # Verify the cluster creation command (should be the second call, after is_available)
            actual_calls = mock_subprocess_run.call_args_list
            assert len(actual_calls) == 2  # is_available call + create call

            # The second call should be the cluster creation
            create_call = actual_calls[1]
            expected_kwargs = {"check": True}

            # The command should be: kind create cluster --name demo --config /tmp/tmpXXX.yaml
            assert create_call[0][0][0] == "kind"
            assert create_call[0][0][1] == "create"
            assert create_call[0][0][2] == "cluster"
            assert create_call[0][0][3] == "--name"
            assert create_call[0][0][4] == "demo"
            assert create_call[0][0][5] == "--config"
            assert (
                len(create_call[0][0]) == 7
            )  # Should have 7 elements total (including config file path)
            assert create_call[0][0][6].endswith(".yaml")  # Config file path
            assert create_call[1] == expected_kwargs

    def test_create_cluster_not_available_raises_error(self):
        """Test create_cluster raises ProviderNotAvailableError when dependencies not available."""
        with patch("shutil.which", return_value=None):
            provider = KindProvider(name="demo")

            with pytest.raises(
                ProviderNotAvailableError, match="KinD, kubectl, and helm are required"
            ):
                provider.create_cluster()

    def test_create_cluster_command_failure_raises_error(self):
        """Test create_cluster raises ClusterCreationError when command fails."""
        provider = KindProvider(name="demo")

        with (
            patch.object(provider, "is_available", return_value=True),
            patch("subprocess.run", side_effect=CalledProcessError(1, "kind")),
            pytest.raises(ClusterCreationError, match="Failed to create KinD cluster"),
        ):
            provider.create_cluster()

    def test_delete_cluster_success(self, mock_subprocess_run):
        """Test successful cluster deletion."""
        provider = KindProvider(name="demo")

        result = provider.delete_cluster()

        assert result is True

        # Verify the delete command
        mock_subprocess_run.assert_called_once_with(
            ["kind", "delete", "cluster", "--name", "demo"], check=True
        )

    def test_delete_cluster_with_custom_name(self, mock_subprocess_run):
        """Test cluster deletion with custom cluster name."""
        provider = KindProvider(name="demo")

        result = provider.delete_cluster(name="custom-cluster")

        assert result is True

        # Verify the delete command uses the custom name
        mock_subprocess_run.assert_called_once_with(
            ["kind", "delete", "cluster", "--name", "custom-cluster"], check=True
        )

    def test_delete_cluster_command_failure_raises_error(self, mock_subprocess_run):
        """Test delete_cluster raises ClusterOperationError when command fails."""
        mock_subprocess_run.side_effect = CalledProcessError(1, "kind")

        provider = KindProvider(name="demo")

        with pytest.raises(
            ClusterOperationError, match="Failed to delete KinD cluster 'demo'"
        ):
            provider.delete_cluster()

    def test_delete_cluster_invokes_correct_command_explicit_patch(self):
        """Test delete_cluster invokes correct command using explicit module patching."""
        with patch("localargo.providers.kind.subprocess.run") as mock_run:
            provider = KindProvider("demo")
            provider.delete_cluster()
            mock_run.assert_called_once_with(
                ["kind", "delete", "cluster", "--name", "demo"], check=True
            )

    def test_get_context_name(self):
        """Test get_context_name returns correct context name format."""
        provider = KindProvider(name="demo")
        assert provider.get_context_name("demo") == "kind-demo"

    def test_get_cluster_status_success(self, mock_subprocess_run):
        """Test successful cluster status retrieval."""
        # Mock kind get clusters command
        mock_run = MagicMock()
        mock_run.returncode = 0
        mock_run.stdout = "demo\nother-cluster\n"

        # Mock kubectl cluster-info command
        mock_run2 = MagicMock()
        mock_run2.returncode = 0

        mock_subprocess_run.side_effect = [mock_run, mock_run2]

        provider = KindProvider(name="demo")

        status = provider.get_cluster_status()

        expected_status = {
            "provider": "kind",
            "name": "demo",
            "exists": True,
            "context": "kind-demo",
            "ready": True,
        }
        assert status == expected_status

        # Verify commands were called correctly
        assert mock_subprocess_run.call_count == 2

    def test_get_cluster_status_cluster_not_exists(self):
        """Test cluster status when cluster doesn't exist."""
        provider = KindProvider(name="demo")

        with patch("subprocess.run") as mock_run:
            # Mock kind get clusters command - cluster not in list
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "other-cluster\n"
            mock_run.return_value = mock_result

            status = provider.get_cluster_status()

            expected_status = {
                "provider": "kind",
                "name": "demo",
                "exists": False,
                "context": "kind-demo",
                "ready": False,
            }
            assert status == expected_status

    def test_get_cluster_status_with_custom_name(self):
        """Test cluster status retrieval with custom cluster name."""
        provider = KindProvider(name="demo")

        with patch("subprocess.run") as mock_run:
            # Mock kind get clusters command
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "custom-cluster\nother-cluster\n"
            mock_run.return_value = mock_result

            status = provider.get_cluster_status(name="custom-cluster")

            expected_status = {
                "provider": "kind",
                "name": "custom-cluster",
                "exists": True,
                "context": "kind-custom-cluster",
                "ready": True,  # kubectl check succeeds with global mock
            }
            assert status == expected_status

    def test_get_cluster_status_command_failure_raises_error(self):
        """Test get_cluster_status raises ClusterOperationError when command fails."""
        provider = KindProvider(name="demo")

        with (
            patch("subprocess.run", side_effect=CalledProcessError(1, "kind")),
            pytest.raises(ClusterOperationError, match="Failed to get cluster status"),
        ):
            provider.get_cluster_status()
