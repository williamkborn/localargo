"""Tables for app list/status with color-coded Health and Sync."""

from __future__ import annotations

from typing import Any

from rich.table import Table
from rich.text import Text

from localargo.eyecandy.table_renderer import TableRenderer


def _style_health(val: str) -> str:
    v = (val or "").lower()
    if v == "healthy":
        return "green"
    if v in ("progressing", "unknown"):
        return "yellow"
    if v == "degraded":
        return "red"
    return "white"


def _style_sync(val: str) -> str:
    v = (val or "").lower()
    if v == "synced":
        return "green"
    if v == "outofsync":
        return "red"
    return "white"


class AppTables(TableRenderer):
    """Render color-coded app state tables using Rich."""

    def render_app_states(self, states: list[dict[str, Any]]) -> None:
        """Render a table of app states with styled Health/Sync columns."""
        if not states:
            self.console.print("[dim]No apps found[/dim]")
            return
        table = Table(show_header=True, header_style="bold blue", box=None)
        table.add_column("Name", style="cyan", no_wrap=True)
        table.add_column("Namespace", style="blue")
        table.add_column("Health", style="white")
        table.add_column("Sync", style="white")
        table.add_column("Revision", style="white")
        for st in states:
            table.add_row(
                Text(str(st.get("Name", "")), style="cyan"),
                Text(str(st.get("Namespace", "")), style="blue"),
                Text(
                    str(st.get("Health", "")), style=_style_health(str(st.get("Health", "")))
                ),
                Text(str(st.get("Sync", "")), style=_style_sync(str(st.get("Sync", "")))),
                Text(str(st.get("Revision", "")), style="white"),
            )
        self.console.print(table)
