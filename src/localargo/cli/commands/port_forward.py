# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Port forwarding management for ArgoCD applications.

This module provides commands for managing port forwarding to services
in ArgoCD applications and Kubernetes clusters.
"""

from __future__ import annotations

import shutil
import subprocess

import click

from localargo.logging import logger
from localargo.utils.cli import (
    check_cli_availability,
    run_subprocess,
)


@click.group()
def port_forward() -> None:
    """Manage port forwarding for ArgoCD applications."""


@port_forward.command()
@click.argument("service")
@click.option("--namespace", "-n", help="Service namespace")
@click.option(
    "--local-port", "-l", type=int, help="Local port (auto-assigned if not specified)"
)
@click.option(
    "--remote-port", "-r", type=int, help="Remote port (auto-detected if not specified)"
)
@click.option("--argocd-namespace", default="argocd", help="ArgoCD namespace")
def start(
    service: str,
    namespace: str | None,
    local_port: int | None,
    remote_port: int | None,
    argocd_namespace: str,
) -> None:
    """Start port forwarding for a service."""
    try:
        # Auto-detect namespace if not provided
        if not namespace:
            namespace = _detect_app_namespace(service, argocd_namespace)

        # Auto-detect ports if not provided
        if not remote_port:
            remote_port = _detect_service_port(service, namespace)

        if not local_port:
            local_port = remote_port

        logger.info(
            "Starting port forward: %s:%s/%s:%s", local_port, namespace, service, remote_port
        )

        # Start port forwarding
        cmd = [
            "kubectl",
            "port-forward",
            "-n",
            namespace,
            f"svc/{service}",
            f"{local_port}:{remote_port}",
        ]

        logger.info("🔗 Port forward active: http://localhost:%s", local_port)
        logger.info("Press Ctrl+C to stop...")

        try:
            subprocess.run(cmd, check=True)
        except KeyboardInterrupt:
            logger.info("\n✅ Port forward stopped")

    except subprocess.CalledProcessError as e:
        logger.error("❌ Starting port forward failed with return code %s", e.returncode)
        if e.stderr:
            logger.error("Error details: %s", e.stderr.strip())
        raise
    except (OSError, ValueError) as e:
        logger.error("❌ Error starting port forward: %s", e)
        raise


@port_forward.command()
@click.argument("app_name")
def app(app_name: str) -> None:
    """Port forward all services in an ArgoCD application."""
    try:
        # Get application details
        # Note: JSON parsing for service auto-detection is not yet implemented
        logger.info("Port forwarding services for app '%s'...", app_name)
        logger.info("⚠️  Auto-detection of app services not yet implemented")
        logger.info("Use 'localargo port-forward start <service>' for individual services")

    except FileNotFoundError:
        logger.error("❌ argocd CLI not found")
    except subprocess.CalledProcessError as e:
        logger.info(
            "❌ Error: %s",
            e,
        )


@port_forward.command()
def list_forwards() -> None:
    """List active port forwards."""
    try:
        # Find kubectl port-forward processes
        pgrep_path = shutil.which("pgrep")
        if pgrep_path is None:
            msg = "pgrep not found in PATH. Please ensure pgrep is installed and available."
            raise RuntimeError(msg)
        result = subprocess.run(
            [pgrep_path, "-f", "kubectl port-forward"],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode == 0 and result.stdout.strip():
            pids = result.stdout.strip().split("\n")
            logger.info("Active port forwards (%s):", len(pids))
            for pid in pids:
                try:
                    # Get process details
                    ps_path = shutil.which("ps")
                    if ps_path is None:
                        msg = "ps not found in PATH. Please ensure ps is installed and available."
                        raise RuntimeError(msg)
                    ps_result = subprocess.run(
                        [ps_path, "-p", pid, "-o", "pid,ppid,cmd"],
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                    logger.info(ps_result.stdout.strip())
                except subprocess.CalledProcessError:
                    pass
        else:
            logger.info("No active port forwards found")

    except FileNotFoundError:
        logger.error("❌ pgrep not available")


@port_forward.command()
@click.option("--all-forwards", "-a", is_flag=True, help="Stop all port forwards")
def stop(*, all_forwards: bool) -> None:
    """Stop port forwarding processes."""
    try:
        if all_forwards:
            # Kill all kubectl port-forward processes
            pkill_path = shutil.which("pkill")
            if pkill_path is None:
                msg = (
                    "pkill not found in PATH. Please ensure pkill is installed and available."
                )
                raise RuntimeError(msg)
            result = subprocess.run(
                [pkill_path, "-f", "kubectl port-forward"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                logger.info("✅ All port forwards stopped")
            else:
                logger.info("No active port forwards to stop")
        else:
            logger.info("Use --all-forwards to stop all port forwards")

    except FileNotFoundError:
        logger.error("❌ pkill not available")


def _detect_app_namespace(service_name: str, _argocd_namespace: str) -> str:
    """Try to detect the namespace for a service based on ArgoCD apps."""
    try:
        # Get all applications
        result = run_subprocess(["argocd", "app", "list", "-o", "name"])
    except FileNotFoundError:
        return "default"

    apps = result.stdout.strip().split("\n")

    # For each app, check if it contains the service
    for app_name in apps:
        if not app_name.strip():
            continue

        app_namespace = _extract_namespace_from_app(app_name, service_name)
        if app_namespace:
            return app_namespace

    # Default fallback
    return "default"


def _extract_namespace_from_app(app_name: str, service_name: str) -> str | None:
    """Extract namespace from an ArgoCD app if it contains the service."""
    try:
        # Get app details
        app_result = run_subprocess(["argocd", "app", "get", app_name, "--hard-refresh=false"])
    except subprocess.CalledProcessError:
        return None

    # Look for the service in the output (simplified)
    if service_name not in app_result.stdout:
        return None

    # Extract destination namespace from app
    lines = app_result.stdout.split("\n")
    for line in lines:
        if "Destination:" in line and "namespace:" in line:
            # Parse namespace from line like:
            # "Destination:  https://kubernetes.default.svc (namespace: myapp)"
            return line.split("namespace:")[-1].strip().split(")")[0].strip()

    return None


def _detect_service_port(service_name: str, namespace: str) -> int:
    """Detect the port for a service."""
    try:
        # Get service details
        kubectl_path = check_cli_availability("kubectl")
        if kubectl_path is None:
            msg = (
                "kubectl not found in PATH. Please ensure kubectl is installed and available."
            )
            raise RuntimeError(msg)
        result = subprocess.run(
            [
                kubectl_path,
                "get",
                "svc",
                service_name,
                "-n",
                namespace,
                "-o",
                "jsonpath={.spec.ports[0].port}",
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        port = result.stdout.strip()
        if port:
            return int(port)
    except (subprocess.CalledProcessError, ValueError):
        # Fallback to common ports
        return 80

    # Fallback to common ports
    return 80
