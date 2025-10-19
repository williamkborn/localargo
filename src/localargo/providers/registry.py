# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Provider registry for cluster management."""

from __future__ import annotations

from typing import TYPE_CHECKING

from localargo.providers.k3s import K3sProvider
from localargo.providers.kind import KindProvider

if TYPE_CHECKING:
    from localargo.providers.base import ClusterProvider


# Registry of available providers
PROVIDERS: dict[str, type[ClusterProvider]] = {
    "kind": KindProvider,
    "k3s": K3sProvider,
}


def get_provider(name: str) -> type[ClusterProvider]:
    """
    Get a provider class by name.

    Args:
        name (str): Name of the provider (e.g., 'kind', 'k3s')

    Returns:
        type[ClusterProvider]: Provider class

    Raises:
        ValueError: If provider name is unknown
    """
    try:
        return PROVIDERS[name]
    except KeyError as err:
        available = ", ".join(PROVIDERS.keys())
        msg = f"Unknown provider: {name}. Available providers: {available}"
        raise ValueError(msg) from err


def list_available_providers() -> list[str]:
    """
    List names of all available providers.

    Returns:
        list[str]: List of provider names
    """
    return list(PROVIDERS.keys())
