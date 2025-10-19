# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Application management for ArgoCD.

This module provides commands for managing ArgoCD applications.
"""

from __future__ import annotations

import subprocess

import click

from localargo.logging import logger
from localargo.utils.cli import ensure_argocd_available


@click.group()
def app() -> None:
    """Manage ArgoCD applications."""


@app.command()
@click.argument("name")
@click.option("--repo", "-r", required=True, help="Git repository URL")
@click.option("--path", "-p", default=".", help="Path within repository")
@click.option(
    "--dest-server", default="https://kubernetes.default.svc", help="Destination server"
)
@click.option("--dest-namespace", default="default", help="Destination namespace")
@click.option("--project", default="default", help="ArgoCD project")
@click.option("--create-namespace", is_flag=True, help="Create namespace if it doesn't exist")
def create(  # pylint: disable=too-many-arguments
    name: str,
    repo: str,
    *,
    path: str,
    dest_server: str,
    dest_namespace: str,
    project: str,
    create_namespace: bool,
) -> None:
    """Create a new ArgoCD application."""
    # Check if argocd CLI is available
    argocd_path = ensure_argocd_available()

    try:
        subprocess.run([argocd_path, "--version"], capture_output=True, check=True)

        # Create application
        cmd = [
            "argocd",
            "app",
            "create",
            name,
            "--repo",
            repo,
            "--path",
            path,
            "--dest-server",
            dest_server,
            "--dest-namespace",
            dest_namespace,
            "--project",
            project,
        ]

        if create_namespace:
            cmd.extend(["--create-namespace"])

        subprocess.run(cmd, check=True)
        logger.info("✅ Application '%s' created successfully", name)

        # Optionally sync immediately
        if click.confirm("Would you like to sync the application now?"):
            subprocess.run([argocd_path, "app", "sync", name], check=True)
            logger.info("✅ Application '%s' synced", name)

    except FileNotFoundError:
        logger.error(
            "❌ argocd CLI not found. Install from: "
            "https://argo-cd.readthedocs.io/en/stable/cli_installation"
        )
    except subprocess.CalledProcessError as e:
        logger.info(
            "❌ Error creating application: %s",
            e,
        )


@app.command()
@click.argument("name")
@click.option("--watch", "-w", is_flag=True, help="Watch sync status")
def sync(name: str, *, watch: bool) -> None:
    """Sync an ArgoCD application."""
    try:
        cmd = ["argocd", "app", "sync", name]
        if watch:
            cmd.append("--watch")

        subprocess.run(cmd, check=True)
        logger.info("✅ Application '%s' sync completed", name)

    except FileNotFoundError:
        logger.error("❌ argocd CLI not found")
    except subprocess.CalledProcessError as e:
        logger.info(
            "❌ Error syncing application: %s",
            e,
        )


@app.command()
@click.argument("name", required=False)
def status(name: str | None) -> None:
    """Show application status."""
    # Check if argocd CLI is available
    argocd_path = ensure_argocd_available()

    try:
        if name:
            # Show specific app status
            result = subprocess.run(
                [argocd_path, "app", "get", name], capture_output=True, text=True, check=True
            )
            logger.info(result.stdout)
        else:
            # Show all apps
            result = subprocess.run(
                [argocd_path, "app", "list"], capture_output=True, text=True, check=True
            )
            logger.info(result.stdout)

    except FileNotFoundError:
        logger.error("❌ argocd CLI not found")
    except subprocess.CalledProcessError:
        logger.info("❌ Error getting status")


@app.command()
@click.argument("name")
def delete(name: str) -> None:
    """Delete an ArgoCD application."""
    # Check if argocd CLI is available
    argocd_path = ensure_argocd_available()

    if click.confirm(f"Are you sure you want to delete application '{name}'?"):
        try:
            subprocess.run([argocd_path, "app", "delete", name], check=True)
            logger.info("✅ Application '%s' deleted", name)
        except FileNotFoundError:
            logger.error("❌ argocd CLI not found")
        except subprocess.CalledProcessError:
            logger.info("❌ Error deleting application")


@app.command()
@click.argument("name")
@click.option(
    "--local", "-l", type=click.Path(exists=True), help="Local directory to diff against"
)
def diff(name: str, local: str | None) -> None:
    """Show diff between desired and live state."""
    # Check if argocd CLI is available
    argocd_path = ensure_argocd_available()

    try:
        if local:
            # Diff against local directory
            subprocess.run([argocd_path, "app", "diff", name, "--local", local], check=True)
        else:
            # Standard diff
            subprocess.run([argocd_path, "app", "diff", name], check=True)

    except FileNotFoundError:
        logger.error("❌ argocd CLI not found")
    except subprocess.CalledProcessError as e:
        logger.info(
            "❌ Error showing diff: %s",
            e,
        )


@app.command()
@click.argument("name")
def logs(name: str) -> None:
    """Show application logs."""
    # Check if argocd CLI is available
    argocd_path = ensure_argocd_available()

    try:
        subprocess.run([argocd_path, "app", "logs", name], check=True)
    except FileNotFoundError:
        logger.error("❌ argocd CLI not found")
    except subprocess.CalledProcessError as e:
        logger.info(
            "❌ Error showing logs: %s",
            e,
        )
