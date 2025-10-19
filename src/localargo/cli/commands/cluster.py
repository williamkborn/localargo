# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Cluster management commands for ArgoCD development.

This module provides commands for managing Kubernetes clusters used for ArgoCD development.
"""

from __future__ import annotations

import base64
import subprocess

import rich_click as click

from localargo.core.cluster import cluster_manager
from localargo.eyecandy.table_renderer import TableRenderer
from localargo.logging import logger
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
                    "🌐 ArgoCD UI will be available at: "
                    "https://argocd.localtest.me (after installation)"
                )
                logger.info("🔧 Development ports available: 30000-30002")
                logger.info(
                    "🚀 Cluster configured with direct port access to ingress controller"
                )
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


@cluster.command()
@click.argument("name")
@click.option(
    "--provider",
    type=click.Choice(["kind", "k3s"]),
    default="kind",
    help="Cluster provider",
)
def delete(name: str, provider: str) -> None:
    """Delete a specific cluster."""
    logger.info("Deleting %s cluster '%s'...", provider, name)

    success = cluster_manager.delete_cluster(provider, name)
    if success:
        logger.info("✅ Cluster '%s' deleted successfully", name)
    else:
        error_msg = f"Failed to delete cluster '{name}'"
        logger.error("❌ %s", error_msg)
        raise click.ClickException(error_msg)


@cluster.command()
@click.argument("name")
@click.option(
    "--provider",
    type=click.Choice(["kind", "k3s"]),
    default="kind",
    help="Cluster provider",
)
def password(name: str, provider: str) -> None:
    """Get ArgoCD initial admin password for a cluster."""
    # Check if kubectl is available
    kubectl_path = ensure_kubectl_available()

    logger.info("Getting ArgoCD password for %s cluster '%s'...", provider, name)

    try:
        # Switch to the cluster context if needed
        cluster_manager.switch_context(f"{provider}-{name}")

        # Get the ArgoCD initial admin secret
        result = subprocess.run(
            [
                kubectl_path,
                "get",
                "secret",
                "argocd-initial-admin-secret",
                "-n",
                "argocd",
                "-o",
                "jsonpath={.data.password}",
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        if result.stdout:
            # Decode the base64 password
            decoded_password = base64.b64decode(result.stdout.strip()).decode("utf-8")
            logger.info("🔐 ArgoCD Login Credentials:")
            logger.info("   Username: admin")
            logger.info("   Password: %s", decoded_password)
            logger.info("   URL: https://argocd.localtest.me")
        else:
            logger.error("❌ No password found in ArgoCD initial admin secret")
            logger.info("💡 Make sure ArgoCD is installed and the initial admin secret exists")

    except subprocess.CalledProcessError as e:
        logger.error("❌ Failed to get ArgoCD password: %s", e)
        if "NotFound" in e.stderr:
            logger.info("💡 ArgoCD may not be installed or the cluster may not exist")
        error_msg = "Failed to retrieve ArgoCD password"
        raise click.ClickException(error_msg) from e
