# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Command-line interface for LocalArgo."""

from __future__ import annotations

import rich_click as click

from localargo.__about__ import __version__
from localargo.cli.commands import app, cluster, debug, port_forward, secrets, sync, template
from localargo.logging import init_cli_logging, logger


@click.group(
    context_settings={"help_option_names": ["-h", "--help"]}, invoke_without_command=True
)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.version_option(version=__version__, prog_name="localargo")
def localargo(*, verbose: bool) -> None:
    """Localargo - Convenient ArgoCD local development tool."""
    # Initialize logging
    init_cli_logging(verbose=verbose)

    ctx = click.get_current_context()
    if ctx is None or ctx.invoked_subcommand is None:
        logger.info("Localargo - Convenient ArgoCD local development tool")
        logger.info("Run 'localargo --help' for available commands.")


# Register subcommands
localargo.add_command(cluster.cluster)
localargo.add_command(app.app)
localargo.add_command(port_forward.port_forward)
localargo.add_command(secrets.secrets)
localargo.add_command(sync.sync_cmd)
localargo.add_command(template.template)
localargo.add_command(debug.debug)
