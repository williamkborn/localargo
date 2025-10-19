# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Cluster management commands for ArgoCD development.

This module provides commands for managing Kubernetes clusters used for ArgoCD development.
"""

from __future__ import annotations

import subprocess
from contextlib import suppress

import rich_click as click

from localargo.core.cluster import cluster_manager
from localargo.eyecandy.progress_steps import StepLogger
from localargo.eyecandy.table_renderer import TableRenderer
from localargo.logging import logger
from localargo.manager import ClusterManager, ClusterManagerError
from localargo.utils.cli import (
    build_kubectl_get_cmd,
    ensure_kubectl_available,
)


@click.group()
def cluster() -> None:
    """Manage Kubernetes clusters for ArgoCD development."""


@cluster.command()
@click.option("--context", "-c", help="Specific context to use")
@click.option("--namespace", "-n", default="argocd", help="ArgoCD namespace")
def status(context: str | None, namespace: str) -> None:
    """Show current cluster and ArgoCD status."""
    # Check if kubectl is available
    kubectl_path = ensure_kubectl_available()

    try:
        # Get cluster status
        if context:
            # Use specific context
            logger.info("Using context: %s", context)
            cluster_status = {"context": context, "ready": True}  # Assume ready if specified
        else:
            cluster_status = cluster_manager.get_cluster_status()
            logger.info("Current context: %s", cluster_status.get("context", "unknown"))

        # Check if ArgoCD is installed
        result = subprocess.run(
            [
                kubectl_path,
                "get",
                "deployment",
                "argocd-server",
                "-n",
                namespace,
                "--ignore-not-found",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        # Prepare status data for table display
        status_data = {
            "Cluster Context": cluster_status.get("context", "unknown"),
            "Cluster Ready": "Yes" if cluster_status.get("ready", False) else "No",
            "ArgoCD Status": "Installed"
            if result.returncode == 0 and result.stdout.strip()
            else "Not Found",
            "Namespace": namespace,
        }

        # Use table renderer for nice display
        table_renderer = TableRenderer()
        table_renderer.render_key_values("Cluster Status", status_data)

        if result.returncode == 0 and result.stdout.strip():
            logger.info("✅ ArgoCD found in namespace: %s", namespace)
            # Show ArgoCD pods status in a simple list
            pod_result = subprocess.run(
                build_kubectl_get_cmd(
                    kubectl_path,
                    "pods",
                    namespace,
                    label_selector="app.kubernetes.io/name=argocd-server",
                    output_format=(
                        "custom-columns=NAME:.metadata.name,"
                        "STATUS:.status.phase,"
                        "READY:.status.containerStatuses[0].ready"
                    ),
                ),
                check=False,
                capture_output=True,
                text=True,
            )

            if pod_result.returncode == 0 and pod_result.stdout.strip():
                pod_lines = pod_result.stdout.strip().split("\n")[1:]  # Skip header
                if pod_lines:
                    table_renderer.render_simple_list(
                        [line for line in pod_lines if line.strip()], "ArgoCD Pods"
                    )
        else:
            logger.warning("❌ ArgoCD not found in namespace: %s", namespace)
            logger.info("Run 'localargo cluster init' to set up ArgoCD locally")

    except subprocess.CalledProcessError as e:
        logger.error("Error checking cluster status: %s", e)
    except FileNotFoundError:
        logger.error("kubectl not found. Please install kubectl.")


@cluster.command()
@click.option(
    "--provider",
    type=click.Choice(["kind", "k3s"]),
    default="kind",
    help="Local cluster provider",
)
@click.option("--name", default="localargo", help="Cluster name")
def init(provider: str, name: str) -> None:
    """Initialize a local Kubernetes cluster with ArgoCD."""
    logger.info("Initializing %s cluster '%s' with ArgoCD...", provider, name)

    try:
        success = cluster_manager.create_cluster(provider, name)
        if success:
            logger.info("✅ %s cluster '%s' created successfully", provider.upper(), name)
            if provider == "kind":
                logger.info(
                    "🌐 ArgoCD UI will be available at: http://localhost:8080 (after installation)"
                )
                logger.info("🔧 Development ports available: 30000-30002")
        else:
            logger.error("Failed to create %s cluster '%s'", provider, name)
    except subprocess.CalledProcessError as e:
        logger.error("❌ Creating cluster failed with return code %s", e.returncode)
        if e.stderr:
            logger.error("Error details: %s", e.stderr.strip())
        raise
    except (OSError, ValueError) as e:
        logger.error("Error creating cluster: %s", e)


@cluster.command()
@click.argument("context_name")
def switch(context_name: str) -> None:
    """Switch to a different Kubernetes context."""
    if cluster_manager.switch_context(context_name):
        logger.info("✅ Switched to context: %s", context_name)
    else:
        logger.error("Context '%s' not found", context_name)


@cluster.command()
def list_contexts() -> None:
    """List available Kubernetes contexts."""
    contexts = cluster_manager.get_contexts()
    if contexts:
        logger.info("Available contexts:")
        for ctx in contexts:
            logger.info("  %s", ctx)
    else:
        logger.error("No contexts found or kubectl not available")


# Declarative cluster management commands


@cluster.command()
@click.argument("manifest", type=click.Path(exists=True), default="clusters.yaml")
def apply(manifest: str) -> None:
    """Create clusters defined in manifest file."""
    steps = ["loading manifest", "creating clusters", "configuring contexts", "finalizing"]

    try:
        with StepLogger(steps) as step_logger:
            step_logger.step("loading manifest", status="success", manifest_path=manifest)

            manager = ClusterManager(manifest)
            step_logger.step("creating clusters", status="success")

            results = manager.apply()

            successful = sum(results.values())
            total = len(results)

            # Show detailed results using table renderer
            if results:
                table_data = []
                for cluster_name, success in results.items():
                    table_data.append(
                        {
                            "name": cluster_name,
                            "status": "Created" if success else "Failed",
                            "result": "✅" if success else "❌",
                        }
                    )

                table_renderer = TableRenderer()
                table_renderer.render_list(["Cluster", "Status", "Result"], table_data)

            if successful == total:
                step_logger.step("configuring contexts", status="success")
                step_logger.step("finalizing", status="success")
            else:
                step_logger.step(
                    "configuring contexts",
                    status="warning",
                    message=f"Only {successful}/{total} clusters created",
                )
                step_logger.step("finalizing", status="warning")

    except ClusterManagerError as e:
        # Log the error step if we have an active step logger
        with suppress(NameError):
            step_logger.step("creating clusters", status="error", error_msg=str(e))
            logger.error("Error applying manifest: %s", e)
        raise click.ClickException(str(e)) from e
    except Exception as e:
        # Log the error step if we have an active step logger
        with suppress(NameError):
            step_logger.step("creating clusters", status="error", error_msg=str(e))
        logger.error("Unexpected error: %s", e)
        raise click.ClickException(str(e)) from e


@cluster.command()
@click.argument("manifest", type=click.Path(exists=True), default="clusters.yaml")
def delete(manifest: str) -> None:
    """Delete clusters defined in manifest file."""
    try:
        manager = ClusterManager(manifest)
        results = manager.delete()

        successful = sum(results.values())
        total = len(results)

        if successful == total:
            logger.info("✅ Successfully deleted %s/%s clusters", successful, total)
        else:
            logger.warning("⚠️  Deleted %s/%s clusters", successful, total)

        # Show detailed results
        for cluster_name, success in results.items():
            cluster_status = "✅" if success else "❌"
            logger.info("  %s %s", cluster_status, cluster_name)

    except ClusterManagerError as e:
        logger.error("Error deleting clusters: %s", e)
        raise click.ClickException(str(e)) from e
    except Exception as e:
        logger.error("Unexpected error: %s", e)
        raise click.ClickException(str(e)) from e


@cluster.command()
@click.argument("manifest", type=click.Path(exists=True), default="clusters.yaml")
def status_manifest(manifest: str) -> None:
    """Show status of clusters defined in manifest file."""
    try:
        manager = ClusterManager(manifest)
        results = manager.status()

        ready_count = 0
        exists_count = 0

        # Prepare data for table display
        table_data = []
        for cluster_name, status_info in results.items():
            exists = status_info.get("exists", False)
            ready = status_info.get("ready", False)

            if exists:
                exists_count += 1
                if ready:
                    ready_count += 1

            # Determine status for table
            if "error" in status_info:
                cluster_status = f"Error: {status_info['error']}"
            elif ready:
                cluster_status = "Ready"
            elif exists:
                cluster_status = "Exists (not ready)"
            else:
                cluster_status = "Does not exist"

            table_data.append(
                {
                    "Cluster": cluster_name,
                    "Exists": "Yes" if exists else "No",
                    "Ready": "Yes" if ready else "No",
                    "Status": cluster_status,
                }
            )

        # Use table renderer for nice display
        table_renderer = TableRenderer()
        table_renderer.render_list(["Cluster", "Exists", "Ready", "Status"], table_data)

        # Show summary
        summary_data = {
            "Total Clusters": len(results),
            "Existing Clusters": exists_count,
            "Ready Clusters": ready_count,
            "Success Rate": f"{ready_count}/{exists_count}" if exists_count > 0 else "N/A",
        }
        table_renderer.render_key_values("Summary", summary_data)

    except ClusterManagerError as e:
        logger.error("Error getting cluster status: %s", e)
        raise click.ClickException(str(e)) from e
    except Exception as e:
        logger.error("Unexpected error: %s", e)
        raise click.ClickException(str(e)) from e
