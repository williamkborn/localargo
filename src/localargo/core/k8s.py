"""Kubernetes helpers for app pod discovery, log streaming, and manifest apply."""

from __future__ import annotations

import shutil
import subprocess as sp
from pathlib import Path
from typing import TYPE_CHECKING, Any

from localargo.logging import logger
from localargo.utils.cli import run_subprocess
from localargo.utils.proc import run_json, run_stream


def _kubeconfig_args(kubeconfig: str | None) -> list[str]:
    if not kubeconfig:
        return []
    # Allow both file paths and directories (ignore directories gracefully)
    path = Path(kubeconfig)
    if path.exists() and path.is_file():
        return ["--kubeconfig", str(path)]
    return ["--kubeconfig", str(path)]


def apply_manifests(files: list[str], *, kubeconfig: str | None = None) -> None:
    """Apply one or more manifest files using kubectl apply -f.

    Args:
        files (list[str]): List of file paths (YAML files or directories). Each
            will be passed to kubectl via repeated -f flags.
        kubeconfig (str | None): Optional kubeconfig file path. When provided,
            it's passed to kubectl via --kubeconfig.
    """
    if not files:
        return
    args: list[str] = ["kubectl", *(_kubeconfig_args(kubeconfig)), "apply"]
    for f in files:
        args.extend(["-f", f])
    logger.info("Applying manifests: %s", ", ".join(files))
    run_subprocess(args)


def ensure_namespace(namespace: str) -> None:
    """Create namespace if it does not exist."""
    args = ["kubectl", "get", "ns", namespace, "-o", "name"]
    result = run_subprocess(args, check=False)
    if result.returncode != 0:
        run_subprocess(["kubectl", "create", "ns", namespace])


def upsert_secret(namespace: str, secret_name: str, data: dict[str, str]) -> None:
    """Create or update a generic secret with provided key/value pairs.

    Values are passed from environment; empty values are allowed and result in empty strings.
    """
    ensure_namespace(namespace)
    # Try create
    base = ["kubectl", "-n", namespace, "create", "secret", "generic", secret_name]
    for k, v in data.items():
        base.extend(["--from-literal", f"{k}={v}"])
    create_result = run_subprocess(base, check=False)
    if create_result.returncode == 0:
        return

    # Fallback to kubectl create secret generic --dry-run=client -o yaml | kubectl apply -f -
    kubectl_path = shutil.which("kubectl")
    if not kubectl_path:
        msg = "kubectl not found"
        raise FileNotFoundError(msg)
    dry = [
        kubectl_path,
        "-n",
        namespace,
        "create",
        "secret",
        "generic",
        secret_name,
        "--dry-run=client",
        "-o",
        "yaml",
    ]
    for k, v in data.items():
        dry.extend(["--from-literal", f"{k}={v}"])
    # Pipe into apply using captured output for safer resource handling
    dry_result = sp.run(dry, check=True, capture_output=True)
    sp.run([kubectl_path, "apply", "-f", "-"], check=True, input=dry_result.stdout)


if TYPE_CHECKING:  # imported only for type checking
    from collections.abc import Iterator


def list_pods_for_app(app: str, namespace: str) -> list[str]:
    """List pods associated with an app using common label conventions."""
    obj = run_json(["kubectl", "get", "pods", "-n", namespace, "-o", "json"])
    items = obj.get("items", []) if isinstance(obj, dict) else []
    pods: list[str] = []
    for item in items:
        matched = _extract_pod_name_if_matches(item, app)
        if matched:
            pods.append(matched)
    return pods


def _matches_app(labels: dict[str, Any], app: str) -> bool:
    values = [
        labels.get("app.kubernetes.io/instance"),
        labels.get("app.kubernetes.io/name"),
        labels.get("app"),
        labels.get("argo-app"),
    ]
    return any(isinstance(v, str) and v == app for v in values)


def _extract_pod_name_if_matches(item: Any, app: str) -> str | None:
    meta = item.get("metadata", {}) if isinstance(item, dict) else {}
    name = meta.get("name")
    labels = meta.get("labels", {}) or {}
    if isinstance(labels, dict) and _matches_app(labels, app) and isinstance(name, str):
        return name
    return None


def stream_logs(
    pod: str,
    namespace: str,
    *,
    container: str | None = None,
    since: str | None = None,
    follow: bool = True,
) -> Iterator[str]:
    """Stream logs from a pod, yielding lines as strings."""
    args = ["kubectl", "logs", pod, "-n", namespace]
    if container:
        args.extend(["-c", container])
    if since:
        args.extend(["--since", since])
    if follow:
        args.append("-f")
    return run_stream(args)
