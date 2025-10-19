# SPDX-FileCopyrightText: 2025-present U.N. Owen <void@some.where>
from __future__ import annotations

#
# SPDX-License-Identifier: MIT
import shutil
import subprocess

import click

from localargo.core.cluster import cluster_manager
from localargo.logging import logger


@click.group()
def cluster() -> None:
    """Manage Kubernetes clusters for ArgoCD development."""


@cluster.command()
@click.option("--context", "-c", help="Specific context to use")
@click.option("--namespace", "-n", default="argocd", help="ArgoCD namespace")
def status(context: str | None, namespace: str) -> None:
    """Show current cluster and ArgoCD status."""
    # Check if kubectl is available
    kubectl_path = shutil.which("kubectl")
    if not kubectl_path:
        msg = "kubectl not found"
        raise FileNotFoundError(msg)

    try:
        # Get cluster status
        if context:
            # Use specific context
            logger.info(f"Using context: {context}")
            cluster_status = {"context": context, "ready": True}  # Assume ready if specified
        else:
            cluster_status = cluster_manager.get_cluster_status()
            logger.info(f"Current context: {cluster_status.get('context', 'unknown')}")

        # Check if ArgoCD is installed
        result = subprocess.run(
            [kubectl_path, "get", "deployment", "argocd-server", "-n", namespace, "--ignore-not-found"],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode == 0 and result.stdout.strip():
            logger.info(f"✅ ArgoCD found in namespace: {namespace}")
            # Show ArgoCD pods status
            subprocess.run(
                [kubectl_path, "get", "pods", "-n", namespace, "-l", "app.kubernetes.io/name=argocd-server"],
                check=False,
            )
        else:
            logger.warning(f"❌ ArgoCD not found in namespace: {namespace}")
            logger.info("Run 'localargo cluster init' to set up ArgoCD locally")

    except subprocess.CalledProcessError as e:
        logger.error(f"Error checking cluster status: {e}")
    except FileNotFoundError:
        logger.error("kubectl not found. Please install kubectl.")


@cluster.command()
@click.option("--provider", type=click.Choice(["kind", "k3s"]), default="kind", help="Local cluster provider")
@click.option("--name", default="localargo", help="Cluster name")
def init(provider: str, name: str) -> None:
    """Initialize a local Kubernetes cluster with ArgoCD."""
    logger.info(f"Initializing {provider} cluster '{name}' with ArgoCD...")

    try:
        success = cluster_manager.create_cluster(provider, name)
        if success:
            logger.info(f"✅ {provider.upper()} cluster '{name}' created successfully")
            if provider == "kind":
                logger.info("🌐 ArgoCD UI will be available at: http://localhost:8080 (after installation)")
                logger.info("🔧 Development ports available: 30000-30002")
        else:
            logger.error(f"Failed to create {provider} cluster '{name}'")
    except (subprocess.CalledProcessError, OSError, ValueError) as e:
        logger.error(f"Error creating cluster: {e}")


@cluster.command()
@click.argument("context_name")
def switch(context_name: str) -> None:
    """Switch to a different Kubernetes context."""
    if cluster_manager.switch_context(context_name):
        logger.info(f"✅ Switched to context: {context_name}")
    else:
        logger.error(f"Context '{context_name}' not found")


@cluster.command()
def list_contexts() -> None:
    """List available Kubernetes contexts."""
    contexts = cluster_manager.get_contexts()
    if contexts:
        logger.info("Available contexts:")
        for ctx in contexts:
            logger.info(f"  {ctx}")
    else:
        logger.error("No contexts found or kubectl not available")
