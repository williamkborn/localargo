# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>
#
# SPDX-License-Identifier: MIT
"""State checkers for idempotent execution framework.

These functions check if components are already installed/configured
before executing installation steps.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING, Any

from localargo.core.cluster import cluster_manager
from localargo.core.types import StepStatus
from localargo.logging import logger
from localargo.utils.cli import run_subprocess
from localargo.utils.proc import ProcessError, run_json

if TYPE_CHECKING:
    from localargo.config.manifest import UpManifest
    from localargo.core.argocd import ArgoClient


def check_cluster(_manifest: UpManifest, _client: ArgoClient | None = None) -> StepStatus:
    """Check if the cluster is already created and ready."""
    cluster = _manifest.clusters[0]
    provider = cluster_manager.get_provider(cluster.provider)

    try:
        status = provider.get_cluster_status(cluster.name)
        if status.get("exists", False) and status.get("ready", False):
            return StepStatus(
                state="completed",
                reason=f"Cluster '{cluster.name}' exists and is ready",
                details=status,
            )
        if status.get("exists", False):
            return StepStatus(
                state="pending",
                reason=f"Cluster '{cluster.name}' exists but is not ready",
                details=status,
            )
        return StepStatus(
            state="pending", reason=f"Cluster '{cluster.name}' does not exist", details=status
        )
    except Exception as e:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        logger.warning("Failed to check cluster status: %s", e)
        return StepStatus(state="pending", reason=f"Unable to determine cluster status: {e}")


def check_argocd(_manifest: UpManifest, _client: ArgoClient | None = None) -> StepStatus:
    """Check if ArgoCD is already installed."""
    try:
        # Check if argocd-server deployment exists and is ready
        result = run_subprocess(
            [
                "kubectl",
                "get",
                "deployment",
                "argocd-server",
                "-n",
                "argocd",
                "--ignore-not-found",
            ]
        )

        if "argocd-server" not in result.stdout:
            return StepStatus(state="pending", reason="ArgoCD server deployment not found")

        # Check if deployment is ready
        result = run_subprocess(
            [
                "kubectl",
                "get",
                "deployment",
                "argocd-server",
                "-n",
                "argocd",
                "-o",
                "jsonpath={.status.readyReplicas}",
            ]
        )

        ready_replicas = result.stdout.strip()
        if ready_replicas and int(ready_replicas) > 0:
            return StepStatus(
                state="completed",
                reason="ArgoCD is installed and ready",
                details={"ready_replicas": int(ready_replicas)},
            )
        return StepStatus(state="pending", reason="ArgoCD deployment exists but is not ready")

    except ProcessError:
        return StepStatus(state="pending", reason="ArgoCD deployment not found")
    except Exception as e:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        logger.warning("Failed to check ArgoCD status: %s", e)
        return StepStatus(state="pending", reason=f"Unable to determine ArgoCD status: {e}")


def check_nginx_ingress(
    _manifest: UpManifest, _client: ArgoClient | None = None
) -> StepStatus:
    """Check if nginx-ingress controller is already installed."""
    try:
        # Check if ingress-nginx deployment exists
        result = run_subprocess(
            [
                "kubectl",
                "get",
                "deployment",
                "ingress-nginx-controller",
                "-n",
                "ingress-nginx",
                "--ignore-not-found",
            ]
        )

        if "ingress-nginx-controller" not in result.stdout:
            return StepStatus(state="pending", reason="Nginx ingress controller not found")

        # Check if deployment is ready
        result = run_subprocess(
            [
                "kubectl",
                "get",
                "deployment",
                "ingress-nginx-controller",
                "-n",
                "ingress-nginx",
                "-o",
                "jsonpath={.status.readyReplicas}",
            ]
        )

        ready_replicas = result.stdout.strip()
        if ready_replicas and int(ready_replicas) > 0:
            return StepStatus(
                state="completed",
                reason="Nginx ingress controller is installed and ready",
                details={"ready_replicas": int(ready_replicas)},
            )
        return StepStatus(
            state="pending", reason="Nginx ingress controller exists but is not ready"
        )

    except ProcessError:
        return StepStatus(state="pending", reason="Nginx ingress controller not found")
    except (OSError, ValueError, RuntimeError) as e:
        logger.warning("Failed to check nginx ingress status: %s", e)
        return StepStatus(
            state="pending", reason=f"Unable to determine nginx ingress status: {e}"
        )


def _check_secret_exists(namespace: str, secret_name: str) -> bool:
    """Check if a specific secret exists in a namespace."""
    try:
        result = run_subprocess(
            [
                "kubectl",
                "get",
                "secret",
                secret_name,
                "-n",
                namespace,
                "--ignore-not-found",
            ],
            check=False,
        )
        # Secret exists if kubectl succeeds and output contains the secret name
        return result.returncode == 0 and (
            hasattr(result, "stdout") and secret_name in result.stdout
        )
    except subprocess.CalledProcessError:
        return False


def check_secrets(manifest: UpManifest, _client: ArgoClient | None = None) -> StepStatus:
    """Check if all required secrets are already created.

    Groups secrets by (namespace, secret_name) since multiple manifest entries
    may define keys for the same secret.
    """
    if not manifest.secrets:
        return StepStatus(state="completed", reason="No secrets to check")

    # Get unique secrets (namespace, secret_name combinations) in order
    # Use dict to maintain insertion order while deduplicating
    unique_secrets = dict.fromkeys(
        (sec.namespace, sec.secret_name) for sec in manifest.secrets
    )

    missing_secrets = []
    existing_secrets = []

    for namespace, secret_name in unique_secrets:
        if _check_secret_exists(namespace, secret_name):
            existing_secrets.append(f"{namespace}/{secret_name}")
        else:
            missing_secrets.append(f"{namespace}/{secret_name}")

    if not missing_secrets:
        return StepStatus(
            state="completed",
            reason=f"All {len(existing_secrets)} secrets exist",
            details={"existing_secrets": existing_secrets},
        )
    return StepStatus(
        state="pending",
        reason=f"{len(missing_secrets)} of {len(unique_secrets)} secrets missing",
        details={"missing_secrets": missing_secrets, "existing_secrets": existing_secrets},
    )


def check_repo_creds(manifest: UpManifest, client: ArgoClient | None = None) -> StepStatus:
    """Check if all required repo credentials are configured in ArgoCD."""
    if not manifest.repo_creds:
        return StepStatus(state="completed", reason="No repo credentials to check")

    if not client:
        return StepStatus(
            state="pending", reason="ArgoCD client required for repo credential checking"
        )

    configured_repos = _get_configured_repos()
    if configured_repos is None:
        return StepStatus(state="pending", reason="Unable to list ArgoCD repositories")

    missing_creds, existing_creds = _categorize_repo_creds(
        manifest.repo_creds, configured_repos
    )
    return _create_repo_creds_status(manifest.repo_creds, missing_creds, existing_creds)


def _get_configured_repos() -> dict[str, dict] | None:
    """Get configured repositories from ArgoCD. Returns None if unable to retrieve."""
    try:
        result = run_json(["argocd", "repo", "list", "-o", "json"])
        return {repo.get("repo"): repo for repo in result} if isinstance(result, list) else {}
    except ProcessError:
        return None


def _categorize_repo_creds(
    repo_creds: list, configured_repos: dict[str, dict]
) -> tuple[list[str], list[str]]:
    """Categorize repo credentials into missing and existing."""
    missing_creds = []
    existing_creds = []

    for cred in repo_creds:
        if cred.repo_url in configured_repos:
            existing_creds.append(cred.repo_url)
        else:
            missing_creds.append(cred.repo_url)

    return missing_creds, existing_creds


def _create_repo_creds_status(
    repo_creds: list, missing_creds: list[str], existing_creds: list[str]
) -> StepStatus:
    """Create appropriate status based on missing and existing credentials."""
    if not missing_creds:
        return StepStatus(
            state="completed",
            reason=f"All {len(existing_creds)} repo credentials configured",
            details={"configured_repos": existing_creds},
        )
    return StepStatus(
        state="pending",
        reason=f"{len(missing_creds)} of {len(repo_creds)} repo credentials missing",
        details={"missing_creds": missing_creds, "existing_creds": existing_creds},
    )


def check_apps(manifest: UpManifest, client: ArgoClient | None = None) -> StepStatus:
    """Check if all applications are deployed and synced."""
    if not manifest.apps:
        return StepStatus(state="completed", reason="No applications to check")

    if not client:
        return StepStatus(
            state="pending", reason="ArgoCD client required for application checking"
        )

    app_states = _get_app_states(client)
    if app_states is None:
        return StepStatus(state="pending", reason="Unable to get ArgoCD applications")

    app_categories = _categorize_apps(manifest.apps, app_states)
    return _create_apps_status(manifest.apps, app_categories)


def _get_app_states(client: ArgoClient) -> dict[str, Any] | None:
    """Get application states from ArgoCD. Returns None if unable to retrieve."""
    try:
        argocd_apps = client.get_apps()
        return {app.name: app for app in argocd_apps}
    except (OSError, ValueError, RuntimeError):
        return None


def _categorize_apps(apps: list, app_states: dict[str, Any]) -> dict[str, list]:
    """Categorize applications into synced, missing, and unsynced."""
    missing_apps = []
    synced_apps = []
    unsynced_apps = []

    for app in apps:
        if app.name not in app_states:
            missing_apps.append(app.name)
        else:
            app_state = app_states[app.name]
            if _is_app_synced_and_healthy(app_state):
                synced_apps.append(app.name)
            else:
                unsynced_apps.append(
                    {
                        "name": app.name,
                        "sync_status": app_state.sync,
                        "health_status": app_state.health,
                    }
                )

    return {
        "missing_apps": missing_apps,
        "synced_apps": synced_apps,
        "unsynced_apps": unsynced_apps,
    }


def _is_app_synced_and_healthy(app_state: Any) -> bool:
    """Check if an application is synced and healthy."""
    return bool(app_state.sync == "Synced" and app_state.health == "Healthy")


def _create_apps_status(apps: list, categories: dict[str, list]) -> StepStatus:
    """Create appropriate status based on application categories."""
    missing_apps = categories["missing_apps"]
    synced_apps = categories["synced_apps"]
    unsynced_apps = categories["unsynced_apps"]

    total_apps = len(apps)
    synced_count = len(synced_apps)
    missing_count = len(missing_apps)
    unsynced_count = len(unsynced_apps)

    if missing_count == 0 and unsynced_count == 0:
        return StepStatus(
            state="completed",
            reason=f"All {synced_count} applications are synced and healthy",
            details={"synced_apps": synced_apps},
        )

    details = {
        "synced_apps": synced_apps,
        "missing_apps": missing_apps,
        "unsynced_apps": unsynced_apps,
    }

    status_reason = _determine_apps_status_reason(total_apps, missing_count, unsynced_count)

    return StepStatus(state="pending", reason=status_reason, details=details)


def _determine_apps_status_reason(
    total_apps: int, missing_count: int, unsynced_count: int
) -> str:
    """Determine the status reason based on missing and unsynced counts."""
    if missing_count > 0 and unsynced_count == 0:
        return f"{missing_count} of {total_apps} applications not deployed"
    if missing_count == 0 and unsynced_count > 0:
        return f"{unsynced_count} of {total_apps} applications need sync"
    return f"{missing_count + unsynced_count} of {total_apps} applications need attention"
