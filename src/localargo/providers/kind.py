# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>
#
# SPDX-License-Identifier: MIT
"""KinD (Kubernetes in Docker) provider implementation."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from localargo.providers.base import (
    ClusterCreationError,
    ClusterOperationError,
    ClusterProvider,
    ProviderNotAvailableError,
)
from localargo.utils.cli import check_cli_availability, run_subprocess


class KindProvider(ClusterProvider):
    """KinD (Kubernetes in Docker) cluster provider."""

    @property
    def provider_name(self) -> str:
        return "kind"

    def _create_kind_config(self) -> str:
        """Create a kind cluster config with port mappings for ingress."""
        return """kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
- role: control-plane
  extraPortMappings:
  - containerPort: 80
    hostPort: 80
    protocol: TCP
  - containerPort: 443
    hostPort: 443
    protocol: TCP
"""

    def is_available(self) -> bool:
        """Check if KinD, kubectl, and helm are installed and available."""
        try:
            # Check kind
            kind_path = check_cli_availability("kind")
            if not kind_path:
                return False
            result = subprocess.run(
                [kind_path, "version"], capture_output=True, text=True, check=True
            )
            if "kind" not in result.stdout.lower():
                return False

            # Check kubectl
            kubectl_path = check_cli_availability("kubectl")
            if not kubectl_path:
                return False

            # Check helm
            helm_path = shutil.which("helm")
            return bool(helm_path)
        except (subprocess.CalledProcessError, FileNotFoundError, RuntimeError):
            return False

    def create_cluster(self, **kwargs: Any) -> bool:  # noqa: ARG002
        """Create a KinD cluster and install ArgoCD with nginx-ingress."""
        if not self.is_available():
            msg = (
                "KinD, kubectl, and helm are required. Install from: "
                "https://kind.sigs.k8s.io/, https://kubernetes.io/docs/tasks/tools/, "
                "and https://helm.sh/"
            )
            raise ProviderNotAvailableError(msg)

        try:
            # Create cluster with port mappings for direct access
            config_content = self._create_kind_config()
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".yaml", delete=False
            ) as config_file:
                config_file.write(config_content)
                config_file_path = config_file.name

            cmd = [
                "kind",
                "create",
                "cluster",
                "--name",
                self.name,
                "--config",
                config_file_path,
            ]
            subprocess.run(cmd, check=True)

            # Clean up temporary config file
            Path(config_file_path).unlink(missing_ok=True)

            # Wait for cluster to be ready
            self._wait_for_cluster_ready(f"kind-{self.name}")

            # Install nginx-ingress
            self._install_nginx_ingress()

            # Install ArgoCD
            self._install_argocd()

        except subprocess.CalledProcessError as e:
            msg = f"Failed to create KinD cluster: {e}"
            raise ClusterCreationError(msg) from e

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
            result = subprocess.run(
                [kind_path, "get", "clusters"], capture_output=True, text=True, check=True
            )
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
                    run_subprocess(["kubectl", "cluster-info", "--context", context_name])
                    status["ready"] = True
                except subprocess.CalledProcessError:
                    pass

        except subprocess.CalledProcessError as e:
            msg = f"Failed to get cluster status: {e}"
            raise ClusterOperationError(msg) from e

        return status

    def _wait_for_cluster_ready(
        self, context_name: str | subprocess.Popen, timeout: int = 60
    ) -> None:
        """Wait for the cluster to be ready."""
        if isinstance(context_name, str) or context_name is None:
            context_name = f"kind-{self.name}"
        super()._wait_for_cluster_ready(context_name, timeout)

    def _install_nginx_ingress(self) -> None:
        """Install nginx-ingress controller."""
        helm_path = shutil.which("helm")
        kubectl_path = shutil.which("kubectl")
        if helm_path is None:
            msg = "helm not found in PATH. Please ensure helm is installed and available."
            raise RuntimeError(msg)
        if kubectl_path is None:
            msg = (
                "kubectl not found in PATH. Please ensure kubectl is installed and available."
            )
            raise RuntimeError(msg)

        try:
            # Add ingress-nginx helm repo
            subprocess.run(
                [
                    helm_path,
                    "repo",
                    "add",
                    "ingress-nginx",
                    "https://kubernetes.github.io/ingress-nginx",
                ],
                check=False,  # Allow failure if repo already exists
            )
            subprocess.run([helm_path, "repo", "update"], check=True)

            # Install nginx-ingress using helm with kind-specific configuration
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
                    "--set",
                    "controller.hostNetwork=true",
                    "--set",
                    "controller.dnsPolicy=ClusterFirstWithHostNet",
                    "--set",
                    "controller.kind=DaemonSet",
                    "--set",
                    "controller.service.type=ClusterIP",
                    "--set",
                    "controller.extraArgs.enable-ssl-passthrough=true",
                    "--set",
                    "controller.extraArgs.enable-ssl-chain-completion=false",
                    "--set",
                    "controller.config.use-proxy-protocol=false",
                    "--set",
                    "controller.config.compute-full-forwarded-for=true",
                    "--set",
                    "controller.config.use-forwarded-headers=true",
                    "--set",
                    "controller.config.ssl-protocols=TLSv1.2 TLSv1.3",
                    "--set",
                    r"controller.nodeSelector.kubernetes\.io/os=linux",
                    "--set",
                    "controller.config.server-name-hash-bucket-size=256",
                ],
                check=True,
            )

            # Wait for controller to be ready
            subprocess.run(
                [
                    kubectl_path,
                    "-n",
                    "ingress-nginx",
                    "rollout",
                    "status",
                    "daemonset/ingress-nginx-controller",
                    "--timeout=180s",
                ],
                check=True,
            )

        except subprocess.CalledProcessError as e:
            msg = f"Failed to install nginx-ingress: {e}"
            raise ClusterCreationError(msg) from e

    def _install_argocd(self) -> None:
        """Install ArgoCD using helm with ingress configuration."""
        helm_path = shutil.which("helm")
        if helm_path is None:
            msg = "helm not found in PATH. Please ensure helm is installed and available."
            raise RuntimeError(msg)

        try:
            # Add ArgoCD helm repo
            subprocess.run(
                [helm_path, "repo", "add", "argo", "https://argoproj.github.io/argo-helm"],
                check=True,
            )
            subprocess.run([helm_path, "repo", "update"], check=True)

            # Install ArgoCD with ingress enabled using proper SSL passthrough configuration
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
                    "--set",
                    "server.ingress.enabled=true",
                    "--set",
                    "server.ingress.ingressClassName=nginx",
                    "--set",
                    "server.ingress.hostname=argocd.localtest.me",
                    "--set",
                    "server.ingress.annotations.nginx\\.ingress\\.kubernetes\\.io/"
                    "force-ssl-redirect=true",
                    "--set",
                    "server.ingress.annotations.nginx\\.ingress\\.kubernetes\\.io/"
                    "ssl-passthrough=true",
                    "--set",
                    "server.ingress.paths[0]=/",
                    "--set",
                    "server.ingress.pathType=Prefix",
                    "--set",
                    "server.ingress.tls=false",
                    "--set",
                    "server.extraArgs[0]=--insecure=false",
                    "--set",
                    "configs.params.server.insecure=false",
                    "--set",
                    "configs.params.server.grpc.web=true",
                    "--set",
                    "global.domain=argocd.localtest.me",
                    "--set",
                    "configs.cm.url=https://argocd.localtest.me",
                ],
                check=True,
            )

        except subprocess.CalledProcessError as e:
            msg = f"Failed to install ArgoCD: {e}"
            raise ClusterCreationError(msg) from e
