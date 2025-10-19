# SPDX-FileCopyrightText: 2025-present U.N. Owen <void@some.where>
#
# SPDX-License-Identifier: MIT
from __future__ import annotations

import logging
import os

from rich.console import Console
from rich.logging import RichHandler

"""Logging configuration with rich handler for localargo."""


def setup_logging(
    level: str = "INFO",
    *,
    show_time: bool = True,
    show_path: bool = False,
    rich_tracebacks: bool = True,
) -> logging.Logger:
    """Set up logging with rich handler.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        show_time: Whether to show timestamps
        show_path: Whether to show file paths
        rich_tracebacks: Whether to use rich tracebacks

    Returns:
        Configured logger instance
    """
    # Create console for rich output
    console = Console(stderr=True)

    # Configure rich handler
    rich_handler = RichHandler(
        console=console,
        show_time=show_time,
        show_path=show_path,
        enable_link_path=False,
        markup=True,
        rich_tracebacks=rich_tracebacks,
        tracebacks_show_locals=False,
    )

    # Set log level
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    rich_handler.setLevel(numeric_level)

    # Configure root logger
    logging.basicConfig(
        level=numeric_level,
        format="%(message)s",  # Rich handler handles formatting
        handlers=[rich_handler],
        force=True,  # Override any existing configuration
    )

    # Create and return logger
    logger = logging.getLogger("localargo")
    logger.setLevel(numeric_level)

    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """Get a logger instance.

    Args:
        name: Logger name (defaults to 'localargo')

    Returns:
        Logger instance
    """
    if name is None:
        name = "localargo"
    return logging.getLogger(name)


# Global logger instance
logger = get_logger()


def init_cli_logging(*, verbose: bool = False) -> logging.Logger:
    """Initialize logging for CLI usage.

    Args:
        verbose: Enable debug logging

    Returns:
        Configured logger
    """
    # Check environment variable first, then verbose flag
    env_level = os.getenv("LOCALARGO_LOG_LEVEL", "").upper()
    if env_level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
        level = env_level
    else:
        level = "DEBUG" if verbose else "INFO"
    return setup_logging(level=level)
