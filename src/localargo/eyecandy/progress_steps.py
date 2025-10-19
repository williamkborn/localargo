# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>

#
# SPDX-License-Identifier: MIT

"""Progress steps interface for LocalArgo CLI UI."""

# pylint: disable=duplicate-code,too-many-public-methods,too-many-instance-attributes

from __future__ import annotations

import time
from contextlib import contextmanager, suppress
from typing import TYPE_CHECKING, Any

try:
    from typing import Self
except ImportError:
    from typing_extensions import Self

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

if TYPE_CHECKING:
    from collections.abc import Generator


class StepLogger:
    """
    Supports declarative multi-step progress flows.

    Args:
        steps (list[str]): List of step names to track
        console (Console | None): Rich console instance for output
            (optional, creates default if None)

    Example:
      steps = ["initialize", "create cluster", "wait for readiness", "configure kubecontext"]
      with StepLogger(steps) as logger:
          logger.step("initialize", status="success")
          logger.step("create cluster", status="error", error_msg="timeout")
    """

    def __init__(self, steps: list[str], console: Console | None = None) -> None:
        self.steps = steps
        self.console = console or Console()
        self.current_step_index = 0
        self.start_time = time.time()
        self._completed_steps: dict[str, dict[str, Any]] = {}

    def __enter__(self) -> Self:
        """Enter context manager, display initial progress."""
        self.console.print(
            f"\n[bold blue]Starting workflow with {len(self.steps)} steps...[/bold blue]\n"
        )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Exit context manager, show final summary."""
        total_time = time.time() - self.start_time

        # Count successes, warnings, and failures
        success_count, warning_count, error_count = self._count_step_results()

        if error_count == 0 and warning_count == 0:
            self.console.print(
                f"\n[green]✅ All {len(self.steps)} steps completed successfully "
                f"in {total_time:.1f}s[/green]"
            )
        elif error_count == 0:
            self.console.print(
                f"\n[yellow]⚠️  {success_count}/{len(self.steps)} steps completed "
                f"with {warning_count} warnings in {total_time:.1f}s[/yellow]"
            )
        else:
            self.console.print(
                f"\n[red]❌ {success_count}/{len(self.steps)} steps completed "
                f"with {error_count} errors in {total_time:.1f}s[/red]"
            )

        # Show step summary if there were issues
        if error_count > 0 or warning_count > 0:
            self._show_step_summary()

    def step(
        self,
        name: str,
        status: str = "success",
        error_msg: str | None = None,
        **info: Any,
    ) -> None:
        """Log a step with success/failure status."""
        if name not in self.steps:
            self.console.print(f"[red]⚠️  Unknown step: {name}[/red]")
            return

        # Parse status string
        success = status == "success"
        warning = status == "warning"
        error = status == "error"

        step_info = {
            "success": success,
            "warning": warning,
            "error": error,
            "error_msg": error_msg,
            "info": info,
            "timestamp": time.time(),
        }

        self._completed_steps[name] = step_info

        # Update current step index

        with suppress(ValueError):
            self.current_step_index = self.steps.index(name)

        # Display step status
        if success:
            icon = "✅"
            style = "green"
        elif warning:
            icon = "⚠️"
            style = "yellow"
        else:
            icon = "❌"
            style = "red"

        # Format step display
        step_display = f"[bold {style}]{icon} {name}[/bold {style}]"

        if error_msg:
            self.console.print(f"{step_display} - {error_msg}")
        else:
            self.console.print(step_display)

        # Show additional info if provided
        if info:
            info_text = ", ".join(f"{k}={v}" for k, v in info.items())
            self.console.print(f"  [dim]{info_text}[/dim]")

    @contextmanager
    def step_with_progress(
        self, name: str, total: int = 100, description: str | None = None
    ) -> Generator[Progress, None, None]:
        """Context manager for steps that need progress indication."""
        if name not in self.steps:
            self.console.print(f"[red]⚠️  Unknown step: {name}[/red]")
            return

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=self.console,
            transient=True,
        ) as progress:
            progress.add_task(description or f"Processing {name}...", total=total)

            try:
                yield progress

                # Mark step as completed
                self.step(name, status="success", progress_info=f"Completed {total} items")
            except Exception as e:
                # Mark step as failed
                self.step(name, status="error", error_msg=str(e))
                raise

    def _show_step_summary(self) -> None:
        """Show a summary of all step results."""
        if not self._completed_steps:
            return

        self.console.print("\n[bold]Step Summary:[/bold]")

        for step_name in self.steps:
            if step_name in self._completed_steps:
                step_info = self._completed_steps[step_name]
                if step_info.get("success", False):
                    icon = "✅"
                    style = "green"
                elif step_info.get("warning", False):
                    icon = "⚠️"
                    style = "yellow"
                else:
                    icon = "❌"
                    style = "red"

                if step_info.get("timestamp"):
                    duration = step_info["timestamp"] - self.start_time
                    duration = f" ({duration:.1f}s)"
                else:
                    duration = ""

                self.console.print(
                    f"  [bold {style}]{icon} {step_name}[/bold {style}]{duration}"
                )
            else:
                self.console.print(f"  [dim]⏳ {step_name} (not started)[/dim]")

    def get_step_info(self, name: str) -> dict[str, Any] | None:
        """Get information about a specific step."""
        return self._completed_steps.get(name)

    def is_completed(self, name: str) -> bool:
        """Check if a step has been completed."""
        return name in self._completed_steps

    def _count_step_results(self) -> tuple[int, int, int]:
        """Count completed steps by result type.

        Returns:
            tuple[int, int, int]: (success_count, warning_count, error_count)
        """
        success_count = sum(
            1
            for step_info in self._completed_steps.values()
            if step_info.get("success", False) and not step_info.get("warning", False)
        )
        warning_count = sum(
            1
            for step_info in self._completed_steps.values()
            if step_info.get("warning", False)
        )
        error_count = sum(
            1 for step_info in self._completed_steps.values() if step_info.get("error", False)
        )
        return success_count, warning_count, error_count

    def get_completed_steps_count(self) -> int:
        """Get the number of completed steps."""
        return len(self._completed_steps)

    def get_success_count(self) -> int:
        """Get count of successful steps."""
        success_count, _, _ = self._count_step_results()
        return success_count

    def get_error_count(self) -> int:
        """Get count of failed steps."""
        _, _, error_count = self._count_step_results()
        return error_count
