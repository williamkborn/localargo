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
    kubectl_path = ensure_kubectl_available()

    try:
        cluster_status = _get_cluster_status(context)
        argocd_installed = _check_argocd_installation(kubectl_path, namespace)

        _display_cluster_status(cluster_status, namespace, argocd_installed=argocd_installed)

        if argocd_installed:
            _display_argocd_pods_status(kubectl_path, namespace)
        else:
            _show_argocd_not_found_message(namespace)

    except subprocess.CalledProcessError as e:
        logger.error("Error checking cluster status: %s", e)
    except FileNotFoundError:
        logger.error("kubectl not found. Please install kubectl.")


def _get_cluster_status(context: str | None) -> dict[str, str | bool]:
    """Get cluster status information."""
    if context:
        logger.info("Using context: %s", context)
        return {"context": context, "ready": True}  # Assume ready if specified

    cluster_status = cluster_manager.get_cluster_status()
    logger.info("Current context: %s", cluster_status.get("context", "unknown"))
    return cluster_status


def _check_argocd_installation(kubectl_path: str, namespace: str) -> bool:
    """Check if ArgoCD is installed in the specified namespace."""
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
    return bool(result.returncode == 0 and result.stdout.strip())


def _display_cluster_status(
    cluster_status: dict[str, str | bool], namespace: str, *, argocd_installed: bool
) -> None:
    """Display the cluster status information."""
    status_data = {
        "Cluster Context": cluster_status.get("context", "unknown"),
        "Cluster Ready": "Yes" if cluster_status.get("ready", False) else "No",
        "ArgoCD Status": "Installed" if argocd_installed else "Not Found",
        "Namespace": namespace,
    }

    table_renderer = TableRenderer()
    table_renderer.render_key_values("Cluster Status", status_data)


def _display_argocd_pods_status(kubectl_path: str, namespace: str) -> None:
    """Display ArgoCD pods status if available."""
    logger.info("✅ ArgoCD found in namespace: %s", namespace)

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
            table_renderer = TableRenderer()
            table_renderer.render_simple_list(
                [line for line in pod_lines if line.strip()], "ArgoCD Pods"
            )


def _show_argocd_not_found_message(namespace: str) -> None:
    """Show message when ArgoCD is not found."""
    logger.warning("❌ ArgoCD not found in namespace: %s", namespace)
    logger.info("Run 'localargo cluster init' to set up ArgoCD locally")


@cluster.command()
@click.option(
    "--provider",
    type=click.Choice(["kind", "k3s"]),
    default="kind",
    help="Local cluster provider",
)
@click.option("--name", default="localargo", help="Cluster name")
@click.argument("cluster_name", required=False)
def init(provider: str, name: str, cluster_name: str | None) -> None:
    """Initialize a local Kubernetes cluster with ArgoCD."""
    effective_name = cluster_name or name
    if _do_create_cluster(provider, effective_name):
        _log_kind_hints_if_applicable(provider)


def _do_create_cluster(provider: str, name: str) -> bool:
    """Create cluster with error handling and logging. Returns success flag."""
    logger.info("Initializing %s cluster '%s' with ArgoCD...", provider, name)

    try:
        success = cluster_manager.create_cluster(provider, name)
    except subprocess.CalledProcessError as e:
        logger.error("❌ Creating cluster failed with return code %s", e.returncode)
        if e.stderr:
            logger.error("Error details: %s", e.stderr.strip())
        return False
    except (OSError, ValueError) as e:
        logger.error("Error creating cluster: %s", e)
        return False

    if success:
        logger.info("✅ %s cluster '%s' created successfully", provider.upper(), name)
        return True

    logger.error("Failed to create %s cluster '%s'", provider, name)
    return False


def _log_kind_hints_if_applicable(provider: str) -> None:
    """Log helpful hints when using kind provider."""
    if provider != "kind":
        return
    logger.info(
        "🌐 ArgoCD UI will be available at: "
        "https://argocd.localtest.me (after installation)"
    )
    logger.info("🔧 Development ports available: 30000-30002")
    logger.info("🚀 Cluster configured with direct port access to ingress controller")


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


@cluster.command(name="list")
def list_clusters() -> None:
    """List available clusters across providers."""
    clusters = cluster_manager.list_clusters()

    rows: list[dict[str, str]] = []
    for c in clusters:
        provider = str(c.get("provider", ""))
        name = str(c.get("name", ""))
        cluster_status = (
            "ready"
            if c.get("ready", False)
            else ("exists" if c.get("exists", False) else "missing")
        )
        context = str(c.get("context", ""))
        rows.append(
            {
                "name": name,
                "provider": provider,
                "status": cluster_status,
                "context": context,
            }
        )

    renderer = TableRenderer()
    if rows:
        renderer.render_status_table(rows)
    else:
        renderer.render_simple_list([], "Clusters")


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
