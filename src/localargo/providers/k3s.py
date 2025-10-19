# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>
#
# SPDX-License-Identifier: MIT
"""k3s provider implementation."""

from __future__ import annotations

import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from localargo.providers.base import (
    ClusterCreationError,
    ClusterOperationError,
    ClusterProvider,
    ProviderNotAvailableError,
    check_process_exited_with_error,
)
from localargo.utils.cli import check_cli_availability, run_subprocess


def build_k3s_server_command(kubeconfig_path: str) -> list[str]:
    """Build the k3s server command with standard options.

    Args:
        kubeconfig_path (str): Path where kubeconfig should be written

    Returns:
        list[str]: k3s server command as list of strings
    """
    return [
        "k3s",
        "server",
        "--cluster-init",  # Enable clustering
        "--disable",
        "traefik",  # Disable default ingress
        "--disable",
        "servicelb",  # Disable service load balancer
        "--write-kubeconfig",
        kubeconfig_path,
    ]


class K3sProvider(ClusterProvider):
    """k3s (lightweight Kubernetes) cluster provider."""

    def __init__(self, name: str = "localargo"):
        super().__init__(name)
        # Use secure temp file for kubeconfig
        _, temp_path = tempfile.mkstemp(suffix=".yaml")
        self._kubeconfig_path = temp_path

    @property
    def provider_name(self) -> str:
        return "k3s"

    def is_available(self) -> bool:
        """Check if k3s is installed and available."""
        try:
            k3s_path = check_cli_availability("k3s")
            if not k3s_path:
                return False
            result = subprocess.run(
                [k3s_path, "--version"], capture_output=True, text=True, check=True
            )
            return "k3s" in result.stdout.lower()
        except (subprocess.CalledProcessError, FileNotFoundError, RuntimeError):
            return False

    def create_cluster(self, **kwargs: Any) -> bool:  # noqa: ARG002
        """Create a k3s cluster with ArgoCD-friendly configuration."""
        if not self.is_available():
            msg = "k3s is not installed. Install with: curl -sfL https://get.k3s.io | sh -"
            raise ProviderNotAvailableError(msg)

        try:
            # Set up environment for k3s
            env = os.environ.copy()
            env["K3S_KUBECONFIG_OUTPUT"] = self._kubeconfig_path
            env["K3S_CLUSTER_NAME"] = self.name

            # Start k3s server in background
            cmd = build_k3s_server_command(self._kubeconfig_path)

            # Start k3s server in background - process must persist beyond this method
            process = subprocess.Popen(  # pylint: disable=consider-using-with
                cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )

            # Wait for cluster to be ready
            self._wait_for_cluster_ready(process)

            # Set up kubectl context
            self._configure_kubectl_context()

        except subprocess.CalledProcessError as e:
            msg = f"Failed to create k3s cluster: {e}"
            raise ClusterCreationError(msg) from e
        except Exception as e:
            msg = f"Unexpected error creating k3s cluster: {e}"
            raise ClusterCreationError(msg) from e

        return True

    def delete_cluster(self, name: str | None = None) -> bool:
        """Delete a k3s cluster."""
        # k3s clusters are typically managed as system services
        # For now, we'll provide guidance rather than automated deletion
        cluster_name = name or self.name
        msg = (
            f"k3s cluster '{cluster_name}' deletion must be done manually. "
            "Typically: sudo systemctl stop k3s && sudo k3s-uninstall.sh"
        )
        raise ClusterOperationError(msg)

    def get_cluster_status(self, name: str | None = None) -> dict[str, Any]:
        """Get k3s cluster status information."""
        cluster_name = name or self.name

        status = {
            "provider": "k3s",
            "name": cluster_name,
            "exists": False,
            "context": cluster_name,
            "ready": False,
            "kubeconfig": self._kubeconfig_path,
        }

        # Check if kubeconfig exists and is valid
        kubeconfig = Path(self._kubeconfig_path)
        if kubeconfig.exists():
            status["exists"] = True

            # Check if cluster is accessible
            try:
                run_subprocess(["kubectl", "--kubeconfig", str(kubeconfig), "cluster-info"])
                status["ready"] = True
            except subprocess.CalledProcessError:
                pass

        return status

    def _wait_for_cluster_ready(
        self, context_name: str | subprocess.Popen, timeout: int = 60
    ) -> None:
        """Wait for the k3s cluster to be ready."""
        # k3s implementation expects a process, not a context name
        if isinstance(context_name, str):
            msg = "k3s provider expects a process object, not a context name"
            raise TypeError(msg)

        start_time = time.time()

        while time.time() - start_time < timeout:
            check_process_exited_with_error(
                context_name, error_msg="k3s server process exited with error"
            )
            if context_name.poll() is not None:
                # Process has exited successfully
                break

            # Check if kubeconfig is ready and cluster is accessible
            if self._is_kubeconfig_ready():
                return

            time.sleep(2)

        if context_name.poll() is None:
            context_name.terminate()
        msg = f"k3s cluster '{self.name}' failed to become ready within {timeout} seconds"
        raise ClusterCreationError(msg)

    def _is_kubeconfig_ready(self) -> bool:
        """Return True if kubeconfig exists and cluster is accessible."""
        kubeconfig = Path(self._kubeconfig_path)
        if not kubeconfig.exists():
            return False
        try:
            run_subprocess(["kubectl", "--kubeconfig", str(kubeconfig), "cluster-info"])
        except subprocess.CalledProcessError:
            return False
        return True

    def _configure_kubectl_context(self) -> None:
        """Configure kubectl context for the k3s cluster."""
        try:
            # Rename the default context to our cluster name
            self._run_kubectl_command(
                [
                    "config",
                    "--kubeconfig",
                    self._kubeconfig_path,
                    "rename-context",
                    "default",
                    self.name,
                ],
                check=True,
                capture_output=True,
            )

        except subprocess.CalledProcessError as e:
            msg = f"Failed to configure kubectl context: {e}"
            raise ClusterOperationError(msg) from e
