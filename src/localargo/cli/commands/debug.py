# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Debugging and troubleshooting tools for ArgoCD.

This module provides commands for debugging and troubleshooting ArgoCD applications
and Kubernetes clusters.
"""

from __future__ import annotations

import subprocess

import click
import yaml

from localargo.logging import logger
from localargo.utils.cli import (
    build_kubectl_get_pods_cmd,
    build_kubectl_logs_cmd,
    check_cli_availability,
    ensure_argocd_available,
    ensure_kubectl_available,
)


@click.group()
def debug() -> None:
    """Debugging and troubleshooting tools for ArgoCD."""


@debug.command()
@click.argument("app_name")
@click.option("--namespace", "-n", default="argocd", help="ArgoCD namespace")
@click.option("--tail", "-t", type=int, default=50, help="Number of log lines to show")
def logs(app_name: str, namespace: str, tail: int) -> None:
    """Show ArgoCD application logs."""
    # Check if kubectl is available
    kubectl_path = ensure_kubectl_available()

    try:
        logger.info("Fetching logs for application '%s'...", app_name)

        # Get application pods
        label_selector = f"app.kubernetes.io/instance={app_name}"
        cmd = build_kubectl_get_pods_cmd(kubectl_path, namespace, label_selector)
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)

        pods = result.stdout.strip().split()

        if not pods:
            logger.info("❌ No pods found for application '%s'", app_name)
            return

        # Show logs for each pod
        for pod in pods:
            logger.info("\n📄 Logs for pod: %s", pod)
            logger.info("-" * 50)

            try:
                cmd = build_kubectl_logs_cmd(kubectl_path, namespace, pod, tail)
                subprocess.run(cmd, check=True)
            except subprocess.CalledProcessError as e:
                logger.info("❌ Error getting logs for pod %s: %s", pod, e)

    except subprocess.CalledProcessError as e:
        logger.info(
            "❌ Error: %s",
            e,
        )


@debug.command()
@click.argument("app_name")
@click.option("--check-images", is_flag=True, help="Check if container images exist")
@click.option("--check-secrets", is_flag=True, help="Check if referenced secrets exist")
def validate(app_name: str, *, check_images: bool, check_secrets: bool) -> None:
    """Validate ArgoCD application configuration."""
    # Check if argocd CLI is available
    argocd_path = ensure_argocd_available()

    # Check if kubectl is available if secrets checking is requested
    if check_secrets:
        kubectl_path = ensure_kubectl_available()

    try:
        logger.info("Validating application '%s'...", app_name)

        # Get application details
        result = subprocess.run(
            [argocd_path, "app", "get", app_name], capture_output=True, text=True, check=True
        )

        app_info = result.stdout

        # Basic validation checks
        checks = []

        # Check sync status
        if "OutOfSync" in app_info:
            checks.append(("❌", "Application is out of sync"))
        else:
            checks.append(("✅", "Application sync status OK"))

        # Check health status
        if "Degraded" in app_info or "Unknown" in app_info:
            checks.append(("❌", "Application health is degraded"))
        elif "Healthy" in app_info:
            checks.append(("✅", "Application health is OK"))

        # Check for images if requested
        if check_images:
            image_issues = _check_container_images(app_name)
            checks.extend(image_issues)

        # Check for secrets if requested
        if check_secrets:
            secret_issues = _check_secret_references(app_name, argocd_path, kubectl_path)
            checks.extend(secret_issues)

        # Display results
        logger.info("\nValidation Results:")
        logger.info("=" * 30)
        for status, message in checks:
            logger.info("%s %s", status, message)

    except FileNotFoundError:
        logger.error("❌ argocd CLI not found")
    except subprocess.CalledProcessError as e:
        logger.info(
            "❌ Error validating application: %s",
            e,
        )


def _check_component_health(  # pylint: disable=line-too-long
    component: str, description: str, namespace: str, kubectl_path: str
) -> tuple[str, str]:
    """Check health of a single ArgoCD component."""
    try:
        result = subprocess.run(
            [
                kubectl_path,
                "get",
                "deployment",
                component,
                "-n",
                namespace,
                "-o",
                "jsonpath={.status.readyReplicas}/{.status.replicas}",
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        status = result.stdout.strip()
        if "/" in status:
            ready, total = status.split("/")
            if ready == total and ready != "0":
                return ("✅", f"{description}: {ready}/{total} ready")
            return ("❌", f"{description}: {ready}/{total} ready")
    except subprocess.CalledProcessError:
        return ("❌", f"{description}: not found")

    return ("❓", f"{description}: status unknown")


def health(namespace: str) -> None:
    """Check ArgoCD system health."""
    kubectl_path = check_cli_availability("kubectl", "kubectl not found")
    if not kubectl_path:
        logger.error("kubectl not found in PATH. Please ensure kubectl is installed.")
        return

    logger.info("Checking ArgoCD system health...")

    # Check ArgoCD components
    components = [
        ("argocd-server", "ArgoCD Server"),
        ("argocd-repo-server", "Repository Server"),
        ("argocd-application-controller", "Application Controller"),
        ("argocd-dex-server", "Dex Server (optional)"),
        ("argocd-redis", "Redis Cache"),
    ]

    health_checks = [
        _check_component_health(comp, desc, namespace, kubectl_path)
        for comp, desc in components
    ]

    # Display results
    logger.info("\nArgoCD Health Check:")
    logger.info("=" * 30)
    for status, message in health_checks:
        logger.info("%s %s", status, message)

    # Check API server connectivity
    try:
        argocd_path = ensure_argocd_available()
    except FileNotFoundError:
        logger.error("❌ argocd CLI not found")
        return

    try:
        subprocess.run([argocd_path, "version", "--client"], capture_output=True, check=True)
        logger.info("✅ ArgoCD API connectivity OK")
    except (FileNotFoundError, subprocess.CalledProcessError):
        logger.error("❌ ArgoCD API connectivity issues")


@debug.command()
@click.argument("app_name")
@click.option("--output", "-o", type=click.Path(), help="Output file for events")
def events(app_name: str, output: str | None) -> None:
    """Show Kubernetes events for an application."""
    # Check if argocd and kubectl CLIs are available
    argocd_path = ensure_argocd_available()

    kubectl_path = check_cli_availability("kubectl", "kubectl not found")
    if not kubectl_path:
        msg = "kubectl not found"
        raise FileNotFoundError(msg)

    try:
        # Get application namespace
        result = subprocess.run(
            [
                argocd_path,
                "app",
                "get",
                app_name,
                "-o",
                "jsonpath={.spec.destination.namespace}",
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        namespace = result.stdout.strip()

        logger.info(
            "Fetching events for application '%s' in namespace '%s'...", app_name, namespace
        )

        # Get events
        cmd = [
            kubectl_path,
            "get",
            "events",
            "-n",
            namespace,
            "--sort-by=.metadata.creationTimestamp",
        ]

        if output:
            # Redirect output to file
            with open(output, "w", encoding="utf-8") as f:
                subprocess.run(cmd, stdout=f, check=True)
            logger.info("✅ Events written to %s", output)
        else:
            # Show in terminal
            subprocess.run(cmd, check=True)

    except FileNotFoundError:
        logger.error("❌ kubectl or argocd CLI not found")
    except subprocess.CalledProcessError as e:
        logger.info(
            "❌ Error getting events: %s",
            e,
        )


def _check_container_images(app_name: str) -> list[tuple[str, str]]:
    """Check if container images referenced in the app exist."""
    issues = []

    # Check if argocd CLI is available
    argocd_path = ensure_argocd_available()

    try:
        # Get application manifests
        result = subprocess.run(
            [argocd_path, "app", "manifests", app_name],
            capture_output=True,
            text=True,
            check=True,
        )

        manifests = yaml.safe_load_all(result.stdout)

        for manifest in manifests:
            if manifest.get("kind") in [
                "Deployment",
                "StatefulSet",
                "DaemonSet",
                "Job",
                "CronJob",
            ]:
                containers = (
                    manifest.get("spec", {})
                    .get("template", {})
                    .get("spec", {})
                    .get("containers", [])
                )
                for container in containers:
                    image = container.get("image", "")
                    # Basic image validation (could be enhanced with actual registry checks)
                    if not image:
                        issues.append(
                            (
                                "❌",
                                f"Container missing image in "
                                f"{manifest.get('metadata', {}).get('name', 'unknown')}",
                            )
                        )
                    elif ":" not in image:
                        issues.append(("⚠️ ", f"Container image without tag: {image}"))

    except (subprocess.CalledProcessError, OSError, ValueError, yaml.YAMLError) as e:
        issues.append(
            ("❌", f"Error checking images: {e}")
        )  # Keep this one as it's returning issues, not raising

    return issues


def _check_secret_references(
    app_name: str, argocd_path: str, kubectl_path: str
) -> list[tuple[str, str]]:
    """Check if secrets referenced in the app exist."""
    issues: list[tuple[str, str]] = []

    # CLI paths are already validated in the calling function

    try:
        app_namespace = _get_app_namespace(argocd_path, app_name)
        secret_refs = _extract_secret_refs_from_manifests(argocd_path, app_name, app_namespace)
        _verify_secrets_exist(kubectl_path, secret_refs, issues)

    except (subprocess.CalledProcessError, OSError, ValueError, yaml.YAMLError) as exc:
        issues.append(("❌", f"Error checking secrets: {exc}"))

    return issues


def _get_app_namespace(argocd_path: str, app_name: str) -> str:
    """Get the namespace for the ArgoCD app."""
    result = subprocess.run(
        [argocd_path, "app", "get", app_name, "-o", "jsonpath={.spec.destination.namespace}"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _extract_secret_refs_from_manifests(  # pylint: disable=line-too-long
    argocd_path: str, app_name: str, app_ns: str
) -> set[tuple[str, str]]:
    """Extract secret references from app manifests."""
    result = subprocess.run(
        [argocd_path, "app", "manifests", app_name], capture_output=True, text=True, check=True
    )
    manifests = yaml.safe_load_all(result.stdout)
    secret_refs = set()

    for manifest in manifests:
        if manifest.get("kind") == "Secret":
            continue

        # Extract spec based on resource type
        spec = manifest.get("spec", {})
        container_spec = spec.get("template", {}).get("spec", spec)

        for container in container_spec.get("containers", []):
            # Check envFrom
            for env_src in container.get("envFrom", []):
                if "secretRef" in env_src:
                    secret_refs.add((env_src["secretRef"]["name"], app_ns))

            # Check env vars
            for env_var in container.get("env", []):
                if "valueFrom" in env_var and "secretKeyRef" in env_var["valueFrom"]:
                    secret_refs.add((env_var["valueFrom"]["secretKeyRef"]["name"], app_ns))

    return secret_refs


def _verify_secrets_exist(  # pylint: disable=line-too-long
    kubectl_path: str, secret_refs: set[tuple[str, str]], issues: list[tuple[str, str]]
) -> None:
    """Verify that referenced secrets exist in the cluster."""
    for secret_name, namespace in secret_refs:
        try:
            subprocess.run(
                [kubectl_path, "get", "secret", secret_name, "-n", namespace],
                capture_output=True,
                check=True,
            )
            issues.append(("✅", f"Secret '{secret_name}' exists in '{namespace}'"))
        except subprocess.CalledProcessError:
            issues.append(("❌", f"Secret '{secret_name}' not found in '{namespace}'"))
