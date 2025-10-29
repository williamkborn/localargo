# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Idempotent execution framework for up-manifest operations.

This module provides a step-based execution system that checks current state
before performing operations, enabling idempotent execution of up commands.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from localargo.core.checkers import (
    check_apps,
    check_argocd,
    check_cluster,
    check_nginx_ingress,
    check_repo_creds,
    check_secrets,
)
from localargo.core.executors import (
    execute_apps_deployment,
    execute_argocd_installation,
    execute_cluster_creation,
    execute_nginx_installation,
    execute_repo_creds_setup,
    execute_secrets_creation,
)
from localargo.core.types import ExecutionStep, StepStatus
from localargo.logging import logger

if TYPE_CHECKING:
    from localargo.config.manifest import UpManifest
    from localargo.core.argocd import ArgoClient


class ExecutionEngine:
    """Orchestrates idempotent execution of up-manifest steps."""

    def __init__(self, steps: list[ExecutionStep]) -> None:
        self.steps = steps
        self.results: dict[str, StepStatus] = {}

    def execute(
        self,
        manifest: UpManifest,
        client: ArgoClient | None = None,
        *,
        force: bool = False,
    ) -> dict[str, StepStatus]:
        """Execute all steps, checking state first unless force=True.

        Args:
            manifest (UpManifest): The up-manifest to execute
            client (ArgoClient | None): ArgoCD client for ArgoCD operations (created lazily if None)
            force (bool): If True, skip state checking and execute all steps

        Returns:
            dict[str, StepStatus]: Dictionary mapping step names to their execution status
        """
        self.results = {}

        for step in self.steps:
            # Lazily create ArgoCD client when we reach a step that needs it
            client = self._ensure_client_for_step(step, client)
            step_client = client if step.requires_client else None

            if force:
                if not self._execute_step_force(manifest, step, step_client):
                    break  # Stop execution on failure
            else:
                self._execute_step_normal(manifest, step, step_client)

        return self.results

    def _ensure_client_for_step(
        self, step: ExecutionStep, client: ArgoClient | None
    ) -> ArgoClient | None:
        """Ensure ArgoCD client exists if step requires it."""
        if step.requires_client and client is None:
            try:
                # pylint: disable=import-outside-toplevel
                from localargo.core.argocd import ArgoClient

                client = ArgoClient(namespace="argocd", insecure=True)
            except Exception as e:  # noqa: BLE001 # pylint: disable=broad-exception-caught
                # If client creation fails, log and continue
                # The step will likely fail but that's expected
                logger.warning("Failed to create ArgoCD client: %s", e)
        return client

    def _execute_step_force(
        self, manifest: UpManifest, step: ExecutionStep, client: ArgoClient | None
    ) -> bool:
        """Execute a step in force mode. Returns False if execution should stop."""
        logger.info("🔄 Force executing: %s", step.description)
        try:
            step.execute(manifest, client)
        except (OSError, ValueError, RuntimeError) as e:
            logger.error("❌ Failed to execute %s: %s", step.name, e)
            self.results[step.name] = StepStatus(state="failed", reason=str(e))
            return False  # Stop execution on failure

        self.results[step.name] = StepStatus(state="completed", reason="Force executed")
        return True

    def _execute_step_normal(
        self, manifest: UpManifest, step: ExecutionStep, client: ArgoClient | None
    ) -> None:
        """Execute a step in normal mode (check first, then execute if needed)."""
        logger.info("🔍 Checking: %s", step.description)
        status = step.check(manifest, client)

        if status.is_completed:
            logger.info("⏭️  Skipped: %s (%s)", step.description, status.reason)
            self.results[step.name] = status
            return

        # Execute the step
        logger.info("⚙️  Executing: %s", step.description)
        try:
            step.execute(manifest, client)
            self.results[step.name] = StepStatus(
                state="completed", reason="Executed successfully"
            )
            logger.info("✅ Completed: %s", step.description)
        except (OSError, ValueError, RuntimeError) as e:
            logger.error("❌ Failed: %s - %s", step.description, e)
            self.results[step.name] = StepStatus(state="failed", reason=str(e))
            # Stop execution on failure and re-raise the exception
            raise

    def get_status_summary(self) -> dict[str, int]:
        """Get summary of execution results."""
        summary = {"completed": 0, "skipped": 0, "failed": 0, "pending": 0}

        for status in self.results.values():
            if status.state == "completed":
                summary["completed"] += 1
            elif status.state == "skipped":
                summary["skipped"] += 1
            elif status.state == "failed":
                summary["failed"] += 1
            else:
                summary["pending"] += 1

        return summary


# Standard execution steps for up-manifest operations
# IMPORTANT: Order matters! Steps must be executed in dependency order:
#   1. cluster must exist before argocd can be installed
#   2. argocd must be ready before client-dependent steps (repo-creds, apps)
#   3. secrets must be created before apps (apps may reference secrets)
STANDARD_UP_STEPS = [
    ExecutionStep(
        name="cluster",
        description="Create Kubernetes cluster",
        check_function=check_cluster,
        execute_function=execute_cluster_creation,
        requires_client=False,
    ),
    ExecutionStep(
        name="argocd",
        description="Install ArgoCD",
        check_function=check_argocd,
        execute_function=execute_argocd_installation,
        requires_client=False,
    ),
    ExecutionStep(
        name="nginx",
        description="Install nginx ingress controller",
        check_function=check_nginx_ingress,
        execute_function=execute_nginx_installation,
        requires_client=False,
    ),
    ExecutionStep(
        name="secrets",
        description="Create Kubernetes secrets",
        check_function=check_secrets,
        execute_function=execute_secrets_creation,
        requires_client=False,
    ),
    ExecutionStep(
        name="repo-creds",
        description="Configure ArgoCD repository credentials",
        check_function=check_repo_creds,
        execute_function=execute_repo_creds_setup,
        requires_client=True,
    ),
    ExecutionStep(
        name="apps",
        description="Deploy and sync ArgoCD applications",
        check_function=check_apps,
        execute_function=execute_apps_deployment,
        requires_client=True,
    ),
]


def create_up_execution_engine() -> ExecutionEngine:
    """Create an execution engine configured for up-manifest operations."""
    return ExecutionEngine(STANDARD_UP_STEPS)
