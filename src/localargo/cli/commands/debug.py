# SPDX-FileCopyrightText: 2025-present U.N. Owen <void@some.where>
from __future__ import annotations

import shutil
import subprocess

#
# SPDX-License-Identifier: MIT
import click

from localargo.logging import logger


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
    kubectl_path = shutil.which("kubectl")
    if not kubectl_path:
        msg = "kubectl not found"
        raise FileNotFoundError(msg)

    try:
        logger.info(f"Fetching logs for application '{app_name}'...")

        # Get application pods
        result = subprocess.run(
            [
                kubectl_path,
                "get",
                "pods",
                "-n",
                namespace,
                "-l",
                f"app.kubernetes.io/instance={app_name}",
                "-o",
                "jsonpath={.items[*].metadata.name}",
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        pods = result.stdout.strip().split()

        if not pods:
            logger.info(f"❌ No pods found for application '{app_name}'")
            return

        # Show logs for each pod
        for pod in pods:
            logger.info(f"\n📄 Logs for pod: {pod}")
            logger.info("-" * 50)

            try:
                subprocess.run([kubectl_path, "logs", "-n", namespace, pod, "--tail", str(tail)], check=True)
            except subprocess.CalledProcessError as e:
                logger.info(f"❌ Error getting logs for pod {pod}: {e}")

    except subprocess.CalledProcessError as e:
        logger.info(
            f"❌ Error: {e}",
        )


@debug.command()
@click.argument("app_name")
@click.option("--check-images", is_flag=True, help="Check if container images exist")
@click.option("--check-secrets", is_flag=True, help="Check if referenced secrets exist")
def validate(app_name: str, *, check_images: bool, check_secrets: bool) -> None:
    """Validate ArgoCD application configuration."""
    # Check if argocd and kubectl CLIs are available
    argocd_path = shutil.which("argocd")
    if not argocd_path:
        msg = "argocd CLI not found"
        raise FileNotFoundError(msg)

    kubectl_path = shutil.which("kubectl")
    if not kubectl_path:
        msg = "kubectl not found"
        raise FileNotFoundError(msg)

    try:
        logger.info(f"Validating application '{app_name}'...")

        # Get application details
        result = subprocess.run([argocd_path, "app", "get", app_name], capture_output=True, text=True, check=True)

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
            secret_issues = _check_secret_references(app_name)
            checks.extend(secret_issues)

        # Display results
        logger.info("\nValidation Results:")
        logger.info("=" * 30)
        for status, message in checks:
            logger.info(f"{status} {message}")

    except FileNotFoundError:
        logger.error("❌ argocd CLI not found")
    except subprocess.CalledProcessError as e:
        logger.info(
            f"❌ Error validating application: {e}",
        )


@debug.command()
@click.option("--namespace", "-n", default="argocd", help="ArgoCD namespace")
def health(namespace: str) -> None:
    """Check ArgoCD system health."""
    try:
        logger.info("Checking ArgoCD system health...")

        # Check ArgoCD components
        components = [
            ("argocd-server", "ArgoCD Server"),
            ("argocd-repo-server", "Repository Server"),
            ("argocd-application-controller", "Application Controller"),
            ("argocd-dex-server", "Dex Server (optional)"),
            ("argocd-redis", "Redis Cache"),
        ]

        health_checks = []

        for component, description in components:
            try:
                kubectl_path = shutil.which("kubectl")  # Redefine for scoping
                if kubectl_path is None:
                    msg = "kubectl not found in PATH. Please ensure kubectl is installed and available."
                    raise RuntimeError(msg)
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
                        health_checks.append(("✅", f"{description}: {ready}/{total} ready"))
                    else:
                        health_checks.append(("❌", f"{description}: {ready}/{total} ready"))
                else:
                    health_checks.append(("❓", f"{description}: status unknown"))

            except subprocess.CalledProcessError:
                health_checks.append(("❌", f"{description}: not found"))

        # Display results
        logger.info("\nArgoCD Health Check:")
        logger.info("=" * 30)
        for status, message in health_checks:
            logger.info(f"{status} {message}")

        # Check API server connectivity
        try:
            argocd_path = shutil.which("argocd")  # Redefine for scoping
            if argocd_path is None:
                msg = "argocd not found in PATH. Please ensure argocd CLI is installed and available."
                raise RuntimeError(msg)
            subprocess.run([argocd_path, "version", "--client"], capture_output=True, check=True)
            logger.info("✅ ArgoCD API connectivity OK")
        except (FileNotFoundError, subprocess.CalledProcessError):
            logger.error("❌ ArgoCD API connectivity issues")

    except (subprocess.CalledProcessError, OSError, ValueError) as e:
        logger.info(
            f"❌ Error checking health: {e}",
        )


@debug.command()
@click.argument("app_name")
@click.option("--output", "-o", type=click.Path(), help="Output file for events")
def events(app_name: str, output: str | None) -> None:
    """Show Kubernetes events for an application."""
    # Check if argocd and kubectl CLIs are available
    argocd_path = shutil.which("argocd")
    if not argocd_path:
        msg = "argocd CLI not found"
        raise FileNotFoundError(msg)

    kubectl_path = shutil.which("kubectl")
    if not kubectl_path:
        msg = "kubectl not found"
        raise FileNotFoundError(msg)

    try:
        # Get application namespace
        result = subprocess.run(
            [argocd_path, "app", "get", app_name, "-o", "jsonpath={.spec.destination.namespace}"],
            capture_output=True,
            text=True,
            check=True,
        )

        namespace = result.stdout.strip()

        logger.info(f"Fetching events for application '{app_name}' in namespace '{namespace}'...")

        # Get events
        cmd = [kubectl_path, "get", "events", "-n", namespace, "--sort-by=.metadata.creationTimestamp"]

        if output:
            # Redirect output to file
            with open(output, "w") as f:
                subprocess.run(cmd, stdout=f, check=True)
            logger.info(f"✅ Events written to {output}")
        else:
            # Show in terminal
            subprocess.run(cmd, check=True)

    except FileNotFoundError:
        logger.error("❌ kubectl or argocd CLI not found")
    except subprocess.CalledProcessError as e:
        logger.info(
            f"❌ Error getting events: {e}",
        )


def _check_container_images(app_name: str) -> list[tuple[str, str]]:
    """Check if container images referenced in the app exist."""
    issues = []

    # Check if argocd CLI is available
    argocd_path = shutil.which("argocd")
    if not argocd_path:
        msg = "argocd CLI not found"
        raise FileNotFoundError(msg)

    try:
        # Get application manifests
        result = subprocess.run([argocd_path, "app", "manifests", app_name], capture_output=True, text=True, check=True)

        import yaml

        manifests = yaml.safe_load_all(result.stdout)

        for manifest in manifests:
            if manifest.get("kind") in ["Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob"]:
                containers = manifest.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
                for container in containers:
                    image = container.get("image", "")
                    # Basic image validation (could be enhanced with actual registry checks)
                    if not image:
                        issues.append(("❌", f"Container missing image in {manifest.get('metadata', {}).get('name')}"))
                    elif ":" not in image:
                        issues.append(("⚠️ ", f"Container image without tag: {image}"))

    except (subprocess.CalledProcessError, OSError, ValueError, yaml.YAMLError) as e:
        issues.append(("❌", f"Error checking images: {e}"))

    return issues


def _check_secret_references(app_name: str) -> list[tuple[str, str]]:
    """Check if secrets referenced in the app exist."""
    issues = []

    # Check if argocd and kubectl CLIs are available
    argocd_path = shutil.which("argocd")
    if not argocd_path:
        msg = "argocd CLI not found"
        raise FileNotFoundError(msg)

    kubectl_path = shutil.which("kubectl")
    if not kubectl_path:
        msg = "kubectl not found"
        raise FileNotFoundError(msg)

    try:
        # Get application destination namespace
        result = subprocess.run(
            [argocd_path, "app", "get", app_name, "-o", "jsonpath={.spec.destination.namespace}"],
            capture_output=True,
            text=True,
            check=True,
        )

        namespace = result.stdout.strip()

        # Get application manifests
        result = subprocess.run([argocd_path, "app", "manifests", app_name], capture_output=True, text=True, check=True)

        import yaml

        manifests = yaml.safe_load_all(result.stdout)

        referenced_secrets = set()

        for manifest in manifests:
            # Check for secret references in various places
            if manifest.get("kind") == "Secret":
                continue  # Skip secret definitions themselves

            # Check envFrom
            spec = manifest.get("spec", {})
            template_spec = spec.get("template", {}).get("spec", {}) if "template" in spec else spec

            for container in template_spec.get("containers", []):
                # Check envFrom for secret refs
                for env_from in container.get("envFrom", []):
                    if "secretRef" in env_from:
                        referenced_secrets.add((env_from["secretRef"]["name"], namespace))

                # Check individual env vars
                for env in container.get("env", []):
                    if "valueFrom" in env and "secretKeyRef" in env["valueFrom"]:
                        referenced_secrets.add((env["valueFrom"]["secretKeyRef"]["name"], namespace))

        # Check if referenced secrets exist
        for secret_name, secret_ns in referenced_secrets:
            try:
                subprocess.run(
                    [kubectl_path, "get", "secret", secret_name, "-n", secret_ns], capture_output=True, check=True
                )
                issues.append(("✅", f"Secret '{secret_name}' exists in '{secret_ns}'"))
            except subprocess.CalledProcessError:
                issues.append(("❌", f"Secret '{secret_name}' not found in '{secret_ns}'"))

    except (subprocess.CalledProcessError, OSError, ValueError, yaml.YAMLError) as e:
        issues.append(("❌", f"Error checking secrets: {e}"))

    return issues
