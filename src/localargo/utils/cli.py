# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>
#
# SPDX-License-Identifier: MIT
"""CLI validation and execution utilities."""

from __future__ import annotations

import shutil
import subprocess
from typing import Any

from localargo.logging import logger


def check_cli_availability(cli_name: str, error_msg: str | None = None) -> str | None:
    """Check if a CLI tool is available in PATH.

    Args:
        cli_name (str): Name of the CLI tool to check
        error_msg (str | None): Optional error message to raise if CLI not found

    Returns:
        str | None: Path to the CLI executable if found, None otherwise

    Raises:
        FileNotFoundError: If error_msg is provided and CLI is not found
    """
    path = shutil.which(cli_name)
    if not path and error_msg:
        raise FileNotFoundError(error_msg)
    return path


def ensure_argocd_available() -> str:
    """Ensure argocd CLI is available and return its path.

    Returns:
        str: Path to the argocd CLI executable

    Raises:
        FileNotFoundError: If argocd CLI is not found
    """
    argocd_path = check_cli_availability("argocd", "argocd CLI not found")
    if not argocd_path:
        msg = "argocd CLI not found"
        raise FileNotFoundError(msg)
    return argocd_path


def ensure_kubectl_available() -> str:
    """Ensure kubectl CLI is available and return its path.

    Returns:
        str: Path to the kubectl CLI executable

    Raises:
        FileNotFoundError: If kubectl CLI is not found
    """
    kubectl_path = check_cli_availability("kubectl", "kubectl not found")
    if not kubectl_path:
        msg = "kubectl not found"
        raise FileNotFoundError(msg)
    return kubectl_path


def ensure_helm_available() -> str:
    """Ensure helm CLI is available and return its path."""
    path = check_cli_availability("helm", "helm not found")
    if not path:
        msg = "helm not found"
        raise FileNotFoundError(msg)
    return path


def ensure_kind_available() -> str:
    """Ensure kind CLI is available and return its path."""
    path = check_cli_availability("kind", "kind not found")
    if not path:
        msg = "kind not found"
        raise FileNotFoundError(msg)
    return path


def ensure_core_tools_available() -> None:
    """Ensure kubectl, helm, argocd, and kind are available.

    Raises FileNotFoundError if any are missing.
    """
    ensure_kubectl_available()
    ensure_helm_available()
    ensure_argocd_available()
    ensure_kind_available()


def build_kubectl_get_pods_cmd(
    kubectl_path: str, namespace: str, label_selector: str
) -> list[str]:
    """Build kubectl command to get pod names with label selector.

    Args:
        kubectl_path (str): Path to kubectl executable
        namespace (str): Kubernetes namespace
        label_selector (str): Label selector for pods

    Returns:
        list[str]: kubectl command as list of strings
    """
    return [
        kubectl_path,
        "get",
        "pods",
        "-n",
        namespace,
        "-l",
        label_selector,
        "-o",
        "jsonpath={.items[*].metadata.name}",
    ]


def build_kubectl_get_cmd(
    kubectl_path: str,
    resource: str,
    namespace: str,
    label_selector: str | None = None,
    output_format: str | None = None,
    **kwargs: str,
) -> list[str]:
    """Build a generic kubectl get command.

    Args:
        kubectl_path (str): Path to kubectl executable
        resource (str): Kubernetes resource type (e.g., 'pods', 'deployments')
        namespace (str): Kubernetes namespace
        label_selector (str | None): Label selector (optional)
        output_format (str | None): Output format (e.g., 'json', 'yaml', 'custom-columns=...')
        **kwargs (str): Additional kubectl arguments

    Returns:
        list[str]: kubectl command as list of strings
    """
    cmd = [kubectl_path, "get", resource, "-n", namespace]

    if label_selector:
        cmd.extend(["-l", label_selector])

    if output_format:
        cmd.extend(["-o", output_format])

    # Add any additional arguments
    for key, value in kwargs.items():
        cmd.extend([f"--{key}", value])

    return cmd


def build_kubectl_logs_cmd(
    kubectl_path: str, namespace: str, pod_name: str, tail: int | None = None
) -> list[str]:
    """Build kubectl command to get logs from a pod.

    Args:
        kubectl_path (str): Path to kubectl executable
        namespace (str): Kubernetes namespace
        pod_name (str): Name of the pod
        tail (int | None): Number of lines to show from the end (optional)

    Returns:
        list[str]: kubectl command as list of strings
    """
    cmd = [kubectl_path, "logs", "-n", namespace, pod_name]
    if tail is not None:
        cmd.extend(["--tail", str(tail)])
    return cmd


def run_subprocess(
    cmd: list[str],
    *,
    capture_output: bool = True,
    text: bool = True,
    check: bool = True,
    **kwargs: Any,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess command with standardized error handling.

    Args:
        cmd (list[str]): Command to run as a list of strings
        capture_output (bool): Whether to capture stdout/stderr
        text (bool): Whether to decode output as text
        check (bool): Whether to raise CalledProcessError on non-zero exit
        **kwargs (Any): Additional arguments to pass to subprocess.run

    Returns:
        subprocess.CompletedProcess[str]: CompletedProcess instance

    Raises:
        subprocess.CalledProcessError: If check=True and command fails
    """
    # Extract CLI name from command for validation
    if cmd:
        cli_name = cmd[0]
        # Check if it's a common CLI tool that should be validated
        if cli_name in ("kubectl", "argocd", "k3s", "kind", "docker"):
            check_cli_availability(cli_name)

    try:
        return subprocess.run(
            cmd,
            capture_output=capture_output,
            text=text,
            check=check,
            **kwargs,
        )
    except subprocess.CalledProcessError as e:
        logger.debug("Command failed: %s", " ".join(cmd))
        logger.debug("Return code: %s", e.returncode)
        if e.stdout:
            logger.debug("Stdout: %s", e.stdout)
        if e.stderr:
            logger.debug("Stderr: %s", e.stderr)
        raise


def log_subprocess_error(error: subprocess.CalledProcessError) -> None:
    """Log a subprocess error in a standardized format.

    Args:
        error (subprocess.CalledProcessError): The subprocess error to log
    """
    logger.info("❌ Error: %s", error)
