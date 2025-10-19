# SPDX-FileCopyrightText: 2025-present U.N. Owen <void@some.where>
from __future__ import annotations

#
# SPDX-License-Identifier: MIT
import shutil
import subprocess

import click

from localargo.logging import logger


@click.group()
def app() -> None:
    """Manage ArgoCD applications."""


@app.command()
@click.argument("name")
@click.option("--repo", "-r", required=True, help="Git repository URL")
@click.option("--path", "-p", default=".", help="Path within repository")
@click.option("--dest-server", default="https://kubernetes.default.svc", help="Destination server")
@click.option("--dest-namespace", default="default", help="Destination namespace")
@click.option("--project", default="default", help="ArgoCD project")
@click.option("--create-namespace", is_flag=True, help="Create namespace if it doesn't exist")
def create(
    name: str, repo: str, path: str, dest_server: str, dest_namespace: str, project: str, *, create_namespace: bool
) -> None:
    """Create a new ArgoCD application."""
    # Check if argocd CLI is available
    argocd_path = shutil.which("argocd")
    if not argocd_path:
        msg = "argocd CLI not found"
        raise FileNotFoundError(msg)

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
        logger.info(f"✅ Application '{name}' created successfully")

        # Optionally sync immediately
        if click.confirm("Would you like to sync the application now?"):
            subprocess.run([argocd_path, "app", "sync", name], check=True)
            logger.info(f"✅ Application '{name}' synced")

    except FileNotFoundError:
        logger.error(
            "❌ argocd CLI not found. Install from: https://argo-cd.readthedocs.io/en/stable/cli_installation/"
        )
    except subprocess.CalledProcessError as e:
        logger.info(
            f"❌ Error creating application: {e}",
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
        logger.info(f"✅ Application '{name}' sync completed")

    except FileNotFoundError:
        logger.error("❌ argocd CLI not found")
    except subprocess.CalledProcessError as e:
        logger.info(
            f"❌ Error syncing application: {e}",
        )


@app.command()
@click.argument("name", required=False)
def status(name: str | None) -> None:
    """Show application status."""
    # Check if argocd CLI is available
    argocd_path = shutil.which("argocd")
    if not argocd_path:
        msg = "argocd CLI not found"
        raise FileNotFoundError(msg)

    try:
        if name:
            # Show specific app status
            result = subprocess.run([argocd_path, "app", "get", name], capture_output=True, text=True, check=True)
            logger.info(result.stdout)
        else:
            # Show all apps
            result = subprocess.run([argocd_path, "app", "list"], capture_output=True, text=True, check=True)
            logger.info(result.stdout)

    except FileNotFoundError:
        logger.error("❌ argocd CLI not found")
    except subprocess.CalledProcessError as e:
        logger.info(
            f"❌ Error getting status: {e}",
        )


@app.command()
@click.argument("name")
def delete(name: str) -> None:
    """Delete an ArgoCD application."""
    # Check if argocd CLI is available
    argocd_path = shutil.which("argocd")
    if not argocd_path:
        msg = "argocd CLI not found"
        raise FileNotFoundError(msg)

    if click.confirm(f"Are you sure you want to delete application '{name}'?"):
        try:
            subprocess.run([argocd_path, "app", "delete", name], check=True)
            logger.info(f"✅ Application '{name}' deleted")
        except FileNotFoundError:
            logger.error("❌ argocd CLI not found")
        except subprocess.CalledProcessError as e:
            logger.info(
                f"❌ Error deleting application: {e}",
            )


@app.command()
@click.argument("name")
@click.option("--local", "-l", type=click.Path(exists=True), help="Local directory to diff against")
def diff(name: str, local: str | None) -> None:
    """Show diff between desired and live state."""
    # Check if argocd CLI is available
    argocd_path = shutil.which("argocd")
    if not argocd_path:
        msg = "argocd CLI not found"
        raise FileNotFoundError(msg)

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
            f"❌ Error showing diff: {e}",
        )


@app.command()
@click.argument("name")
def logs(name: str) -> None:
    """Show application logs."""
    # Check if argocd CLI is available
    argocd_path = shutil.which("argocd")
    if not argocd_path:
        msg = "argocd CLI not found"
        raise FileNotFoundError(msg)

    try:
        subprocess.run([argocd_path, "app", "logs", name], check=True)
    except FileNotFoundError:
        logger.error("❌ argocd CLI not found")
    except subprocess.CalledProcessError as e:
        logger.info(
            f"❌ Error showing logs: {e}",
        )
