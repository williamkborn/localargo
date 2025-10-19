# SPDX-FileCopyrightText: 2025-present U.N. Owen <void@some.where>
#
# SPDX-License-Identifier: MIT
from __future__ import annotations

import shutil
import subprocess
from typing import TYPE_CHECKING, Any, ClassVar

from localargo.logging import logger
from localargo.providers.k3s import K3sProvider
from localargo.providers.kind import KindProvider

if TYPE_CHECKING:
    from localargo.providers.base import ClusterProvider

"""Core cluster management functionality."""


class ClusterManager:
    """High-level cluster management operations."""

    PROVIDERS: ClassVar[dict[str, type[ClusterProvider]]] = {
        "kind": KindProvider,
        "k3s": K3sProvider,
    }

    def __init__(self) -> None:
        self.providers = {name: cls() for name, cls in self.PROVIDERS.items()}

    def get_available_providers(self) -> list[str]:
        """Get list of available (installed) providers."""
        return [name for name, provider in self.providers.items() if provider.is_available()]

    def get_provider(self, name: str) -> ClusterProvider:
        """Get a provider instance by name."""
        if name not in self.providers:
            msg = f"Unknown provider: {name}"
            raise ValueError(msg)
        return self.providers[name]

    def create_cluster(self, provider_name: str, cluster_name: str = "localargo", **kwargs: Any) -> bool:
        """Create a cluster using the specified provider."""
        provider = self.get_provider(provider_name)
        provider.name = cluster_name
        return provider.create_cluster(**kwargs)

    def delete_cluster(self, provider_name: str, cluster_name: str | None = None) -> bool:
        """Delete a cluster using the specified provider."""
        provider = self.get_provider(provider_name)
        return provider.delete_cluster(cluster_name)

    def get_cluster_status(self, provider_name: str | None = None, cluster_name: str | None = None) -> dict[str, Any]:
        """Get cluster status. If provider not specified, check current context."""
        if provider_name:
            provider = self.get_provider(provider_name)
            return provider.get_cluster_status(cluster_name)

        # Try to detect current cluster provider from context
        try:
            kubectl_path = shutil.which("kubectl")
            if kubectl_path is None:
                msg = "kubectl not found in PATH. Please ensure kubectl is installed and available."
                raise RuntimeError(msg)
            result = subprocess.run(
                [kubectl_path, "config", "current-context"], capture_output=True, text=True, check=True
            )
            current_context = result.stdout.strip()

            # Try to identify provider from context name
            for provider in self.providers.values():
                if current_context.startswith(f"{provider.provider_name}-"):
                    status = provider.get_cluster_status()
                    status["detected_from_context"] = True
                    return status
        except subprocess.CalledProcessError:
            return {
                "provider": "none",
                "name": "none",
                "context": "none",
                "exists": False,
                "ready": False,
                "error": "kubectl not available or no current context",
            }
        else:
            # Fallback: generic status - only if try succeeds but no provider found
            return {
                "provider": "unknown",
                "name": "unknown",
                "context": current_context,
                "exists": True,
                "ready": True,
                "detected_from_context": True,
            }

    def list_clusters(self) -> list[dict[str, Any]]:
        """List all clusters across all providers."""
        clusters = []

        for provider in self.providers.values():
            if provider.is_available():
                try:
                    status = provider.get_cluster_status()
                    clusters.append(status)
                except (subprocess.SubprocessError, OSError) as e:
                    # Skip clusters we can't get status for
                    logger.warning(f"Failed to get status for cluster from {provider.provider_name}: {e}")
                    continue

        return clusters

    def switch_context(self, context_name: str) -> bool:
        """Switch to a different kubectl context."""
        try:
            kubectl_path = shutil.which("kubectl")
            if kubectl_path is None:
                msg = "kubectl not found in PATH. Please ensure kubectl is installed and available."
                raise RuntimeError(msg)
            subprocess.run(
                [kubectl_path, "config", "use-context", context_name], check=True
            )  # Show output for debugging
        except subprocess.CalledProcessError:
            return False
        else:
            return True

    def get_contexts(self) -> list[str]:
        """Get list of available kubectl contexts."""
        try:
            kubectl_path = shutil.which("kubectl")
            if kubectl_path is None:
                msg = "kubectl not found in PATH. Please ensure kubectl is installed and available."
                raise RuntimeError(msg)
            result = subprocess.run(
                [kubectl_path, "config", "get-contexts", "-o", "name"],
                capture_output=True,
                text=True,
                check=True,
            )
            contexts = result.stdout.strip().split("\n")
            return [ctx for ctx in contexts if ctx]  # Filter out empty strings
        except subprocess.CalledProcessError:
            return []


# Global cluster manager instance
cluster_manager = ClusterManager()
