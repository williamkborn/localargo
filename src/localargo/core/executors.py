# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Step executors for idempotent execution framework.

These functions perform the actual installation and configuration work.
They reuse logic from the existing up.py implementation.
"""
# pylint: disable=duplicate-code

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from localargo.core.argocd import ArgoClient, RepoAddOptions
from localargo.core.k8s import apply_manifests, ensure_namespace, upsert_secret
from localargo.logging import logger
from localargo.providers.registry import get_provider
from localargo.utils.proc import ProcessError

if TYPE_CHECKING:
    from localargo.config.manifest import UpManifest


def execute_cluster_creation(  # pylint: disable=unused-argument
    manifest: UpManifest,
    client: ArgoClient | None = None,  # noqa: ARG001
) -> None:
    """Create the Kubernetes cluster."""
    cluster = manifest.clusters[0]
    provider_cls = get_provider(cluster.provider)
    provider = provider_cls(name=cluster.name)
    logger.info("Creating cluster '%s' with provider '%s'...", cluster.name, cluster.provider)
    success = provider.create_cluster(**cluster.kwargs)
    if not success:
        msg = f"Failed to create cluster '{cluster.name}' with provider '{cluster.provider}'"
        raise RuntimeError(msg)


def execute_argocd_installation(  # pylint: disable=unused-argument
    _manifest: UpManifest,
    _client: ArgoClient | None = None,
) -> None:
    """Install ArgoCD (this is handled by the cluster provider during creation)."""
    # ArgoCD installation is actually handled by the cluster provider
    # during cluster creation, so this executor is mostly a no-op.
    # The real work happens in the provider's create_cluster method.
    logger.info("ArgoCD installation is handled by cluster provider")


def execute_nginx_installation(  # pylint: disable=unused-argument
    manifest: UpManifest,  # noqa: ARG001
    client: ArgoClient | None = None,  # noqa: ARG001
) -> None:
    """Install nginx-ingress (this is handled by the cluster provider during creation)."""
    # Nginx ingress installation is handled by the cluster provider
    # during cluster creation, so this executor is mostly a no-op.
    # The real work happens in the provider's create_cluster method.
    logger.info("Nginx ingress installation is handled by cluster provider")


def execute_secrets_creation(  # pylint: disable=unused-argument
    manifest: UpManifest,
    client: ArgoClient | None = None,  # noqa: ARG001
) -> None:
    """Create/update Kubernetes secrets.

    Groups secrets by (namespace, secret_name) to ensure all keys are included
    when multiple manifest entries reference the same secret.
    """
    # Group secrets by (namespace, secret_name)
    secret_groups: dict[tuple[str, str], dict[str, str]] = {}

    for sec in manifest.secrets:
        key = (sec.namespace, sec.secret_name)
        if key not in secret_groups:
            secret_groups[key] = {}

        # Add this key-value to the secret
        for v in sec.secret_value:
            secret_groups[key][sec.secret_key] = os.environ.get(v.from_env, "")

    # Create/update each unique secret with all its keys
    for (namespace, secret_name), env_map in secret_groups.items():
        ensure_namespace(namespace)
        upsert_secret(namespace, secret_name, env_map)
        logger.info(
            "Created/updated secret '%s' in namespace '%s' with %d key(s)",
            secret_name,
            namespace,
            len(env_map),
        )


def execute_repo_creds_setup(manifest: UpManifest, client: ArgoClient | None = None) -> None:
    """Add repository credentials to ArgoCD."""
    if not client:
        msg = "ArgoCD client required for repo credentials setup"
        raise ValueError(msg)

    for rc in manifest.repo_creds:
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


def execute_apps_deployment(manifest: UpManifest, client: ArgoClient | None = None) -> None:
    """Create/update and sync ArgoCD applications."""
    if not client:
        msg = "ArgoCD client required for application deployment"
        raise ValueError(msg)

    for app in manifest.apps:
        # Ensure destination namespace exists prior to ArgoCD applying resources
        if getattr(app, "namespace", None):
            ensure_namespace(app.namespace)

        # If app_file provided, apply Application YAML directly; otherwise use CLI
        if getattr(app, "app_file", None):
            apply_manifests([str(app.app_file)])
            # Rely on Application's sync policy; skip CLI sync to avoid RBAC issues
            logger.info("Applied application manifest for '%s'", app.name)
            continue

        _create_or_update_app(client, app)
        client.sync_app(app.name, wait=True)
        logger.info("Created/updated and synced application '%s'", app.name)


def _create_or_update_app(client: ArgoClient, app: Any) -> None:
    """Create or update an ArgoCD application."""
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
    """Build argocd app create/update command arguments."""
    base = ["argocd", "app", "create" if create else "set", app.name]
    _append_repo_path_classic(base, app)
    _append_destination(base, app)
    _append_revision_and_helm(base, app)
    return base


def _append_repo_path_classic(base: list[str], app: Any) -> None:
    """Append repo and path arguments for classic app creation."""
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
    """Append destination arguments."""
    base.extend(
        [
            "--dest-server",
            "https://kubernetes.default.svc",
            "--dest-namespace",
            getattr(app, "namespace", "default"),
        ]
    )


def _append_revision_and_helm(base: list[str], app: Any) -> None:
    """Append revision and helm arguments."""
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
    """Append helm configuration from source, filtered for chart compatibility."""
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
