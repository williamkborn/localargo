# SPDX-FileCopyrightText: 2025-present U.N. Owen <void@some.where>

#
# SPDX-License-Identifier: MIT

"""Table renderer interface for LocalArgo CLI UI."""

from __future__ import annotations

import shutil
from typing import Any

from rich.console import Console
from rich.table import Table
from rich.text import Text


class TableRenderer:
    """
    Declarative interface to render tabular data.

    Example: status list, key-value display.
    """

    def __init__(self, console: Console | None = None) -> None:
        """Initialize table renderer with optional console."""
        self.console = console or Console()

    def render_list(self, headers: list[str], rows: list[dict[str, Any]]) -> None:
        """Render a list of rows given headers."""
        if not rows:
            self.console.print("[dim]No data to display[/dim]")
            return

        table = Table(show_header=True, header_style="bold blue", box=None)

        # Add columns
        for header in headers:
            table.add_column(header, style="cyan", no_wrap=True)

        # Add rows
        for row in rows:
            table.add_row(*[str(row.get(header, "")) for header in headers])

        self.console.print(table)

    def render_key_values(self, title: str, data: dict[str, Any]) -> None:
        """Render a key/value panel view."""
        from rich.panel import Panel

        # Create a table for key-value pairs
        table = Table(show_header=False, box=None, pad_edge=False)

        # Add key-value pairs as rows
        for key, value in data.items():
            table.add_row(Text(key, style="bold cyan"), Text(str(value), style="white"))

        panel = Panel(table, title=f"[bold blue]{title}[/bold blue]", border_style="blue", padding=(1, 2))

        self.console.print(panel)

    def render_status_table(self, clusters: list[dict[str, Any]]) -> None:
        """Render cluster status in a table format."""
        if not clusters:
            self.console.print("[dim]No clusters to display[/dim]")
            return

        # Calculate terminal width for responsive design
        terminal_width = shutil.get_terminal_size().columns

        # Create status table
        table = Table(title="Cluster Status", show_header=True, header_style="bold magenta")

        # Add columns based on available data
        if clusters and len(clusters) > 0:
            sample = clusters[0]
            if "name" in sample:
                table.add_column("Name", style="cyan", no_wrap=True)
            if "provider" in sample:
                table.add_column("Provider", style="green")
            if "status" in sample:
                table.add_column("Status", style="yellow")
            if "context" in sample:
                table.add_column("Context", style="blue", max_width=min(30, terminal_width // 4))

        # Add rows
        for cluster in clusters:
            row_data = []
            styles = []

            if "name" in cluster:
                row_data.append(cluster["name"])
                styles.append("cyan")

            if "provider" in cluster:
                row_data.append(cluster.get("provider", "unknown"))
                styles.append("green")

            if "status" in cluster:
                status = cluster["status"]
                row_data.append(status)
                # Color code status
                if status.lower() in ["ready", "running", "healthy"]:
                    styles.append("green")
                elif status.lower() in ["pending", "starting"]:
                    styles.append("yellow")
                elif status.lower() in ["failed", "error", "stopped"]:
                    styles.append("red")
                else:
                    styles.append("white")

            if "context" in cluster:
                context = cluster.get("context", "")
                row_data.append(context)
                styles.append("blue")

            # Add styled row
            styled_row = [Text(str(item), style=styles[i]) for i, item in enumerate(row_data)]
            table.add_row(*styled_row)

        self.console.print(table)

    def render_simple_list(self, items: list[str], title: str | None = None) -> None:
        """Render a simple list of items."""
        from rich.panel import Panel

        if not items:
            self.console.print("[dim]No items to display[/dim]")
            return

        # Create a simple list
        from rich.columns import Columns

        rendered_items = [Text(f"• {item}", style="white") for item in items]

        if title:
            panel = Panel(
                Columns(rendered_items, equal=False, expand=True),
                title=f"[bold blue]{title}[/bold blue]",
                border_style="blue",
            )
            self.console.print(panel)
        else:
            self.console.print(Columns(rendered_items, equal=False, expand=True))
