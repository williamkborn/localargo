# SPDX-FileCopyrightText: 2025-present U.N. Owen <void@some.where>
#
# SPDX-License-Identifier: MIT
from __future__ import annotations

import os
import shutil
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
)

"""k3s provider implementation."""


class K3sProvider(ClusterProvider):
    """k3s (lightweight Kubernetes) cluster provider."""

    def __init__(self, name: str = "localargo"):
        super().__init__(name)
        # Use secure temp file for kubeconfig
        temp_fd, temp_path = tempfile.mkstemp(suffix=".yaml")
        self._kubeconfig_path = temp_path

    @property
    def provider_name(self) -> str:
        return "k3s"

    def is_available(self) -> bool:
        """Check if k3s is installed and available."""
        try:
            k3s_path = shutil.which("k3s")
            if k3s_path is None:
                return False
            result = subprocess.run([k3s_path, "--version"], capture_output=True, text=True, check=True)
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
            cmd = [
                "k3s",
                "server",
                "--cluster-init",  # Enable clustering
                "--disable",
                "traefik",  # Disable default ingress
                "--disable",
                "servicelb",  # Disable service load balancer
                "--write-kubeconfig",
                self._kubeconfig_path,
            ]

            process = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

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
        else:
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
                kubectl_path = shutil.which("kubectl")
                if kubectl_path is None:
                    msg = "kubectl not found in PATH. Please ensure kubectl is installed and available."
                    raise RuntimeError(msg)
                subprocess.run([kubectl_path, "--kubeconfig", str(kubeconfig), "cluster-info"], check=True)
                status["ready"] = True
            except subprocess.CalledProcessError:
                pass

        return status

    def _wait_for_cluster_ready(self, process: subprocess.Popen, timeout: int = 60) -> None:
        """Wait for the k3s cluster to be ready."""
        start_time = time.time()

        while time.time() - start_time < timeout:
            if process.poll() is not None:
                # Process has exited
                if process.returncode != 0:
                    msg = "k3s server process exited with error"
                    raise ClusterCreationError(msg)
                break

            # Check if kubeconfig is ready and cluster is accessible
            kubeconfig = Path(self._kubeconfig_path)
            if kubeconfig.exists():
                try:
                    kubectl_path = shutil.which("kubectl")
                    if kubectl_path is None:
                        msg = "kubectl not found in PATH. Please ensure kubectl is installed and available."
                    raise RuntimeError(msg)
                    subprocess.run(
                        [kubectl_path, "--kubeconfig", str(kubeconfig), "cluster-info"],
                        capture_output=True,
                        check=True,
                    )
                except subprocess.CalledProcessError:
                    pass
                else:
                    return

            time.sleep(2)

        if process.poll() is None:
            process.terminate()
        msg = f"k3s cluster '{self.name}' failed to become ready within {timeout} seconds"
        raise ClusterCreationError(msg)

    def _configure_kubectl_context(self) -> None:
        """Configure kubectl context for the k3s cluster."""
        try:
            # Rename the default context to our cluster name
            kubectl_path = shutil.which("kubectl")
            if kubectl_path is None:
                msg = "kubectl not found in PATH. Please ensure kubectl is installed and available."
                raise RuntimeError(msg)
            subprocess.run(
                [
                    kubectl_path,
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
