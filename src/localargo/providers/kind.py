# SPDX-FileCopyrightText: 2025-present U.N. Owen <void@some.where>
#
# SPDX-License-Identifier: MIT
from __future__ import annotations

import shutil
import subprocess
import time
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
        """Check if KinD, kubectl, and helm are installed and available."""
        try:
            # Check kind
            kind_path = shutil.which("kind")
            if kind_path is None:
                return False
            result = subprocess.run([kind_path, "version"], capture_output=True, text=True, check=True)
            if "kind" not in result.stdout.lower():
                return False

            # Check kubectl
            kubectl_path = shutil.which("kubectl")
            if kubectl_path is None:
                return False

            # Check helm
            helm_path = shutil.which("helm")
            return bool(helm_path)
        except (subprocess.CalledProcessError, FileNotFoundError, RuntimeError):
            return False

    def create_cluster(self, **kwargs: Any) -> bool:  # noqa: ARG002
        """Create a KinD cluster and install ArgoCD with nginx-ingress."""
        if not self.is_available():
            msg = "KinD, kubectl, and helm are required. Install from: https://kind.sigs.k8s.io/, https://kubernetes.io/docs/tasks/tools/, and https://helm.sh/"
            raise ProviderNotAvailableError(msg)

        try:
            # Create a simple cluster
            cmd = ["kind", "create", "cluster", "--name", self.name]
            subprocess.run(cmd, check=True)

            # Wait for cluster to be ready
            self._wait_for_cluster_ready()

            # Install nginx-ingress
            self._install_nginx_ingress()

            # Install ArgoCD
            self._install_argocd()

        except subprocess.CalledProcessError as e:
            msg = f"Failed to create KinD cluster: {e}"
            raise ClusterCreationError(msg) from e
        else:
            return True

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
                return
            except subprocess.CalledProcessError:
                time.sleep(2)
            else:
                return

        msg = f"Cluster '{self.name}' failed to become ready within {timeout} seconds"
        raise ClusterCreationError(msg)

    def _install_nginx_ingress(self) -> None:
        """Install nginx-ingress controller."""
        helm_path = shutil.which("helm")
        if helm_path is None:
            msg = "helm not found in PATH. Please ensure helm is installed and available."
            raise RuntimeError(msg)

        try:
            # Install nginx-ingress using helm
            subprocess.run(
                [
                    helm_path,
                    "upgrade",
                    "--install",
                    "ingress-nginx",
                    "ingress-nginx/ingress-nginx",
                    "--namespace",
                    "ingress-nginx",
                    "--create-namespace",
                    "--wait",
                    "--wait-for-jobs",
                    "--timeout=180s",
                ],
                check=True,
            )

        except subprocess.CalledProcessError as e:
            msg = f"Failed to install nginx-ingress: {e}"
            raise ClusterCreationError(msg) from e

    def _install_argocd(self) -> None:
        """Install ArgoCD using helm."""
        helm_path = shutil.which("helm")
        if helm_path is None:
            msg = "helm not found in PATH. Please ensure helm is installed and available."
            raise RuntimeError(msg)

        try:
            # Add ArgoCD helm repo
            subprocess.run([helm_path, "repo", "add", "argo", "https://argoproj.github.io/argo-helm"], check=True)
            subprocess.run([helm_path, "repo", "update"], check=True)

            # Install ArgoCD
            subprocess.run(
                [
                    helm_path,
                    "upgrade",
                    "--install",
                    "argocd",
                    "argo/argo-cd",
                    "--namespace",
                    "argocd",
                    "--create-namespace",
                    "--wait",
                    "--wait-for-jobs",
                    "--timeout=180s",
                ],
                check=True,
            )

        except subprocess.CalledProcessError as e:
            msg = f"Failed to install ArgoCD: {e}"
            raise ClusterCreationError(msg) from e
