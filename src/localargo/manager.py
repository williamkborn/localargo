# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Declarative cluster lifecycle management."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from localargo.config.manifest import load_manifest
from localargo.logging import logger
from localargo.providers.base import ProviderError
from localargo.providers.registry import get_provider

if TYPE_CHECKING:
    from localargo.providers.base import ClusterProvider


class ClusterManagerError(Exception):
    """Base exception for cluster manager errors."""


class ClusterManager:
    """
    Declarative cluster lifecycle manager.

    Provides unified orchestration for creating, deleting, and managing
    clusters defined in YAML manifests using dynamic provider selection.

    Args:
        manifest_path (str | Path): Path to cluster manifest file

    Raises:
        ClusterManagerError: If manifest cannot be loaded
    """

    def __init__(self, manifest_path: str | Path):
        try:
            self.manifest = load_manifest(manifest_path)
        except Exception as e:
            msg = f"Failed to load manifest: {e}"
            raise ClusterManagerError(msg) from e

        # Create provider instances for each cluster
        self.providers: dict[str, ClusterProvider] = {}
        for cluster_config in self.manifest.clusters:
            provider_class = get_provider(cluster_config.provider)
            provider_instance = provider_class(name=cluster_config.name)
            self.providers[cluster_config.name] = provider_instance

    def apply(self) -> dict[str, bool]:
        """
        Create all clusters defined in the manifest.

        Returns:
            dict[str, bool]: Dictionary mapping cluster names to success status
        """
        logger.info("Applying cluster manifest...")
        results = {}

        for cluster_config in self.manifest.clusters:
            cluster_name = cluster_config.name
            logger.info(
                "Creating cluster '%s' with provider '%s'",
                cluster_name,
                cluster_config.provider,
            )

            try:
                provider = self.providers[cluster_name]
                success = provider.create_cluster(**cluster_config.kwargs)
                results[cluster_name] = success

                if success:
                    logger.info("✅ Cluster '%s' created successfully", cluster_name)
                    self._update_state_file(cluster_name, "created", cluster_config.provider)
                else:
                    logger.error("❌ Failed to create cluster '%s'", cluster_name)

            except ProviderError as e:
                logger.error("❌ Error creating cluster '%s': %s", cluster_name, e)
                results[cluster_name] = False
            except (OSError, subprocess.SubprocessError, RuntimeError, ValueError) as e:
                logger.error("❌ System error creating cluster '%s': %s", cluster_name, e)
                results[cluster_name] = False

        return results

    def delete(self) -> dict[str, bool]:
        """
        Delete all clusters defined in the manifest.

        Returns:
            dict[str, bool]: Dictionary mapping cluster names to success status
        """
        logger.info("Deleting clusters from manifest...")
        results = {}

        for cluster_config in self.manifest.clusters:
            cluster_name = cluster_config.name
            logger.info("Deleting cluster '%s'", cluster_name)

            try:
                provider = self.providers[cluster_name]
                success = provider.delete_cluster()
                results[cluster_name] = success

                if success:
                    logger.info("✅ Cluster '%s' deleted successfully", cluster_name)
                    self._update_state_file(cluster_name, "deleted", cluster_config.provider)
                else:
                    logger.error("❌ Failed to delete cluster '%s'", cluster_name)

            except ProviderError as e:
                logger.error("❌ Error deleting cluster '%s': %s", cluster_name, e)
                results[cluster_name] = False
            except (OSError, subprocess.SubprocessError, RuntimeError, ValueError) as e:
                logger.error("❌ System error deleting cluster '%s': %s", cluster_name, e)
                results[cluster_name] = False

        return results

    def status(self) -> dict[str, dict[str, Any]]:
        """
        Get status of all clusters defined in the manifest.

        Returns:
            dict[str, dict[str, Any]]: Dictionary mapping cluster names to status information
        """
        logger.info("Getting cluster status...")
        results = {}

        for cluster_config in self.manifest.clusters:
            cluster_name = cluster_config.name

            try:
                provider = self.providers[cluster_name]
                status_info = provider.get_cluster_status()
                results[cluster_name] = status_info

                if status_info.get("ready", False):
                    logger.info("✅ Cluster '%s': ready", cluster_name)
                elif status_info.get("exists", False):
                    logger.warning("⚠️  Cluster '%s': exists but not ready", cluster_name)
                else:
                    logger.warning("❌ Cluster '%s': does not exist", cluster_name)

            except ProviderError as e:
                logger.error("❌ Error getting status for cluster '%s': %s", cluster_name, e)
                results[cluster_name] = {
                    "error": str(e),
                    "exists": False,
                    "ready": False,
                }
            except (OSError, subprocess.SubprocessError, RuntimeError, ValueError) as e:
                logger.error(
                    "❌ System error getting status for cluster '%s': %s", cluster_name, e
                )
                results[cluster_name] = {
                    "error": str(e),
                    "exists": False,
                    "ready": False,
                }

        return results

    def _update_state_file(self, cluster_name: str, action: str, provider: str) -> None:
        """
        Update persistent state file with cluster information.

        Args:
            cluster_name (str): Name of the cluster
            action (str): Action performed ('created' or 'deleted')
            provider (str): Provider name used
        """
        state_file = Path(".localargo") / "state.json"

        # Load existing state
        state: dict[str, Any] = {"clusters": []}
        if state_file.exists():
            try:
                with open(state_file, encoding="utf-8") as f:
                    state = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                # Reset to empty state if file is corrupted
                state = {"clusters": []}

        # Find or create cluster entry
        cluster_entry = None
        for cluster in state["clusters"]:
            if cluster["name"] == cluster_name:
                cluster_entry = cluster
                break

        if cluster_entry is None:
            cluster_entry = {
                "name": cluster_name,
                "provider": provider,
                "created": None,
                "last_action": None,
            }
            state["clusters"].append(cluster_entry)

        # Update cluster entry
        timestamp = int(time.time())
        if action == "created":
            cluster_entry["created"] = timestamp
        cluster_entry["last_action"] = action
        cluster_entry["last_updated"] = timestamp

        # Ensure state directory exists
        state_file.parent.mkdir(exist_ok=True)

        # Write updated state
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
