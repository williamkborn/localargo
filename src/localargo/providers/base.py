# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Base classes and interfaces for cluster providers."""

from __future__ import annotations

import abc
import subprocess
import time
from typing import Any

from localargo.utils.cli import check_cli_availability, run_subprocess


def check_process_exited_with_error(
    process: subprocess.Popen, error_msg: str = "Process failed"
) -> None:
    """Check if a process has exited and raise error if it failed.

    Args:
        process (subprocess.Popen): The subprocess.Popen object to check
        error_msg (str): Error message to raise if process exited with non-zero code

    Raises:
        ClusterCreationError: If process has exited with non-zero return code
    """
    if process.poll() is not None and process.returncode != 0:
        raise ClusterCreationError(error_msg)


class ClusterProvider(abc.ABC):
    """Abstract base class for Kubernetes cluster providers."""

    def __init__(self, name: str = "localargo"):
        self.name = name

    @property
    @abc.abstractmethod
    def provider_name(self) -> str:
        """Name of the provider (e.g., 'kind', 'k3s')."""

    @abc.abstractmethod
    def is_available(self) -> bool:
        """Check if the provider is installed and available."""

    @abc.abstractmethod
    def create_cluster(self, **kwargs: Any) -> bool:
        """Create a new cluster with the provider."""

    @abc.abstractmethod
    def delete_cluster(self, name: str | None = None) -> bool:
        """Delete a cluster."""

    @abc.abstractmethod
    def get_cluster_status(self, name: str | None = None) -> dict[str, Any]:
        """Get cluster status information."""

    def get_context_name(self, cluster_name: str | None = None) -> str:
        """Get the kubectl context name for this cluster."""
        cluster_name = cluster_name or self.name
        return f"{self.provider_name}-{cluster_name}"

    def _ensure_kubectl_available(self) -> str:
        """Ensure kubectl is available and return its path.

        Returns:
            str: Path to kubectl executable

        Raises:
            FileNotFoundError: If kubectl is not found in PATH
        """
        kubectl_path = check_cli_availability("kubectl", "kubectl not found in PATH")
        if not kubectl_path:
            msg = "kubectl not found in PATH"
            raise FileNotFoundError(msg)
        return kubectl_path

    def _run_kubectl_command(
        self, cmd: list[str], **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        """Run a kubectl command with standardized error handling.

        Args:
            cmd (list[str]): kubectl command as list of strings
            **kwargs (Any): Additional arguments for subprocess.run

        Returns:
            subprocess.CompletedProcess[str]: CompletedProcess from subprocess.run
        """
        kubectl_path = self._ensure_kubectl_available()
        return run_subprocess([kubectl_path, *cmd], **kwargs)

    def _wait_for_cluster_ready(
        self, context_name: str | subprocess.Popen, timeout: int = 300
    ) -> None:
        """Wait for cluster to become ready by checking cluster-info.

        Args:
            context_name (str | subprocess.Popen): kubectl context name for the cluster
                or process for k3s
            timeout (int): Maximum time to wait in seconds

        Raises:
            ClusterCreationError: If cluster doesn't become ready within timeout
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                if isinstance(context_name, str):
                    # Standard kubectl-based wait
                    self._run_kubectl_command(
                        ["cluster-info", "--context", context_name],
                        capture_output=True,
                        check=True,
                    )
                    return

                # k3s-specific process-based wait
                check_process_exited_with_error(
                    context_name, error_msg="k3s server process exited with error"
                )
            except subprocess.CalledProcessError:
                if isinstance(context_name, str):
                    time.sleep(2)
                # For k3s, continue polling the process

        if isinstance(context_name, str):
            msg = f"Cluster '{self.name}' failed to become ready within {timeout} seconds"
            raise ClusterCreationError(msg)


class ProviderError(Exception):
    """Base exception for provider-related errors."""


class ProviderNotAvailableError(ProviderError):
    """Raised when a provider is not available."""


class ClusterCreationError(ProviderError):
    """Raised when cluster creation fails."""


class ClusterOperationError(ProviderError):
    """Raised when a cluster operation fails."""
