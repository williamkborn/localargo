"""Kubernetes helpers for app pod discovery and log streaming."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from localargo.utils.proc import run_json, run_stream

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
