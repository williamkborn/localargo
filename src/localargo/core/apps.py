"""App orchestration combining catalog, ArgoCD, and Kubernetes helpers."""

# pylint: disable=too-many-arguments

from __future__ import annotations

import time

import click

from localargo.core.argocd import ArgoClient
from localargo.core.catalog import AppSpec, load_catalog
from localargo.core.k8s import apply_manifests, list_pods_for_app, stream_logs
from localargo.eyecandy.progress_steps import StepLogger
from localargo.eyecandy.tables import AppTables
from localargo.logging import logger
from localargo.utils.proc import ProcessError


def _targets(specs: list[AppSpec], app_name: str | None, *, all_: bool) -> list[AppSpec]:
    """Resolve which apps to target given a name or --all flag."""
    if all_:
        return specs
    if not app_name:
        msg = "App name is required unless --all is provided"
        raise ValueError(msg)
    for s in specs:
        if s.name == app_name:
            return [s]
    msg = f"App not found: {app_name}"
    raise ValueError(msg)


def deploy(  # pylint: disable=too-many-locals
    app_name: str | None,
    *,
    all_: bool,
    wait: bool,
    profile: str | None,
    kubeconfig: str | None = None,
    # explicit overrides to create a single ArgoCD app or apply manifests
    manifest_files: list[str] | None = None,
    override_repo: str | None = None,
    override_name: str | None = None,
    override_path: str | None = None,
    override_namespace: str | None = None,
    override_project: str | None = None,
    override_type: str | None = None,
    override_helm_values: list[str] | None = None,
) -> None:
    """Create/update and sync target apps from the catalog.

    If an app spec defines manifest_files, apply them via kubectl; otherwise
    use ArgoCD to create/update and sync the application.
    """
    # Handle direct modes first
    if manifest_files:
        _deploy_manifest_files(manifest_files, kubeconfig)
        return
    if override_repo:
        _deploy_override_app(
            app_name,
            wait=wait,
            override_repo=override_repo,
            override_name=override_name,
            override_path=override_path,
            override_namespace=override_namespace,
            override_project=override_project,
            override_type=override_type,
            override_helm_values=override_helm_values,
        )
        return

    specs = load_catalog(profile=profile)
    targets = _targets(specs, app_name, all_=all_)
    manifest_targets, argocd_targets = _split_targets_by_mode(targets)
    steps = _build_steps(manifest_targets, argocd_targets)

    client = ArgoClient()
    with StepLogger(steps) as log:
        _apply_manifest_targets(manifest_targets, kubeconfig, log)
        _deploy_argocd_targets(argocd_targets, client, wait=wait, log=log)


def _split_targets_by_mode(targets: list[AppSpec]) -> tuple[list[AppSpec], list[AppSpec]]:
    manifest_targets = [s for s in targets if getattr(s, "manifest_files", [])]
    argocd_targets = [s for s in targets if not getattr(s, "manifest_files", [])]
    return manifest_targets, argocd_targets


def _build_steps(manifest_targets: list[AppSpec], argocd_targets: list[AppSpec]) -> list[str]:
    steps: list[str] = [f"Apply manifests for {s.name}" for s in manifest_targets]
    steps += [
        step for s in argocd_targets for step in (f"Create/Update {s.name}", f"Sync {s.name}")
    ]
    return steps


def _apply_manifest_targets(
    manifest_targets: list[AppSpec], kubeconfig: str | None, log: StepLogger
) -> None:
    for s in manifest_targets:
        try:
            apply_manifests(s.manifest_files, kubeconfig=kubeconfig)
            log.step(f"Apply manifests for {s.name}")
        except Exception as e:
            log.step(f"Apply manifests for {s.name}", status="error", error_msg=str(e))
            raise


def _deploy_argocd_targets(
    argocd_targets: list[AppSpec], client: ArgoClient, *, wait: bool, log: StepLogger
) -> None:
    for s in argocd_targets:
        try:
            client.create_or_update_app(s)
            log.step(f"Create/Update {s.name}")
        except Exception as e:
            log.step(f"Create/Update {s.name}", status="error", error_msg=str(e))
            raise
    for s in argocd_targets:
        try:
            client.sync_app(s.name, wait=wait, timeout=s.health_timeout)
            log.step(f"Sync {s.name}")
        except Exception as e:
            log.step(f"Sync {s.name}", status="error", error_msg=str(e))
            raise


def _deploy_manifest_files(files: list[str], kubeconfig: str | None) -> None:
    steps = ["Apply manifests"]
    with StepLogger(steps) as log:
        try:
            apply_manifests(files, kubeconfig=kubeconfig)
            log.step("Apply manifests")
        except Exception as e:  # pragma: no cover - surface error
            log.step("Apply manifests", status="error", error_msg=str(e))
            raise


def _deploy_override_app(
    app_name: str | None,
    *,
    wait: bool,
    override_repo: str,
    override_name: str | None,
    override_path: str | None,
    override_namespace: str | None,
    override_project: str | None,
    override_type: str | None,
    override_helm_values: list[str] | None,
) -> None:
    spec = _build_override_spec(
        app_name,
        override_repo=override_repo,
        override_name=override_name,
        override_path=override_path,
        override_namespace=override_namespace,
        override_project=override_project,
        override_type=override_type,
        override_helm_values=override_helm_values,
    )
    _apply_argocd_deploy(spec, wait=wait)


def _build_override_spec(
    app_name: str | None,
    *,
    override_repo: str,
    override_name: str | None,
    override_path: str | None,
    override_namespace: str | None,
    override_project: str | None,
    override_type: str | None,
    override_helm_values: list[str] | None,
) -> AppSpec:
    name = _coalesce(override_name, app_name, "app")
    path = _coalesce(override_path, ".")
    app_type = _coalesce(override_type, "kustomize")
    namespace = _coalesce(override_namespace, "default")
    project = _coalesce(override_project, "default")
    helm = list(override_helm_values or [])
    return AppSpec(
        name=name,
        repo=override_repo,
        path=path,
        type=app_type,  # type: ignore[arg-type]
        namespace=namespace,
        project=project,
        helm_values=helm,
    )


def _apply_argocd_deploy(spec: AppSpec, *, wait: bool) -> None:
    client = ArgoClient()
    steps = [f"Create/Update {spec.name}", f"Sync {spec.name}"]
    with StepLogger(steps) as log:
        try:
            client.create_or_update_app(spec)
            log.step(f"Create/Update {spec.name}")
            client.sync_app(spec.name, wait=wait, timeout=spec.health_timeout)
            log.step(f"Sync {spec.name}")
        except Exception as e:  # pragma: no cover - bubble up
            log.step(f"Sync {spec.name}", status="error", error_msg=str(e))
            raise


def _coalesce(*values: str | None) -> str:
    for v in values:
        if v is not None and str(v) != "":
            return str(v)
    return ""


def sync(app_name: str | None, *, all_: bool, wait: bool, profile: str | None) -> None:
    """Sync target apps from the catalog (optionally wait)."""
    specs = load_catalog(profile=profile)
    targets = _targets(specs, app_name, all_=all_)
    client = ArgoClient()
    steps = [f"Sync {s.name}" for s in targets]
    with StepLogger(steps) as log:
        for s in targets:
            try:
                client.sync_app(s.name, wait=wait, timeout=s.health_timeout)
                log.step(f"Sync {s.name}")
            except Exception as e:
                log.step(f"Sync {s.name}", status="error", error_msg=str(e))
                raise


def list_apps(profile: str | None) -> None:
    """Render a table of all ArgoCD apps."""
    del profile
    client = ArgoClient()
    try:
        states = client.get_apps()
    except ProcessError as e:
        logger.info(
            "❌ Failed to query apps: %s. Try 'localargo cluster password' to refresh auth.",
            e,
        )
        return
    if not states:
        logger.info("i No applications found. Create apps via 'localargo app deploy <app>'")
        return
    rows = [
        {
            "Name": st.name,
            "Namespace": st.namespace,
            "Health": st.health,
            "Sync": st.sync,
            "Revision": (st.revision or "")[:10],
        }
        for st in states
    ]
    AppTables().render_app_states(rows)


def status(app_name: str | None, *, watch: bool, profile: str | None) -> None:
    """Show app status for one or all apps; supports --watch."""
    del profile
    client = ArgoClient()
    tables = AppTables()

    def render() -> None:
        if app_name:
            st = client.get_app(app_name)
            rows = [
                {
                    "Name": st.name,
                    "Namespace": st.namespace,
                    "Health": st.health,
                    "Sync": st.sync,
                    "Revision": (st.revision or "")[:10],
                }
            ]
        else:
            sts = client.get_apps()
            rows = [
                {
                    "Name": st.name,
                    "Namespace": st.namespace,
                    "Health": st.health,
                    "Sync": st.sync,
                    "Revision": (st.revision or "")[:10],
                }
                for st in sts
            ]
        tables.render_app_states(rows)

    if not watch:
        render()
        return

    try:
        while True:
            render()
            time.sleep(2)
    except KeyboardInterrupt:
        return


def delete(app_name: str, *, profile: str | None) -> None:
    """Delete an app from ArgoCD."""
    del profile
    client = ArgoClient()
    client.delete_app(app_name)


def logs(
    app_name: str,
    *,
    all_pods: bool,
    container: str | None,
    since: str | None,
    follow: bool,
    profile: str | None,
) -> None:  # pylint: disable=too-many-arguments
    """Tail pod logs for an app. Supports multi-pod and follow modes.

    pylint: disable=too-many-arguments
    """
    specs = load_catalog(profile=profile)
    ns = next((s.namespace for s in specs if s.name == app_name), "default")
    pods = list_pods_for_app(app_name, ns)
    target_pods: list[str] = pods if all_pods else pods[:1]
    for pod in target_pods:
        prefix = f"[{pod}/{container or '-'}] "
        for line in stream_logs(pod, ns, container=container, since=since, follow=follow):
            click.echo(f"{prefix}{line}")
