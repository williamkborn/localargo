# SPDX-FileCopyrightText: 2025-present U.N. Owen <void@some.where>
#
# SPDX-License-Identifier: MIT
from __future__ import annotations

import abc
from typing import Any

"""Base provider interface for Kubernetes cluster providers."""


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


class ProviderError(Exception):
    """Base exception for provider-related errors."""


class ProviderNotAvailableError(ProviderError):
    """Raised when a provider is not available."""


class ClusterCreationError(ProviderError):
    """Raised when cluster creation fails."""


class ClusterOperationError(ProviderError):
    """Raised when a cluster operation fails."""
