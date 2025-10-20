"""Validate, up, and down commands for up-manifest flows."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import click

from localargo.config.manifest import (
    UpManifest,
    load_up_manifest,
)
from localargo.core.argocd import ArgoClient, RepoAddOptions
from localargo.core.k8s import apply_manifests, ensure_namespace, upsert_secret
from localargo.logging import logger
from localargo.providers.registry import get_provider
from localargo.utils.cli import (
    ensure_core_tools_available,
)
from localargo.utils.proc import ProcessError


def _default_manifest_path(manifest: str | None) -> str:
    if manifest:
        return manifest
    # Prefer ./localargo.yaml in CWD
    default = Path.cwd() / "localargo.yaml"
    return str(default)


@click.command()
@click.option("--manifest", "manifest_path", default=None, help="Path to localargo.yaml")
def validate_cmd(manifest_path: str | None) -> None:
    """Validate the manifest and print steps that would be executed."""
    manifest_file = _default_manifest_path(manifest_path)
    ensure_core_tools_available()
    upm = load_up_manifest(manifest_file)
    _print_planned_steps(upm)


def _print_planned_steps(upm: UpManifest) -> None:
    cluster = upm.clusters[0]
    logger.info("Planned steps:")
    logger.info("1) Create cluster '%s' with provider '%s'", cluster.name, cluster.provider)
    logger.info("2) Login to ArgoCD using initial admin secret")
    _print_secrets_plan(upm)
    _print_repo_creds(upm)
    _print_apps_plan(upm)


def _print_repo_creds(upm: UpManifest) -> None:
    if upm.repo_creds:
        logger.info("4) Add %d repo credential(s):", len(upm.repo_creds))
        for rc in upm.repo_creds:
            kind = getattr(rc, "type", "git")
            oci = " [OCI]" if getattr(rc, "enable_oci", False) else ""
            name = getattr(rc, "name", None)
            if name and kind == "helm":
                logger.info(
                    "   - repo: %s (type: %s%s, name: %s, username: %s)",
                    rc.repo_url,
                    kind,
                    oci,
                    name,
                    rc.username,
                )
            else:
                logger.info(
                    "   - repo: %s (type: %s%s, username: %s)",
                    rc.repo_url,
                    kind,
                    oci,
                    rc.username,
                )
    else:
        logger.info("4) No repo credentials to add")


def _print_secrets_plan(upm: UpManifest) -> None:
    if upm.secrets:
        logger.info("3) Create/Update %d Kubernetes secret(s):", len(upm.secrets))
        for sec in upm.secrets:
            sources = (
                ", ".join([v.from_env for v in sec.secret_value if v.from_env]) or "<empty>"
            )
            logger.info(
                "   - [%s] secret '%s': set key '%s' from env: %s",
                sec.namespace,
                sec.secret_name,
                sec.secret_key,
                sources,
            )
    else:
        logger.info("3) No secrets to create/update")


def _print_apps_plan(upm: UpManifest) -> None:
    if not upm.apps:
        logger.info("5) No applications to deploy")
        return
    logger.info("5) Create/Update and sync %d application(s):", len(upm.apps))
    for app in upm.apps:
        _print_single_app_plan(app)


def _print_single_app_plan(app: Any) -> None:
    logger.info("   - app '%s':", app.name)
    _print_app_namespace(app)
    if getattr(app, "sources", None):
        _print_sources_details(app)
    else:
        _print_single_source_details(app)
    logger.info("     actions: create-or-update, sync --wait")


def _print_app_namespace(app: Any) -> None:
    if getattr(app, "namespace", None):
        logger.info("     namespace: %s", app.namespace)


def _print_sources_details(app: Any) -> None:
    for s in app.sources:
        repo = getattr(s, "repo_url", "")
        rev = getattr(s, "target_revision", "")
        path = getattr(s, "path", None)
        chart = getattr(s, "chart", None)
        if chart:
            logger.info("     source: repo=%s chart=%s revision=%s", repo, chart, rev)
        else:
            logger.info("     source: repo=%s path=%s revision=%s", repo, path or ".", rev)
        _print_helm_details(getattr(s, "helm", None))


def _print_helm_details(helm_cfg: Any | None) -> None:
    if helm_cfg and helm_cfg.value_files:
        logger.info("       helm values: %s", ", ".join(helm_cfg.value_files))
    if helm_cfg and getattr(helm_cfg, "release_name", None):
        logger.info("       helm release: %s", helm_cfg.release_name)


def _print_single_source_details(app: Any) -> None:
    logger.info(
        "     repo=%s path=%s revision=%s", app.repo_url, app.path, app.target_revision
    )


@click.command()
@click.option("--manifest", "manifest_path", default=None, help="Path to localargo.yaml")
def up_cmd(manifest_path: str | None) -> None:
    """Bring up cluster, configure ArgoCD, apply secrets, deploy apps."""
    manifest_file = _default_manifest_path(manifest_path)
    ensure_core_tools_available()
    upm = load_up_manifest(manifest_file)

    _create_cluster(upm)

    # 2) Login to ArgoCD
    client = ArgoClient(namespace="argocd", insecure=True)

    # Apply secrets before configuring repo credentials so apps can pull needed values
    _apply_secrets(upm)

    _add_repo_creds(client, upm)

    _deploy_apps(client, upm)

    logger.info("✅ Up complete")


def _create_cluster(upm: UpManifest) -> None:
    cluster = upm.clusters[0]
    provider_cls = get_provider(cluster.provider)
    provider = provider_cls(name=cluster.name)
    logger.info("Creating cluster '%s' with provider '%s'...", cluster.name, cluster.provider)
    provider.create_cluster(**cluster.kwargs)


def _add_repo_creds(client: ArgoClient, upm: UpManifest) -> None:
    for rc in upm.repo_creds:
        logger.info("Adding repo creds for %s", rc.repo_url)
        client.add_repo_cred(
            repo_url=rc.repo_url,
            username=rc.username,
            password=rc.password,
            options=RepoAddOptions(
                repo_type=getattr(rc, "type", "git"),
                enable_oci=getattr(rc, "enable_oci", False),
                description=getattr(rc, "description", None),
                name=getattr(rc, "name", None),
            ),
        )


def _apply_secrets(upm: UpManifest) -> None:
    for sec in upm.secrets:
        env_map: dict[str, str] = {}
        for v in sec.secret_value:
            env_map[sec.secret_key] = os.environ.get(v.from_env, "")
        ensure_namespace(sec.namespace)
        upsert_secret(sec.namespace, sec.secret_name, env_map)


def _deploy_apps(client: ArgoClient, upm: UpManifest) -> None:
    for app in upm.apps:
        # Ensure destination namespace exists prior to ArgoCD applying resources
        if getattr(app, "namespace", None):
            ensure_namespace(app.namespace)
        # If app_file provided, apply Application YAML directly; otherwise use CLI
        if getattr(app, "app_file", None):
            apply_manifests([str(app.app_file)])
            # Rely on Application's sync policy; skip CLI sync to avoid RBAC issues
            continue
        _create_or_update_app(client, app)
        client.sync_app(app.name, wait=True)


def _create_or_update_app(client: ArgoClient, app: Any) -> None:
    create_args = _build_app_args(app, create=True)
    try:
        client.run_with_auth(create_args)
    except ProcessError:  # update on existence or other benign failures
        update_args = _build_app_args(app, create=False)
        try:
            client.run_with_auth(update_args)
        except ProcessError:
            logger.error(
                "Failed to create or update app '%s'.\nCreate args: %s\nUpdate args: %s",
                app.name,
                " ".join(create_args),
                " ".join(update_args),
            )
            raise


def _build_app_args(app: Any, *, create: bool) -> list[str]:
    base = ["argocd", "app", "create" if create else "set", app.name]
    _append_repo_path_classic(base, app)
    _append_destination(base, app)
    _append_revision_and_helm(base, app)
    return base


def _append_repo_path_classic(base: list[str], app: Any) -> None:
    sources = getattr(app, "sources", None) or []
    # Use first source only; older argocd CLI lacks --source support
    if sources:
        s = sources[0]
        repo = getattr(s, "repo_url", app.repo_url)
        path = getattr(s, "path", app.path)
        chart = getattr(s, "chart", None)
        base.extend(["--repo", repo])
        if chart:
            base.extend(["--helm-chart", chart])
        else:
            base.extend(["--path", path or "."])
        # Merge helm flags from the source into top-level handling
        _append_source_helm_filtered(base, getattr(s, "helm", None), is_chart=bool(chart))
        # Prefer source revision over top-level when provided
        if getattr(s, "target_revision", None):
            # Prefer source-specified revision; _append_revision_and_helm will use this
            app.target_revision = s.target_revision
        return
    base.extend(["--repo", app.repo_url, "--path", app.path])


def _append_destination(base: list[str], app: Any) -> None:
    base.extend(
        [
            "--dest-server",
            "https://kubernetes.default.svc",
            "--dest-namespace",
            getattr(app, "namespace", "default"),
        ]
    )


def _append_revision_and_helm(base: list[str], app: Any) -> None:
    # Ensure single --revision occurrence
    base.extend(["--revision", app.target_revision])
    # If sources exist, we already appended any per-source helm flags; avoid duplicates
    if getattr(app, "sources", None):
        return
    if getattr(app, "helm", None):
        if app.helm.release_name:
            base.extend(["--release-name", app.helm.release_name])
        for v in getattr(app.helm, "value_files", []) or []:
            base.extend(["--values", v])


def _append_source_helm_filtered(base: list[str], hcfg: Any | None, *, is_chart: bool) -> None:
    if hcfg and getattr(hcfg, "release_name", None):
        base.extend(["--release-name", hcfg.release_name])
    if hcfg and getattr(hcfg, "value_files", None):
        for v in _filter_values_for_chart(hcfg.value_files, is_chart=is_chart):
            base.extend(["--values", v])


def _filter_values_for_chart(values: list[str], *, is_chart: bool) -> list[str]:
    """Filter helm values for chart repos to avoid external or env paths."""
    if not is_chart:
        return list(values)
    return [v for v in values if v and "/" not in v and not v.startswith("$")]


def _compose_source_arg(s: Any) -> str:
    # No longer used; kept for reference compatibility with newer argocd CLIs
    parts: list[str] = []
    repo = getattr(s, "repo_url", None)
    path = getattr(s, "path", None)
    chart = getattr(s, "chart", None)
    rev = getattr(s, "target_revision", None)
    ref = getattr(s, "ref", None)
    if repo:
        parts.append(f"repoURL={repo}")
    if path:
        parts.append(f"path={path}")
    if chart:
        parts.append(f"chart={chart}")
    if rev:
        parts.append(f"targetRevision={rev}")
    if ref:
        parts.append(f"ref={ref}")
    return ",".join(parts)


@click.command()
@click.option("--manifest", "manifest_path", default=None, help="Path to localargo.yaml")
def down_cmd(manifest_path: str | None) -> None:
    """Tear down cluster; equivalent to `localargo cluster delete <name>`."""
    manifest_file = _default_manifest_path(manifest_path)
    ensure_core_tools_available()
    upm = load_up_manifest(manifest_file)

    cluster = upm.clusters[0]
    provider_cls = get_provider(cluster.provider)
    provider = provider_cls(name=cluster.name)
    logger.info("Deleting cluster '%s' with provider '%s'...", cluster.name, cluster.provider)
    provider.delete_cluster(cluster.name)
    logger.info("✅ Down complete")
