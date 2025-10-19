"""App orchestration combining catalog, ArgoCD, and Kubernetes helpers."""

# pylint: disable=too-many-arguments

from __future__ import annotations

import itertools
import time

import click

from localargo.core.argocd import ArgoClient
from localargo.core.catalog import AppSpec, load_catalog
from localargo.core.k8s import list_pods_for_app, stream_logs
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


def deploy(app_name: str | None, *, all_: bool, wait: bool, profile: str | None) -> None:
    """Create/update and sync target apps from the catalog."""
    specs = load_catalog(profile=profile)
    targets = _targets(specs, app_name, all_=all_)
    client = ArgoClient()
    steps = list(
        itertools.chain.from_iterable(
            (f"Create/Update {s.name}", f"Sync {s.name}") for s in targets
        )
    )
    with StepLogger(steps) as log:
        for s in targets:
            try:
                client.create_or_update_app(s)
                log.step(f"Create/Update {s.name}")
            except Exception as e:
                log.step(f"Create/Update {s.name}", status="error", error_msg=str(e))
                raise
        for s in targets:
            try:
                client.sync_app(s.name, wait=wait, timeout=s.health_timeout)
                log.step(f"Sync {s.name}")
            except Exception as e:
                log.step(f"Sync {s.name}", status="error", error_msg=str(e))
                raise


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
