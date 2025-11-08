"""Validate, up, and down commands for up-manifest flows."""
# pylint: disable=duplicate-code

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
from localargo.core.checkers import check_argocd, check_cluster
from localargo.core.execution import STANDARD_UP_STEPS, create_up_execution_engine
from localargo.core.k8s import apply_manifests, ensure_namespace, upsert_secret
from localargo.core.types import StepStatus
from localargo.logging import logger
from localargo.providers.registry import get_provider
from localargo.utils.cli import ensure_core_tools_available
from localargo.utils.proc import ProcessError


def _default_manifest_path(manifest: str | None) -> str:
    if manifest:
        return manifest
    # Prefer ./localargo.yaml in CWD
    default = Path.cwd() / "localargo.yaml"
    return str(default)


@click.command()
@click.option("--manifest", "manifest_path", default=None, help="Path to localargo.yaml")
@click.option("--status", is_flag=True, help="Check and display current status of all steps")
@click.option(
    "--exclude",
    "excluded_apps",
    multiple=True,
    help="Exclude specific apps from validation. Can be used multiple times.",
)
def validate_cmd(
    manifest_path: str | None, *, status: bool, excluded_apps: tuple[str, ...]
) -> None:
    """Validate the manifest and print steps that would be executed."""
    manifest_file = _default_manifest_path(manifest_path)
    ensure_core_tools_available()
    upm = load_up_manifest(manifest_file)

    # Handle excluded apps (don't remove from ArgoCD during validation)
    if excluded_apps:
        upm = _handle_excluded_apps(upm, excluded_apps, remove_from_argocd=False)

    _validate_environment_variables(upm)

    if status:
        _print_current_status(upm)
    else:
        _print_planned_steps(upm)


def _validate_environment_variables(upm: UpManifest) -> None:
    """Validate that all environment variables referenced in secrets exist."""
    for sec in upm.secrets:
        for v in sec.secret_value:
            if v.from_env and v.from_env not in os.environ:
                logger.error("❌ Validation failed: Missing environment variables:")
                logger.error("   - %s.%s <- %s", sec.secret_name, sec.secret_key, v.from_env)
                logger.error("")
                logger.error(
                    "Please set these environment variables before running 'localargo up'"
                )
                msg = "Environment variable validation failed"
                raise click.ClickException(msg)


def _print_current_status(upm: UpManifest) -> None:
    """Check and print the current status of all execution steps."""
    logger.info("Checking current status of all steps...")

    # We'll create the ArgoCD client lazily only when needed
    client = None
    client_available = False

    step_number = 1
    all_completed = True

    for step in STANDARD_UP_STEPS:
        client, client_available = _ensure_client_if_needed(
            step, upm, client, client_available
        )
        step_completed = _check_and_print_step(
            step, upm, client, client_available, step_number
        )
        if not step_completed:
            all_completed = False
        step_number += 1

    _print_completion_message(all_completed)


def _ensure_client_if_needed(
    step: Any,
    upm: UpManifest,
    client: Any,
    client_available: bool,  # noqa: FBT001
) -> tuple[Any, bool]:
    """Ensure ArgoCD client is initialized if step requires it."""
    if step.requires_client and client is None:
        client_available = _try_initialize_argocd_client(upm)
        if client_available:
            client = ArgoClient(namespace="argocd", insecure=True)
    return client, client_available


def _check_and_print_step(
    step: Any,
    upm: UpManifest,
    client: Any,
    client_available: bool,  # noqa: FBT001
    step_number: int,
) -> bool:
    """Check a step and print its status, return True if completed."""
    step_client = client if (step.requires_client and client_available) else None
    status, checked = _check_step_status(step, upm, step_client, client_available)
    _print_step_status(step_number, step, status)
    return checked and status.is_completed


def _try_initialize_argocd_client(upm: UpManifest) -> bool:
    """Try to initialize ArgoCD client by checking dependencies."""
    try:
        cluster_status = check_cluster(upm, None)
        if not cluster_status.is_completed:
            return False

        argocd_status = check_argocd(upm, None)
    except (OSError, ValueError, RuntimeError):
        return False
    return argocd_status.is_completed


def _check_step_status(
    step: Any,
    upm: UpManifest,
    step_client: Any,
    client_available: bool,  # noqa: FBT001
) -> tuple[StepStatus, bool]:
    """Check a step's status, returning (status, was_checked)."""
    # Skip checking client-dependent steps if client isn't available
    if step.requires_client and not client_available:
        status = StepStatus(state="pending", reason="Cannot check (dependencies not ready)")
        return status, False

    try:
        status = step.check(upm, step_client)
    except (OSError, ValueError, RuntimeError) as e:
        logger.warning("Failed to check status of %s: %s", step.name, e)
        # Return a failed status
        status = StepStatus(state="failed", reason=f"Check failed: {e!s}")
        return status, False
    return status, True


def _print_completion_message(all_completed: bool) -> None:  # noqa: FBT001
    """Print the appropriate completion message."""
    if all_completed:
        logger.info("\n✅ All steps are already completed!")
    else:
        logger.info("\n⚠️  Some steps need to be executed. Run 'localargo up' to proceed.")


def _print_step_status(step_number: int, step: Any, status: Any) -> None:
    """Print the status of a single step."""
    if status.state == "completed":
        logger.info("✅ %s) %s - %s", step_number, step.description, status.reason)
    elif status.state == "skipped":
        logger.info("⏭️  %s) %s - %s", step_number, step.description, status.reason)
    else:
        logger.info("⏳ %s) %s - %s", step_number, step.description, status.reason)


def _print_step_error(step_number: int, step: Any, error: str) -> None:
    """Print an error status for a step."""
    logger.info("❌ %s) %s - Error checking status: %s", step_number, step.description, error)


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
@click.option(
    "--force", is_flag=True, help="Force execution of all steps, bypassing state checks"
)
@click.option(
    "--exclude",
    "excluded_apps",
    multiple=True,
    help=(
        "Exclude specific apps from deployment. If already installed, they will be removed from ArgoCD. "
        "Repeatable."
    ),
)
def up_cmd(manifest_path: str | None, *, force: bool, excluded_apps: tuple[str, ...]) -> None:
    """Bring up cluster, configure ArgoCD, apply secrets, deploy apps."""
    manifest_file = _default_manifest_path(manifest_path)
    ensure_core_tools_available()
    upm = load_up_manifest(manifest_file)

    # Handle excluded apps
    if excluded_apps:
        upm = _handle_excluded_apps(upm, excluded_apps)

    # Validate configuration before starting any operations
    _validate_environment_variables(upm)

    # Create execution engine and run steps
    engine = create_up_execution_engine()

    # Execute all steps with state checking (unless force=True)
    # The ArgoCD client will be created lazily when needed
    engine.execute(upm, client=None, force=force)

    # Report final status
    summary = engine.get_status_summary()
    total_steps = len(engine.steps)
    completed = summary["completed"] + summary["skipped"]

    if summary["failed"] > 0:
        msg = "❌ Up failed: %s of %s steps failed"
        logger.error(msg, summary["failed"], total_steps)
        raise click.ClickException(msg % (summary["failed"], total_steps))
    if force:
        logger.info(
            "✅ Up complete: %s of %s steps executed (force mode)", completed, total_steps
        )
    else:
        logger.info("✅ Up complete: %s of %s steps processed", completed, total_steps)


def _handle_excluded_apps(
    upm: UpManifest, excluded_apps: tuple[str, ...], *, remove_from_argocd: bool = True
) -> UpManifest:
    """Handle excluded apps by optionally removing them from ArgoCD and filtering from manifest."""
    if not excluded_apps:
        return upm

    excluded_set = set(excluded_apps)

    # Remove excluded apps from ArgoCD if requested
    if remove_from_argocd:
        _remove_excluded_apps_from_argocd(excluded_set)

    # Filter apps from the manifest
    filtered_apps = [app for app in upm.apps if app.name not in excluded_set]

    logger.info("Excluded %d app(s): %s", len(excluded_apps), ", ".join(excluded_apps))

    # Return new UpManifest with filtered apps
    return UpManifest(
        clusters=upm.clusters,
        apps=filtered_apps,
        repo_creds=upm.repo_creds,
        secrets=upm.secrets,
    )


def _remove_excluded_apps_from_argocd(excluded_apps: set[str]) -> None:
    """Remove excluded apps from ArgoCD if they exist."""
    try:
        client = ArgoClient(namespace="argocd", insecure=True)
        installed_apps = client.get_apps()
        installed_app_names = {app.name for app in installed_apps}

        for app_name in excluded_apps:
            if app_name in installed_app_names:
                logger.info("Removing excluded app '%s' from ArgoCD...", app_name)
                client.delete_app(app_name)
                logger.info("✅ Removed app '%s' from ArgoCD", app_name)
    except Exception as e:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        logger.warning("Could not check/remove excluded apps from ArgoCD: %s", e)
        logger.info("Continuing with app filtering from manifest...")


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
