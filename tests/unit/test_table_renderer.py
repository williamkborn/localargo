# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>

#
# SPDX-License-Identifier: MIT

"""Tests for table renderer UI component."""

import shutil
from unittest.mock import MagicMock, patch

from rich.console import Console

from localargo.eyecandy.table_renderer import TableRenderer


class TestTableRenderer:
    """Test cases for TableRenderer class."""

    def test_render_list_empty_data(self):
        """Test rendering empty data shows appropriate message."""
        console = Console(record=True)
        renderer = TableRenderer(console)
        renderer.render_list(["Name", "Status"], [])

        output = console.export_text()
        assert "No data to display" in output

    def test_render_list_with_data(self):
        """Test rendering list with data displays table correctly."""
        console = Console(record=True)
        renderer = TableRenderer(console)
        headers = ["Name", "Status", "Type"]
        rows = [
            {"Name": "test-cluster", "Status": "ready", "Type": "kind"},
            {"Name": "prod-cluster", "Status": "running", "Type": "k3s"},
        ]

        renderer.render_list(headers, rows)

        output = console.export_text()
        assert "test-cluster" in output
        assert "prod-cluster" in output
        assert "ready" in output
        assert "running" in output
        assert "kind" in output
        assert "k3s" in output

    def test_render_key_values(self):
        """Test rendering key-value pairs displays panel correctly."""
        console = Console(record=True)
        renderer = TableRenderer(console)
        data = {
            "Cluster": "test-cluster",
            "Status": "ready",
            "Provider": "kind",
            "Context": "kind-test-cluster",
        }

        renderer.render_key_values("Cluster Info", data)

        output = console.export_text()
        assert "Cluster Info" in output
        assert "test-cluster" in output
        assert "ready" in output
        assert "kind" in output

    def test_render_status_table(self):
        """Test rendering status table with cluster data."""
        console = Console(record=True)
        renderer = TableRenderer(console)
        clusters = [
            {
                "name": "test-cluster",
                "provider": "kind",
                "status": "ready",
                "context": "kind-test-cluster",
            },
            {
                "name": "failed-cluster",
                "provider": "k3s",
                "status": "failed",
                "context": "k3s-failed-cluster",
            },
        ]

        renderer.render_status_table(clusters)

        output = console.export_text()
        assert "Cluster Status" in output
        assert "test-cluster" in output
        assert "failed-cluster" in output
        assert "ready" in output
        assert "failed" in output

    def test_render_status_table_empty(self):
        """Test rendering status table with no clusters."""
        console = Console(record=True)
        renderer = TableRenderer(console)
        renderer.render_status_table([])

        output = console.export_text()
        assert "No clusters to display" in output

    def test_render_simple_list(self):
        """Test rendering simple list of items."""
        console = Console(record=True)
        renderer = TableRenderer(console)
        items = ["item1", "item2", "item3"]

        renderer.render_simple_list(items, "Test Items")

        output = console.export_text()
        assert "Test Items" in output
        assert "• item1" in output
        assert "• item2" in output
        assert "• item3" in output

    def test_render_simple_list_empty(self):
        """Test rendering simple list with no items."""
        console = Console(record=True)
        renderer = TableRenderer(console)
        renderer.render_simple_list([], "Empty List")

        output = console.export_text()
        assert "No items to display" in output

    def test_render_simple_list_no_title(self):
        """Test rendering simple list without title."""
        console = Console(record=True)
        renderer = TableRenderer(console)
        items = ["item1", "item2"]

        renderer.render_simple_list(items)

        output = console.export_text()
        assert "• item1" in output
        assert "• item2" in output
        # Should not contain any panel markup since no title
        assert "┌─" not in output
        assert "└─" not in output

    def test_console_recording(self):
        """Test that console recording works for testing."""
        console = Console(record=True)
        renderer = TableRenderer(console)

        # Render something
        renderer.render_list(["Test"], [{"Test": "value"}])

        # Check that console recorded the output
        output = console.export_text()
        assert "value" in output

    def test_responsive_width_handling(self):
        """Test that table adapts to terminal width."""
        # This test verifies that the table renderer doesn't crash with different terminal sizes
        console = Console(record=True)
        renderer = TableRenderer(console)

        # Test with very narrow terminal (should not crash)
        original_columns = shutil.get_terminal_size().columns

        try:
            # Mock a narrow terminal
            with patch("shutil.get_terminal_size", return_value=MagicMock(columns=40)):
                clusters = [{"name": "verylongclustername", "status": "ready"}]
                # Should not raise an exception
                renderer.render_status_table(clusters)

                output = console.export_text()
                assert "verylongclustername" in output
        finally:
            # Restore original terminal size
            with patch(
                "shutil.get_terminal_size",
                return_value=MagicMock(columns=original_columns),
            ):
                pass
