# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Debugging and troubleshooting tools for ArgoCD.

This module provides commands for debugging and troubleshooting ArgoCD applications
and Kubernetes clusters.
"""

from __future__ import annotations

import subprocess
from typing import Any

import click
import yaml

from localargo.logging import logger
from localargo.utils.cli import (
    build_kubectl_get_pods_cmd,
    build_kubectl_logs_cmd,
    check_cli_availability,
    ensure_argocd_available,
    ensure_kubectl_available,
    log_subprocess_error,
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
        log_subprocess_error(e)


@debug.command()
@click.argument("app_name")
@click.option("--check-images", is_flag=True, help="Check if container images exist")
@click.option("--check-secrets", is_flag=True, help="Check if referenced secrets exist")
def validate(app_name: str, *, check_images: bool, check_secrets: bool) -> None:
    """Validate ArgoCD application configuration."""
    try:
        argocd_path = ensure_argocd_available()
        kubectl_path = ensure_kubectl_available() if check_secrets else None

        logger.info("Validating application '%s'...", app_name)

        app_info = _get_application_info(argocd_path, app_name)
        checks = _perform_basic_validation_checks(app_info)

        if check_images:
            image_issues = _check_container_images(app_name)
            checks.extend(image_issues)

        if check_secrets:
            secret_issues = _check_secret_references(app_name, argocd_path, kubectl_path)
            checks.extend(secret_issues)

        _display_validation_results(checks)

    except FileNotFoundError:
        logger.error("❌ argocd CLI not found")
    except subprocess.CalledProcessError as e:
        logger.error("❌ Error validating application: %s", e)


def _get_application_info(argocd_path: str, app_name: str) -> str:
    """Get application details from ArgoCD."""
    result = subprocess.run(
        [argocd_path, "app", "get", app_name], capture_output=True, text=True, check=True
    )
    return result.stdout


def _perform_basic_validation_checks(app_info: str) -> list[tuple[str, str]]:
    """Perform basic validation checks on application info."""
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

    return checks


def _display_validation_results(checks: list[tuple[str, str]]) -> None:
    """Display validation results."""
    logger.info("\nValidation Results:")
    logger.info("=" * 30)
    for status, message in checks:
        logger.info("%s %s", status, message)


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
    issues: list[tuple[str, str]] = []

    # Check if argocd CLI is available
    argocd_path = ensure_argocd_available()

    try:
        manifests = _load_manifests(argocd_path, app_name)
        for manifest in manifests:
            if _is_workload_kind(manifest.get("kind")):
                containers = _get_containers_from_manifest(manifest)
                _collect_image_issues(containers, manifest, issues)
    except (subprocess.CalledProcessError, OSError, ValueError, yaml.YAMLError) as e:
        # Keep this one as it's returning issues, not raising
        issues.append(("❌", f"Error checking images: {e}"))

    return issues


def _load_manifests(argocd_path: str, app_name: str) -> list[dict[str, Any]]:
    """Load manifests for an application via argocd CLI."""
    result = subprocess.run(
        [argocd_path, "app", "manifests", app_name],
        capture_output=True,
        text=True,
        check=True,
    )
    return list(yaml.safe_load_all(result.stdout))


def _is_workload_kind(kind: str | None) -> bool:
    """Return True if kind is a workload that contains containers."""
    return kind in {"Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob"}


def _get_containers_from_manifest(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract containers list from manifest safely."""
    template_spec = _get_template_spec(manifest)
    if template_spec is None:
        return []
    containers = template_spec.get("containers")
    if not isinstance(containers, list):
        return []
    return [c for c in containers if isinstance(c, dict)]


def _get_template_spec(manifest: dict[str, Any]) -> dict[str, Any] | None:
    """Safely navigate to spec.template.spec, returning a dict or None."""
    spec = manifest.get("spec")
    if not isinstance(spec, dict):
        return None
    template = spec.get("template")
    if not isinstance(template, dict):
        return None
    template_spec = template.get("spec")
    if not isinstance(template_spec, dict):
        return None
    return template_spec


def _collect_image_issues(
    containers: list[dict[str, Any]],
    manifest: dict[str, Any],
    issues: list[tuple[str, str]],
) -> None:
    """Append image-related issues for given containers to the list."""
    for container in containers:
        image = container.get("image", "")
        if not image:
            name = manifest.get("metadata", {}).get("name", "unknown")
            issues.append(("❌", f"Container missing image in {name}"))
        elif ":" not in image:
            issues.append(("⚠️ ", f"Container image without tag: {image}"))


def _check_secret_references(
    app_name: str, argocd_path: str, kubectl_path: str | None
) -> list[tuple[str, str]]:
    """Check if secrets referenced in the app exist."""
    issues: list[tuple[str, str]] = []

    # CLI paths are already validated in the calling function

    if kubectl_path is None:
        issues.append(("❌", "kubectl path is required for secret checking"))
        return issues

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
    manifests = _get_app_manifests(argocd_path, app_name)
    secret_refs = set()

    for manifest in manifests:
        if manifest.get("kind") == "Secret":
            continue

        container_spec = _get_container_spec(manifest)
        secret_refs.update(_extract_secret_refs_from_containers(container_spec, app_ns))

    return secret_refs


def _get_app_manifests(argocd_path: str, app_name: str) -> list[dict[str, str]]:
    """Get manifests for an ArgoCD application."""
    result = subprocess.run(
        [argocd_path, "app", "manifests", app_name], capture_output=True, text=True, check=True
    )
    return list(yaml.safe_load_all(result.stdout))


def _get_container_spec(manifest: dict[str, Any]) -> dict[str, Any]:
    """Get the container specification from a manifest."""
    spec = manifest.get("spec", {})
    if not isinstance(spec, dict):
        return {}
    template_spec = spec.get("template", {})
    if not isinstance(template_spec, dict):
        return spec
    container_spec = template_spec.get("spec", spec)
    if not isinstance(container_spec, dict):
        return spec
    return container_spec


def _extract_secret_refs_from_containers(
    container_spec: dict[str, Any], namespace: str
) -> set[tuple[str, str]]:
    """Extract secret references from container specifications."""
    secret_refs = set()

    for container in container_spec.get("containers", []):
        secret_refs.update(_extract_secret_refs_from_env_from(container, namespace))
        secret_refs.update(_extract_secret_refs_from_env_vars(container, namespace))

    return secret_refs


def _extract_secret_refs_from_env_from(
    container: dict[str, Any], namespace: str
) -> set[tuple[str, str]]:
    """Extract secret references from envFrom configurations."""
    secret_refs = set()

    for env_src in container.get("envFrom", []):
        if "secretRef" in env_src:
            secret_refs.add((env_src["secretRef"]["name"], namespace))

    return secret_refs


def _extract_secret_refs_from_env_vars(
    container: dict[str, Any], namespace: str
) -> set[tuple[str, str]]:
    """Extract secret references from environment variables."""
    secret_refs = set()

    for env_var in container.get("env", []):
        if "valueFrom" in env_var and "secretKeyRef" in env_var["valueFrom"]:
            secret_refs.add((env_var["valueFrom"]["secretKeyRef"]["name"], namespace))

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
