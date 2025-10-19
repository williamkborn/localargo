# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>

#
# SPDX-License-Identifier: MIT

"""Tests for progress steps UI component."""

import time

import pytest
from rich.console import Console

from localargo.eyecandy.progress_steps import StepLogger


class TestStepLogger:
    """Test cases for StepLogger class."""

    def test_init(self):
        """Test StepLogger initialization."""
        steps = ["step1", "step2", "step3"]
        logger = StepLogger(steps)

        assert logger.steps == steps
        assert logger.current_step_index == 0
        assert isinstance(logger.start_time, float)
        assert logger.get_completed_steps_count() == 0

    def test_context_manager_enter(self):
        """Test entering context manager displays initial message."""
        steps = ["step1", "step2"]
        console = Console(record=True)
        logger = StepLogger(steps, console=console)

        with logger:
            pass

        output = console.export_text()
        assert "Starting workflow with 2 steps" in output

    def test_context_manager_exit_success(self):
        """Test exiting context manager after successful completion."""
        steps = ["step1", "step2"]
        console = Console(record=True)
        logger = StepLogger(steps, console=console)

        with logger:
            logger.step("step1", status="success")
            logger.step("step2", status="success")

        output = console.export_text()
        assert "All 2 steps completed successfully" in output

    def test_context_manager_exit_with_warnings(self):
        """Test exiting context manager with warnings."""
        steps = ["step1", "step2"]
        console = Console(record=True)
        logger = StepLogger(steps, console=console)

        with logger:
            logger.step("step1", status="success")
            logger.step("step2", status="warning")

        output = console.export_text()
        assert "1/2 steps completed with 1 warnings" in output

    def test_context_manager_exit_with_errors(self):
        """Test exiting context manager with errors."""
        steps = ["step1", "step2"]
        console = Console(record=True)
        logger = StepLogger(steps, console=console)

        with logger:
            logger.step("step1", status="success")
            logger.step("step2", status="error", error_msg="Test error")

        output = console.export_text()
        assert "1/2 steps completed with 1 errors" in output

    def test_step_success(self):
        """Test logging a successful step."""
        console = Console(record=True)
        logger = StepLogger(["test_step"], console=console)
        logger.step("test_step", status="success")

        output = console.export_text()
        assert "✅ test_step" in output

    def test_step_warning(self):
        """Test logging a warning step."""
        console = Console(record=True)
        logger = StepLogger(["test_step"], console=console)
        logger.step("test_step", status="warning")

        output = console.export_text()
        assert "⚠️" in output
        assert "test_step" in output

    def test_step_failure(self):
        """Test logging a failed step."""
        console = Console(record=True)
        logger = StepLogger(["test_step"], console=console)
        logger.step("test_step", status="error", error_msg="Something went wrong")

        output = console.export_text()
        assert "❌ test_step" in output
        assert "Something went wrong" in output

    def test_step_with_info(self):
        """Test logging a step with additional info."""
        console = Console(record=True)
        logger = StepLogger(["test_step"], console=console)
        logger.step("test_step", status="success", items_processed=42, duration="2.5s")

        output = console.export_text()
        assert "items_processed=42" in output
        assert "duration=2.5s" in output

    def test_step_unknown_step(self):
        """Test logging a step that doesn't exist in the steps list."""
        console = Console(record=True)
        logger = StepLogger(["known_step"], console=console)
        logger.step("unknown_step", status="success")

        output = console.export_text()
        assert "⚠️" in output
        assert "Unknown step: unknown_step" in output

    def test_step_with_progress_context_manager(self):
        """Test step with progress context manager."""
        console = Console(record=True)
        logger = StepLogger(["test_step"], console=console)

        with logger.step_with_progress("test_step", total=100) as _:
            # The progress context manager should work without manual task management
            # since the task is already created inside step_with_progress
            pass

        output = console.export_text()
        assert "✅ test_step" in output
        assert "Completed 100 items" in output

    def test_step_with_progress_exception(self):
        """Test step with progress context manager that raises exception."""
        console = Console(record=True)
        logger = StepLogger(["test_step"], console=console)

        error_msg = "Test error"
        with (
            pytest.raises(ValueError, match=error_msg),
            logger.step_with_progress("test_step", total=100) as _,
        ):
            raise ValueError(error_msg)

        output = console.export_text()
        assert "❌ test_step" in output
        assert "Test error" in output

    def test_get_step_info(self):
        """Test getting step information."""
        console = Console(record=True)
        logger = StepLogger(["test_step"], console=console)
        logger.step("test_step", status="success", custom_info="test_value")

        info = logger.get_step_info("test_step")
        assert info is not None
        assert info["success"] is True
        assert info["info"]["custom_info"] == "test_value"

        # Test non-existent step
        assert logger.get_step_info("nonexistent") is None

    def test_is_completed(self):
        """Test checking if step is completed."""
        console = Console(record=True)
        logger = StepLogger(["test_step"], console=console)

        assert not logger.is_completed("test_step")

        logger.step("test_step", status="success")

        assert logger.is_completed("test_step")

    def test_get_success_count(self):
        """Test getting count of successful steps."""
        console = Console(record=True)
        logger = StepLogger(["step1", "step2", "step3"], console=console)

        assert logger.get_success_count() == 0

        logger.step("step1", status="success")
        assert logger.get_success_count() == 1

        logger.step("step2", status="warning")
        assert logger.get_success_count() == 1

        logger.step("step3", status="error")
        assert logger.get_success_count() == 1

    def test_get_error_count(self):
        """Test getting count of error steps."""
        console = Console(record=True)
        logger = StepLogger(["step1", "step2", "step3"], console=console)

        assert logger.get_error_count() == 0

        logger.step("step1", status="success")
        assert logger.get_error_count() == 0

        logger.step("step2", status="warning")
        assert logger.get_error_count() == 0

        logger.step("step3", status="error")
        assert logger.get_error_count() == 1

    def test_console_recording(self):
        """Test that console recording works for testing."""
        console = Console(record=True)
        logger = StepLogger(["test_step"], console=console)

        logger.step("test_step", status="success")

        # Check that console recorded the output
        output = console.export_text()
        assert "✅" in output
        assert "test_step" in output

    def test_timing_calculation(self):
        """Test that timing is calculated correctly."""
        console = Console(record=True)
        logger = StepLogger(["step1", "step2"], console=console)

        # Record start time
        start_time = logger.start_time

        # Small delay to ensure time difference
        time.sleep(0.01)

        logger.step("step1", status="success")

        # Check that step timestamp is after start time
        step_info = logger.get_step_info("step1")
        assert step_info is not None
        assert step_info["timestamp"] >= start_time

    def test_step_summary_display(self):
        """Test that step summary is displayed correctly."""
        steps = ["step1", "step2", "step3"]
        console = Console(record=True)
        logger = StepLogger(steps, console=console)

        with logger:
            logger.step("step1", status="success")
            # step2 not completed
            logger.step("step3", status="error", error_msg="Failed")

        output = console.export_text()
        assert "Step Summary:" in output
        assert "✅ step1" in output
        assert "⏳ step2" in output
        assert "❌ step3" in output
