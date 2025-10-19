# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Application management for ArgoCD.

Thin CLI wrapper delegating to core app orchestration.
"""

# pylint: disable=too-many-arguments

from __future__ import annotations

import click

from localargo.core import apps as core_apps


@click.group()
def app() -> None:
    """Manage ArgoCD applications."""


@app.command("list")
@click.option("--profile", default=None, help="Profile overlay to apply")
def list_cmd(profile: str | None) -> None:
    """List applications from ArgoCD."""
    core_apps.list_apps(profile=profile)


@app.command()
@click.argument("name", required=False)
@click.option("--watch", is_flag=True, help="Watch app status")
@click.option("--profile", default=None, help="Profile overlay to apply")
def status(name: str | None, *, watch: bool, profile: str | None) -> None:
    """Show application status (optionally watch)."""
    core_apps.status(name, watch=watch, profile=profile)


@app.command()
@click.argument("name", required=False)
@click.option("--all", "all_", is_flag=True, help="Target all apps from catalog")
@click.option("--wait/--no-wait", default=True, help="Wait for Healthy after sync")
@click.option("--profile", default=None, help="Profile overlay to apply")
@click.option(
    "--kubeconfig",
    default=None,
    help="Path to kubeconfig for kubectl-based deployments",
)
@click.option(
    "-f",
    "--file",
    "manifest_files",
    multiple=True,
    help="Manifest file or directory to apply (kubectl -f). Repeatable.",
)
@click.option("--repo", default=None, help="Git repo URL for ArgoCD app")
@click.option("--app-name", "app_name_override", default=None, help="ArgoCD application name")
@click.option("--repo-path", default=".", help="Path within repo (default '.')")
@click.option("--namespace", default="default", help="Destination namespace")
@click.option("--project", default="default", help="ArgoCD project")
@click.option(
    "--type",
    "app_type",
    type=click.Choice(["kustomize", "helm"], case_sensitive=False),
    default="kustomize",
    help="Application type",
)
@click.option(
    "--helm-values",
    "helm_values",
    multiple=True,
    help="Additional Helm values files (only for --type helm). Repeatable.",
)
def deploy(
    name: str | None,
    *,
    all_: bool,
    wait: bool,
    profile: str | None,
    kubeconfig: str | None,
    manifest_files: tuple[str, ...],
    repo: str | None,
    app_name_override: str | None,
    repo_path: str,
    namespace: str,
    project: str,
    app_type: str,
    helm_values: tuple[str, ...],
) -> None:
    """Create/update and sync one or all apps using catalog."""
    core_apps.deploy(
        name,
        all_=all_,
        wait=wait,
        profile=profile,
        kubeconfig=kubeconfig,
        manifest_files=list(manifest_files),
        override_repo=repo,
        override_name=app_name_override,
        override_path=repo_path,
        override_namespace=namespace,
        override_project=project,
        override_type=app_type,
        override_helm_values=list(helm_values),
    )


@app.command()
@click.argument("name", required=False)
@click.option("--all", "all_", is_flag=True, help="Target all apps from catalog")
@click.option("--wait/--no-wait", default=True, help="Wait for Healthy after sync")
@click.option("--profile", default=None, help="Profile overlay to apply")
def sync(name: str | None, *, all_: bool, wait: bool, profile: str | None) -> None:
    """Sync one or all apps using catalog."""
    core_apps.sync(name, all_=all_, wait=wait, profile=profile)


@app.command()
@click.argument("name")
@click.option("--all-pods", is_flag=True, help="Tail all pods for the app")
@click.option("--container", default=None, help="Container name to select")
@click.option("--since", default=None, help="Only return logs newer than a relative time")
@click.option("--follow/--no-follow", default=True, help="Follow log output")
@click.option("--profile", default=None, help="Profile overlay to apply")
def logs(
    name: str,
    *,
    all_pods: bool,
    container: str | None,
    since: str | None,
    follow: bool,
    profile: str | None,
) -> None:  # pylint: disable=too-many-arguments
    """Tail logs for the selected app."""
    core_apps.logs(
        name,
        all_pods=all_pods,
        container=container,
        since=since,
        follow=follow,
        profile=profile,
    )


@app.command()
@click.argument("name")
@click.option("--profile", default=None, help="Profile overlay to apply")
def delete(name: str, *, profile: str | None) -> None:
    """Delete an application from ArgoCD."""
    core_apps.delete(name, profile=profile)
