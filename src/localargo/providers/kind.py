# SPDX-FileCopyrightText: 2025-present U.N. Owen <void@some.where>
#
# SPDX-License-Identifier: MIT
from __future__ import annotations

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

"""KinD (Kubernetes in Docker) provider implementation."""


class KindProvider(ClusterProvider):
    """KinD (Kubernetes in Docker) cluster provider."""

    @property
    def provider_name(self) -> str:
        return "kind"

    def is_available(self) -> bool:
        """Check if KinD is installed and available."""
        try:
            kind_path = shutil.which("kind")
            if kind_path is None:
                msg = "kind not found in PATH. Please ensure kind is installed and available."
                raise RuntimeError(msg)
            result = subprocess.run([kind_path, "version"], capture_output=True, text=True, check=True)
            return "kind" in result.stdout.lower()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def create_cluster(self, **kwargs: Any) -> bool:  # noqa: ARG002
        """Create a KinD cluster with ArgoCD-optimized configuration."""
        if not self.is_available():
            msg = "KinD is not installed. Install from: https://kind.sigs.k8s.io/"
            raise ProviderNotAvailableError(msg)

        config_path = self._create_config_file()
        try:
            # Create the cluster
            cmd = ["kind", "create", "cluster", "--config", str(config_path), "--name", self.name]
            subprocess.run(cmd, check=True)  # Show output for debugging

            # Wait for cluster to be ready
            self._wait_for_cluster_ready()

        except subprocess.CalledProcessError as e:
            msg = f"Failed to create KinD cluster: {e}"
            raise ClusterCreationError(msg) from e
        else:
            return True
        finally:
            # Clean up config file
            config_path.unlink(missing_ok=True)

    def delete_cluster(self, name: str | None = None) -> bool:
        """Delete a KinD cluster."""
        cluster_name = name or self.name
        try:
            cmd = ["kind", "delete", "cluster", "--name", cluster_name]
            subprocess.run(cmd, check=True)  # Show output for debugging
        except subprocess.CalledProcessError as e:
            msg = f"Failed to delete KinD cluster '{cluster_name}': {e}"
            raise ClusterOperationError(msg) from e
        else:
            return True

    def get_cluster_status(self, name: str | None = None) -> dict[str, Any]:
        """Get KinD cluster status information."""
        cluster_name = name or self.name
        context_name = f"kind-{cluster_name}"

        try:
            # Check if cluster exists
            kind_path = shutil.which("kind")
            if kind_path is None:
                msg = "kind not found in PATH. Please ensure kind is installed and available."
                raise RuntimeError(msg)
            result = subprocess.run([kind_path, "get", "clusters"], capture_output=True, text=True, check=True)
            clusters = result.stdout.strip().split("\n")
            exists = cluster_name in clusters

            status = {
                "provider": "kind",
                "name": cluster_name,
                "exists": exists,
                "context": context_name,
                "ready": False,
            }

            if exists:
                # Check if context is accessible
                try:
                    kubectl_path = shutil.which("kubectl")
                    if kubectl_path is None:
                        msg = "kubectl not found in PATH. Please ensure kubectl is installed and available."
                        raise RuntimeError(msg)
                    subprocess.run(
                        [kubectl_path, "cluster-info", "--context", context_name],
                        capture_output=True,
                        check=True,
                    )
                    status["ready"] = True
                except subprocess.CalledProcessError:
                    pass

        except subprocess.CalledProcessError as e:
            msg = f"Failed to get cluster status: {e}"
            raise ClusterOperationError(msg) from e
        else:
            return status

    def _create_config_file(self) -> Path:
        """Create a KinD configuration file optimized for ArgoCD."""
        config_content = f"""
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: {self.name}
nodes:
- role: control-plane
  # Configure control plane with extra port mappings for ArgoCD
  extraPortMappings:
  - containerPort: 30080
    hostPort: 8080
    protocol: TCP
  - containerPort: 30443
    hostPort: 8443
    protocol: TCP
  # Additional ports for development services
  - containerPort: 30000
    hostPort: 30000
    protocol: TCP
  - containerPort: 30001
    hostPort: 30001
    protocol: TCP
  - containerPort: 30002
    hostPort: 30002
    protocol: TCP
  kubeadmConfigPatches:
  - |
    kind: InitConfiguration
    nodeRegistration:
      kubeletExtraArgs:
        node-labels: "ingress-ready=true"
  extraMounts:
  - hostPath: /tmp/kind-pv
    containerPath: /tmp/kind-pv
  # Configure containerd for better performance
  image: kindest/node:v1.27.3@sha256:3966ac761ae0136263ffdb6cfd4db23ef8a83cba8a463690e98317add2c9ba72f97
"""

        config_file = Path(tempfile.NamedTemporaryFile(suffix=".yaml", delete=False).name)
        config_file.write_text(config_content)
        return config_file

    def _wait_for_cluster_ready(self, timeout: int = 60) -> None:
        """Wait for the cluster to be ready."""
        context_name = f"kind-{self.name}"
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                kubectl_path = shutil.which("kubectl")
                if kubectl_path is None:
                    msg = "kubectl not found in PATH. Please ensure kubectl is installed and available."
                    raise RuntimeError(msg)
                subprocess.run(
                    [kubectl_path, "cluster-info", "--context", context_name],
                    capture_output=True,
                    check=True,
                )
            except subprocess.CalledProcessError:
                time.sleep(2)
            else:
                return

        msg = f"Cluster '{self.name}' failed to become ready within {timeout} seconds"
        raise ClusterCreationError(msg)
