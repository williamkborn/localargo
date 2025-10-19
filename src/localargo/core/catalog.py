"""App catalog schema, loader, and profile overlays for LocalArgo."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Literal, cast

import yaml


@dataclass
class AppSpec:  # pylint: disable=too-many-instance-attributes
    """Declarative app specification loaded from localargo.yaml."""

    name: str
    repo: str
    path: str = "."
    type: Literal["kustomize", "helm"] = "kustomize"
    namespace: str = "default"
    project: str = "default"
    sync_policy: Literal["manual", "auto"] = "manual"
    helm_values: list[str] = field(default_factory=list)
    health_timeout: int = 300
    # Optional: if provided, deployment will be done via `kubectl apply -f` on these files
    # instead of using the ArgoCD CLI to create/update applications.
    manifest_files: list[str] = field(default_factory=list)


@dataclass
class AppState:
    """Observed state of an ArgoCD application."""

    name: str
    namespace: str
    health: Literal["Healthy", "Progressing", "Degraded", "Unknown"]
    sync: Literal["Synced", "OutOfSync", "Unknown"]
    revision: str | None = None


class CatalogError(ValueError):
    """Raised on invalid catalog content."""


def load_catalog(path: str = "localargo.yaml", profile: str | None = None) -> list[AppSpec]:
    """Load app catalog, applying optional profile overlay if present."""
    base: dict[str, Any] = _safe_load_yaml(path)
    specs = _parse_apps(base)
    if profile:
        overlay_path = f"localargo.{profile}.yaml"
        if os.path.exists(overlay_path):
            overlay = _safe_load_yaml(overlay_path)
            specs = _merge_overlays(specs, overlay)
    _validate(specs)
    return specs


def _safe_load_yaml(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            msg = "Top-level YAML must be a mapping"
            raise CatalogError(msg)
        return data


def _parse_apps(data: dict[str, Any]) -> list[AppSpec]:
    apps_val = data.get("apps", [])
    if apps_val is None:
        return []
    if not isinstance(apps_val, list):
        msg = "'apps' must be a list"
        raise CatalogError(msg)
    specs: list[AppSpec] = []
    for idx, raw in enumerate(apps_val):
        specs.append(_build_spec_from_raw(raw, idx))
    return specs


def _merge_overlays(base_specs: list[AppSpec], overlay: dict[str, Any]) -> list[AppSpec]:
    overlays = overlay.get("apps", [])
    if not overlays:
        return base_specs
    if not isinstance(overlays, list):
        msg = "overlay 'apps' must be a list"
        raise CatalogError(msg)
    by_name: dict[str, AppSpec] = {s.name: s for s in base_specs}
    for idx, raw in enumerate(overlays):
        _apply_overlay_to_map(by_name, raw, idx)
    return list(by_name.values())


def _build_spec_from_raw(raw: Any, idx: int) -> AppSpec:
    if not isinstance(raw, dict):
        msg = f"apps[{idx}] must be a mapping"
        raise CatalogError(msg)
    name = _require_str(raw, "name", idx)
    repo = _require_str(raw, "repo", idx)
    path = str(raw.get("path", "."))
    app_type = _parse_app_type(raw, idx)
    namespace = str(raw.get("namespace", "default"))
    project = str(raw.get("project", "default"))
    sync_policy = _parse_sync_policy(raw, idx)
    helm_values = _parse_helm_values(raw, idx)
    health_timeout = _parse_health_timeout(raw)
    manifest_files = _parse_manifest_files(raw)
    return AppSpec(
        name=name,
        repo=repo,
        path=path,
        type=app_type,
        namespace=namespace,
        project=project,
        sync_policy=sync_policy,
        helm_values=[str(v) for v in helm_values],
        health_timeout=health_timeout,
        manifest_files=manifest_files,
    )


def _parse_app_type(raw: dict[str, Any], idx: int) -> Literal["kustomize", "helm"]:
    app_type = raw.get("type", "kustomize")
    if app_type not in ("kustomize", "helm"):
        msg = f"apps[{idx}].type must be 'kustomize' or 'helm'"
        raise CatalogError(msg)
    return cast(Literal["kustomize", "helm"], app_type)


def _parse_sync_policy(raw: dict[str, Any], idx: int) -> Literal["manual", "auto"]:
    policy = raw.get("syncPolicy", "manual")
    if policy not in ("manual", "auto"):
        msg = f"apps[{idx}].syncPolicy must be 'manual' or 'auto'"
        raise CatalogError(msg)
    return cast(Literal["manual", "auto"], policy)


def _parse_helm_values(raw: dict[str, Any], idx: int) -> list[str]:
    helm_values = raw.get("helmValues", []) or []
    if not isinstance(helm_values, list) or not all(
        isinstance(v, str | os.PathLike) for v in helm_values
    ):
        msg = f"apps[{idx}].helmValues must be a list of strings"
        raise CatalogError(msg)
    return [str(v) for v in helm_values]


def _parse_health_timeout(raw: dict[str, Any]) -> int:
    return int(raw.get("healthTimeout", 300))


def _normalize_manifest_files(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list) and all(isinstance(v, str | os.PathLike) for v in value):
        return [str(v) for v in value]
    msg = "manifest files must be a list of strings"
    raise CatalogError(msg)


def _parse_manifest_files(raw: dict[str, Any]) -> list[str]:
    # Support both snake_case and camelCase
    vals = []
    if "manifest_files" in raw and raw["manifest_files"] is not None:
        vals.extend(_normalize_manifest_files(raw["manifest_files"]))
    if "manifestFiles" in raw and raw["manifestFiles"] is not None:
        vals.extend(_normalize_manifest_files(raw["manifestFiles"]))
    return vals


def _apply_overlay_to_map(by_name: dict[str, AppSpec], raw: Any, idx: int) -> None:
    if not isinstance(raw, dict):
        msg = f"overlay apps[{idx}] must be a mapping"
        raise CatalogError(msg)
    name = _require_str(raw, "name", idx)
    base = by_name.get(name)
    if not base:
        merged_list = _parse_apps({"apps": [raw]})
        if merged_list:
            by_name[name] = merged_list[0]
        return
    _apply_overlay_to_spec(base, raw)


def _apply_overlay_to_spec(base: AppSpec, raw: dict[str, Any]) -> None:
    _overlay_repo(base, raw)
    _overlay_path(base, raw)
    _overlay_type(base, raw)
    _overlay_namespace(base, raw)
    _overlay_project(base, raw)
    _overlay_sync_policy(base, raw)
    _overlay_helm_values(base, raw)
    _overlay_health_timeout(base, raw)
    _overlay_manifest_files(base, raw)


def _overlay_repo(base: AppSpec, raw: dict[str, Any]) -> None:
    if "repo" in raw:
        base.repo = str(raw["repo"])


def _overlay_path(base: AppSpec, raw: dict[str, Any]) -> None:
    if "path" in raw:
        base.path = str(raw["path"])


def _overlay_type(base: AppSpec, raw: dict[str, Any]) -> None:
    if "type" in raw:
        if raw["type"] not in ("kustomize", "helm"):
            msg = "overlay type must be 'kustomize' or 'helm'"
            raise CatalogError(msg)
        base.type = cast(Literal["kustomize", "helm"], raw["type"])


def _overlay_namespace(base: AppSpec, raw: dict[str, Any]) -> None:
    if "namespace" in raw:
        base.namespace = str(raw["namespace"])


def _overlay_project(base: AppSpec, raw: dict[str, Any]) -> None:
    if "project" in raw:
        base.project = str(raw["project"])


def _overlay_sync_policy(base: AppSpec, raw: dict[str, Any]) -> None:
    if "syncPolicy" in raw:
        policy = raw["syncPolicy"]
        if policy not in ("manual", "auto"):
            msg = "overlay syncPolicy must be 'manual' or 'auto'"
            raise CatalogError(msg)
        base.sync_policy = cast(Literal["manual", "auto"], policy)


def _overlay_helm_values(base: AppSpec, raw: dict[str, Any]) -> None:
    if "helmValues" in raw:
        base.helm_values = _normalize_overlay_helm_values(raw["helmValues"])


def _overlay_health_timeout(base: AppSpec, raw: dict[str, Any]) -> None:
    if "healthTimeout" in raw:
        base.health_timeout = int(raw["healthTimeout"])


def _overlay_manifest_files(base: AppSpec, raw: dict[str, Any]) -> None:
    # Merge manifest files if present in overlay
    files = []
    if "manifest_files" in raw:
        files.extend(_normalize_manifest_files(raw["manifest_files"]))
    if "manifestFiles" in raw:
        files.extend(_normalize_manifest_files(raw["manifestFiles"]))
    if files:
        base.manifest_files = files


def _normalize_overlay_helm_values(value: Any) -> list[str]:
    hv = value or []
    if not isinstance(hv, list):
        msg = "overlay helmValues must be a list of strings"
        raise CatalogError(msg)
    for v in hv:
        if not isinstance(v, str | os.PathLike):
            msg = "overlay helmValues must be a list of strings"
            raise CatalogError(msg)
    return [str(v) for v in hv]


def _validate(specs: list[AppSpec]) -> None:
    seen: set[str] = set()
    for s in specs:
        if not s.name or not s.repo:
            msg = "Each app requires non-empty 'name' and 'repo'"
            raise CatalogError(msg)
        if s.name in seen:
            msg = f"Duplicate app name: {s.name}"
            raise CatalogError(msg)
        seen.add(s.name)


def _require_str(raw: dict[str, Any], key: str, idx: int) -> str:
    if key not in raw or raw[key] is None or str(raw[key]).strip() == "":
        msg = f"apps[{idx}].{key} is required"
        raise CatalogError(msg)
    return str(raw[key])
