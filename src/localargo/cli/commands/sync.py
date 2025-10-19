# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Sync ArgoCD applications and local directories.

This module provides commands for syncing ArgoCD applications with local directories
and watching for changes to automatically sync.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
except ImportError:
    FileSystemEventHandler = None
    Observer = None

import click

from localargo.core.argocd import ArgoClient
from localargo.logging import logger
from localargo.utils.cli import run_subprocess

if TYPE_CHECKING:
    from watchdog.events import FileSystemEvent

# Constants
SYNC_DEBOUNCE_SECONDS = 2


@click.command()
@click.option("--watch", "-w", is_flag=True, help="Watch for changes and auto-sync")
@click.option("--path", "-p", help="Local path to watch (for directory sync)")
@click.option("--app", "-a", help="Specific ArgoCD application to sync")
@click.option("--sync-all", is_flag=True, help="Sync all applications")
@click.option("--force", "-f", is_flag=True, help="Force sync even if no changes")
def sync_cmd(
    *, watch: bool, path: str | None, app: str | None, sync_all: bool, force: bool
) -> None:
    """Sync ArgoCD applications or local directories."""
    if not _validate_sync_arguments(path, app, watch=watch, sync_all=sync_all):
        return

    sync_mode = _determine_sync_mode(path, app, watch=watch, sync_all=sync_all)
    _execute_sync_mode(sync_mode, path, app, force=force)


def _validate_sync_arguments(
    path: str | None, app: str | None, *, watch: bool, sync_all: bool
) -> bool:
    """Validate sync command arguments."""
    if watch and not path and not app:
        logger.error("❌ --watch requires --path or --app")
        return False

    if sync_all and app:
        logger.error("❌ Cannot specify both --sync-all and --app")
        return False

    return True


def _determine_sync_mode(
    path: str | None, app: str | None, *, watch: bool, sync_all: bool
) -> str:
    """Determine which sync mode to use based on arguments."""
    if watch:
        return "watch"
    if sync_all:
        return "sync_all"
    if app:
        return "sync_app"
    if path:
        return "sync_path"
    return "error"


def _execute_sync_mode(
    sync_mode: str,
    path: str | None,
    app: str | None,
    *,
    force: bool,
) -> None:
    """Execute the appropriate sync mode."""
    if sync_mode == "watch":
        _sync_watch(path, app)
    elif sync_mode == "sync_all":
        _sync_all_applications(force=force)
    elif sync_mode == "sync_app":
        _sync_application(app, force=force)  # type: ignore[arg-type]
    elif sync_mode == "sync_path":
        _sync_directory(path)  # type: ignore[arg-type]
    else:
        logger.error("❌ Specify what to sync: --app, --sync-all, or --path")


def _get_application_list() -> list[str]:
    """Get list of all ArgoCD applications."""
    # Ensure we're authenticated before invoking argocd
    ArgoClient()  # constructor auto-logins if needed
    try:
        result = run_subprocess(["argocd", "app", "list", "-o", "name"])
    except subprocess.CalledProcessError as e:
        logger.info(
            "❌ Error listing applications: %s. Try 'localargo cluster password' then re-run.",
            e,
        )
        raise
    names = [app.strip() for app in result.stdout.strip().split("\n") if app.strip()]
    if not names:
        logger.info("i No applications found. Use 'localargo app deploy <app>' to create one.")
    return names


def _sync_multiple_applications(apps: list[str], *, force: bool) -> None:
    """Sync multiple ArgoCD applications."""
    for app in apps:
        _sync_single_application_with_error_handling(app, force=force)


def _sync_single_application_with_error_handling(app_name: str, *, force: bool) -> None:
    """Sync a single application with error handling."""
    try:
        _sync_single_application(app_name, force=force)
        logger.info("✅ '%s' synced", app_name)
    except subprocess.CalledProcessError as e:
        logger.info("❌ Error syncing '%s': %s", app_name, e)


def _sync_single_application(app_name: str, *, force: bool) -> None:
    """Sync a single ArgoCD application."""
    logger.info("Syncing '%s'...", app_name)
    # Ensure authentication prior to syncing
    ArgoClient()
    cmd = ["argocd", "app", "sync", app_name]
    if force:
        cmd.append("--force")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        logger.info(
            "❌ Error syncing '%s': %s. Try re-authenticating (localargo cluster password).",
            app_name,
            e,
        )
        raise


def _sync_application(app_name: str, *, force: bool = False) -> None:
    """Sync a specific ArgoCD application."""
    try:
        logger.info("Syncing application '%s'...", app_name)
        ArgoClient()
        cmd = ["argocd", "app", "sync", app_name]
        if force:
            cmd.append("--force")

        subprocess.run(cmd, check=True)
        logger.info("✅ Application '%s' synced successfully", app_name)

    except FileNotFoundError:
        logger.error("❌ argocd CLI not found")
    except subprocess.CalledProcessError as e:
        logger.info("❌ Error syncing application: %s", e)


def _sync_all_applications(*, force: bool = False) -> None:
    """Sync all ArgoCD applications."""
    try:
        logger.info("Syncing all applications...")
        ArgoClient()
        apps = _get_application_list()
        if not apps:
            logger.info("No applications found")
            return

        logger.info("Found %d applications: %s", len(apps), ", ".join(apps))

        _sync_multiple_applications(apps, force=force)
        logger.info("✅ All applications sync completed")

    except FileNotFoundError:
        logger.error("❌ argocd CLI not found")
    except subprocess.CalledProcessError as e:
        logger.info(
            "❌ Error listing applications: %s. Consider re-authenticating via "
            "'localargo cluster password'",
            e,
        )


def _sync_directory(path: str) -> None:
    """Sync a local directory (placeholder for future GitOps integration)."""
    path_obj = Path(path)

    if not path_obj.exists():
        logger.info("❌ Path does not exist: %s", path)
        return

    if not path_obj.is_dir():
        logger.info("❌ Path is not a directory: %s", path)
        return

    logger.info("Directory sync for '%s' not yet implemented", path)
    logger.info("This would integrate with GitOps workflows in the future")


def _sync_watch(path: str | None = None, app: str | None = None) -> None:
    """Watch for changes and auto-sync."""
    if path:
        _watch_directory(path)
    elif app:
        _watch_application(app)


def _watch_directory(path: str) -> None:
    """Watch a directory for changes and sync."""
    if FileSystemEventHandler is None or Observer is None:
        logger.error(
            "❌ watchdog package required for watching. Install with: pip install watchdog"
        )
        return

    path_obj = Path(path)
    if not path_obj.exists():
        logger.info("❌ Path does not exist: %s", path)
        return

    class ChangeHandler(FileSystemEventHandler):
        """Handler for file system events during directory watching.

        Initializes the change handler with last sync timestamp.
        """

        def __init__(self) -> None:
            self.last_sync = 0.0

        @property
        def is_ready(self) -> bool:
            """Check if handler is ready for sync operations."""
            return time.time() - self.last_sync > SYNC_DEBOUNCE_SECONDS

        def on_any_event(self, event: FileSystemEvent) -> None:
            """Handle file system events."""
            # Debounce syncs
            current_time = time.time()
            if current_time - self.last_sync > SYNC_DEBOUNCE_SECONDS:
                logger.info("📁 Change detected: %s", event.src_path)
                # Here you would trigger a sync
                logger.info("🔄 Auto-sync not yet implemented")
                self.last_sync = current_time

    logger.info("👀 Watching directory: %s", path)
    logger.info("Press Ctrl+C to stop watching")

    observer = Observer()
    observer.schedule(ChangeHandler(), path, recursive=True)
    observer.start()

    try:
        observer.join()
    except KeyboardInterrupt:
        observer.stop()
        logger.info("\n✅ Stopped watching")


def _watch_application(app_name: str) -> None:
    """Watch an ArgoCD application for changes."""
    try:
        logger.info("👀 Watching application: %s", app_name)
        logger.info("Press Ctrl+C to stop watching")

        # Use argocd app wait to watch for changes
        cmd = ["argocd", "app", "wait", app_name, "--watch-only"]

        try:
            subprocess.run(cmd, check=True)
        except KeyboardInterrupt:
            logger.info("\n✅ Stopped watching application '%s'", app_name)

    except FileNotFoundError:
        logger.error("❌ argocd CLI not found")
    except subprocess.CalledProcessError as e:
        logger.info("❌ Error watching application: %s", e)
