# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>

#
# SPDX-License-Identifier: MIT

"""Progress steps interface for LocalArgo CLI UI."""

# pylint: disable=duplicate-code,too-many-public-methods,too-many-instance-attributes

from __future__ import annotations

import time
from contextlib import suppress
from typing import TYPE_CHECKING, Any

with suppress(ImportError):
    pass


if TYPE_CHECKING:
    from rich.console import Console

    from localargo.eyecandy.step_logger import StepLogger


def _validate_step_exists(name: str, steps: list[str], console: Console) -> bool:
    """Validate that a step exists in the steps list."""
    if name not in steps:
        console.print(f"[red]⚠️  Unknown step: {name}[/red]")
        return False
    return True


def _create_step_info(
    status: str, error_msg: str | None, info: dict[str, Any]
) -> dict[str, Any]:
    """Create step info dictionary from status and additional data."""
    success = status == "success"
    warning = status == "warning"
    error = status == "error"

    return {
        "success": success,
        "warning": warning,
        "error": error,
        "error_msg": error_msg,
        "info": info,
        "timestamp": time.time(),
    }


def _update_current_step_index(
    name: str, steps: list[str], progress_logger: StepLogger
) -> None:
    """Update the current step index."""
    with suppress(ValueError):
        progress_logger.current_step_index = steps.index(name)


def _display_step_status(name: str, step_info: dict[str, Any], console: Console) -> None:
    """Display the step status with appropriate styling."""
    icon, style = _get_step_display_info(step_info)

    # Format step display
    step_display = f"[bold {style}]{icon} {name}[/bold {style}]"

    if step_info.get("error_msg"):
        console.print(f"{step_display} - {step_info['error_msg']}")
    else:
        console.print(step_display)

    # Show additional info if provided
    info = step_info.get("info", {})
    if info:
        info_text = ", ".join(f"{k}={v}" for k, v in info.items())
        console.print(f"  [dim]{info_text}[/dim]")


def _get_step_display_info(step_info: dict[str, Any]) -> tuple[str, str]:
    """Get the icon and style for step display."""
    if step_info.get("success"):
        return "✅", "green"
    if step_info.get("warning"):
        return "⚠️", "yellow"
    return "❌", "red"
