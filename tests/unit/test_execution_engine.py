# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for the idempotent execution framework."""

from unittest.mock import Mock

import pytest

from localargo.core.execution import (
    ExecutionEngine,
    create_up_execution_engine,
)
from localargo.core.types import ExecutionStep, StepStatus


class TestStepStatus:
    """Test cases for StepStatus class."""

    def test_step_status_creation(self):
        """Test basic StepStatus creation."""
        status = StepStatus(state="completed", reason="Test reason")
        assert status.state == "completed"
        assert status.reason == "Test reason"
        assert not status.details
        assert isinstance(status.timestamp, float)

    def test_step_status_with_details(self):
        """Test StepStatus with custom details."""
        details = {"key": "value", "count": 42}
        status = StepStatus(state="pending", reason="Custom reason", details=details)
        assert status.details == details

    def test_step_status_is_completed(self):
        """Test is_completed property."""
        completed_status = StepStatus(state="completed", reason="Done")
        skipped_status = StepStatus(state="skipped", reason="Already done")
        pending_status = StepStatus(state="pending", reason="Not done")
        failed_status = StepStatus(state="failed", reason="Error")

        assert completed_status.is_completed is True
        assert skipped_status.is_completed is True
        assert pending_status.is_completed is False
        assert failed_status.is_completed is False


class TestExecutionStep:
    """Test cases for ExecutionStep class."""

    def test_step_creation(self):
        """Test ExecutionStep creation."""

        def dummy_check(_manifest, _client):
            return StepStatus(state="completed", reason="OK")

        def dummy_execute(_manifest, _client):
            pass

        step = ExecutionStep(
            name="test-step",
            description="Test step",
            check_function=dummy_check,
            execute_function=dummy_execute,
            requires_client=True,
        )

        assert step.name == "test-step"
        assert step.description == "Test step"
        assert step.requires_client is True

    def test_step_check_execution(self):
        """Test step check execution."""
        check_result = StepStatus(state="completed", reason="Mock check")

        def mock_check(_manifest, _client):
            return check_result

        def dummy_execute(_manifest, _client):
            pass

        step = ExecutionStep(
            name="test",
            description="Test",
            check_function=mock_check,
            execute_function=dummy_execute,
        )

        manifest = Mock()
        client = Mock()
        result = step.check(manifest, client)

        assert result == check_result

    def test_step_execute_execution(self):
        """Test step execute execution."""
        executed = {"called": False}

        def dummy_check(_manifest, _client):
            return StepStatus(state="pending", reason="Needs execution")

        def mock_execute(_manifest, _client):
            executed["called"] = True

        step = ExecutionStep(
            name="test",
            description="Test",
            check_function=dummy_check,
            execute_function=mock_execute,
        )

        manifest = Mock()
        client = Mock()
        step.execute(manifest, client)

        assert executed["called"] is True


class TestExecutionEngine:
    """Test cases for ExecutionEngine class."""

    def test_engine_creation(self):
        """Test ExecutionEngine creation with steps."""
        steps = [
            ExecutionStep(
                name="step1",
                description="Step 1",
                check_function=lambda _m, _c: StepStatus(state="completed", reason="OK"),
                execute_function=lambda _m, _c: None,
            ),
            ExecutionStep(
                name="step2",
                description="Step 2",
                check_function=lambda _m, _c: StepStatus(state="pending", reason="Needs work"),
                execute_function=lambda _m, _c: None,
            ),
        ]

        engine = ExecutionEngine(steps)
        assert len(engine.steps) == 2
        assert not engine.results

    def test_execute_with_all_completed_steps(self):
        """Test execution when all steps are already completed."""
        executed_steps = []

        def make_completed_step(name):
            return ExecutionStep(
                name=name,
                description=f"Step {name}",
                check_function=lambda _m, _c: StepStatus(
                    state="completed", reason="Already done"
                ),
                execute_function=lambda _m, _c: executed_steps.append(name),
            )

        steps = [make_completed_step("step1"), make_completed_step("step2")]
        engine = ExecutionEngine(steps)

        manifest = Mock()
        results = engine.execute(manifest)

        # Should not execute any steps since they're all completed
        assert not executed_steps
        assert len(results) == 2
        assert all(status.state == "completed" for status in results.values())

    def test_execute_with_pending_steps(self):
        """Test execution when steps need to be executed."""
        executed_steps = []

        def make_pending_step(name):
            return ExecutionStep(
                name=name,
                description=f"Step {name}",
                check_function=lambda _m, _c: StepStatus(state="pending", reason="Needs work"),
                execute_function=lambda _m, _c: executed_steps.append(name),
            )

        steps = [make_pending_step("step1"), make_pending_step("step2")]
        engine = ExecutionEngine(steps)

        manifest = Mock()
        results = engine.execute(manifest)

        # Should execute both steps
        assert executed_steps == ["step1", "step2"]
        assert len(results) == 2
        assert all(status.state == "completed" for status in results.values())

    def test_execute_with_mixed_states(self):
        """Test execution with mix of completed and pending steps."""
        executed_steps = []

        def make_step(name, state):
            return ExecutionStep(
                name=name,
                description=f"Step {name}",
                check_function=lambda _m, _c: StepStatus(
                    state=state, reason=f"State: {state}"
                ),
                execute_function=lambda _m, _c: executed_steps.append(name),
            )

        steps = [
            make_step("completed", "completed"),
            make_step("pending", "pending"),
            make_step("skipped", "skipped"),
        ]
        engine = ExecutionEngine(steps)

        manifest = Mock()
        results = engine.execute(manifest)

        # Should only execute the pending step
        assert executed_steps == ["pending"]
        assert len(results) == 3
        assert results["completed"].state == "completed"
        assert results["pending"].state == "completed"  # Executed successfully
        assert results["skipped"].state == "skipped"

    def test_execute_force_mode(self):
        """Test execution in force mode (bypasses checking)."""
        executed_steps = []

        def make_step(name):
            return ExecutionStep(
                name=name,
                description=f"Step {name}",
                check_function=lambda _m, _c: StepStatus(
                    state="completed", reason="Would skip"
                ),
                execute_function=lambda _m, _c: executed_steps.append(name),
            )

        steps = [make_step("step1"), make_step("step2")]
        engine = ExecutionEngine(steps)

        manifest = Mock()
        results = engine.execute(manifest, force=True)

        # Should execute all steps regardless of check results
        assert executed_steps == ["step1", "step2"]
        assert len(results) == 2
        assert all(status.state == "completed" for status in results.values())
        assert all("Force executed" in status.reason for status in results.values())

    def test_execute_with_client_requirement(self):
        """Test execution with steps that require ArgoCD client."""
        executed_with_client = []

        def make_step(name, requires_client):
            return ExecutionStep(
                name=name,
                description=f"Step {name}",
                check_function=lambda _m, _c: StepStatus(state="pending", reason="Needs work"),
                execute_function=lambda _m, c: executed_with_client.append(c),
                requires_client=requires_client,
            )

        steps = [
            make_step("no-client", False),
            make_step("with-client", True),
        ]
        engine = ExecutionEngine(steps)

        manifest = Mock()
        client = Mock()
        engine.execute(manifest, client=client)

        # First step should get None as client, second should get the client
        assert len(executed_with_client) == 2
        assert executed_with_client[0] is None
        assert executed_with_client[1] is client

    def test_execute_stops_on_failure(self):
        """Test that execution stops when a step fails."""
        executed_steps = []

        def failing_execute(_m, _c):
            msg = "Step failed"
            raise RuntimeError(msg)

        steps = [
            ExecutionStep(
                name="success",
                description="Success step",
                check_function=lambda _m, _c: StepStatus(state="pending", reason="OK"),
                execute_function=lambda _m, _c: executed_steps.append("success"),
            ),
            ExecutionStep(
                name="failure",
                description="Failing step",
                check_function=lambda _m, _c: StepStatus(state="pending", reason="OK"),
                execute_function=failing_execute,
            ),
            ExecutionStep(
                name="skipped",
                description="Skipped step",
                check_function=lambda _m, _c: StepStatus(state="pending", reason="OK"),
                execute_function=lambda _m, _c: executed_steps.append("skipped"),
            ),
        ]
        engine = ExecutionEngine(steps)

        manifest = Mock()

        with pytest.raises(Exception, match="Step failed"):
            engine.execute(manifest)

        # Only the first step should have executed
        assert executed_steps == ["success"]
        assert len(engine.results) == 2  # Success and failure steps recorded
        assert engine.results["success"].state == "completed"
        assert engine.results["failure"].state == "failed"

    def test_get_status_summary(self):
        """Test status summary generation."""
        engine = ExecutionEngine([])

        # Manually set results to test summary
        engine.results = {
            "completed1": StepStatus(state="completed", reason="OK"),
            "completed2": StepStatus(state="completed", reason="OK"),
            "skipped1": StepStatus(state="skipped", reason="Already done"),
            "failed1": StepStatus(state="failed", reason="Error"),
            "pending1": StepStatus(state="pending", reason="Waiting"),
        }

        summary = engine.get_status_summary()
        assert summary["completed"] == 2
        assert summary["skipped"] == 1
        assert summary["failed"] == 1
        assert summary["pending"] == 1


class TestUpExecutionEngine:  # pylint: disable=too-few-public-methods
    """Test cases for the up-specific execution engine."""

    def test_create_up_execution_engine(self):
        """Test creation of up-specific execution engine."""
        engine = create_up_execution_engine()

        # Should have the standard 6 steps
        assert len(engine.steps) == 6

        step_names = [step.name for step in engine.steps]
        expected_names = ["cluster", "argocd", "nginx", "secrets", "repo-creds", "apps"]
        assert step_names == expected_names

        # Check that steps have correct descriptions
        descriptions = [step.description for step in engine.steps]
        assert "Create Kubernetes cluster" in descriptions[0]
        assert "Install ArgoCD" in descriptions[1]
        assert "Install nginx ingress" in descriptions[2]

        # Check client requirements
        assert engine.steps[0].requires_client is False  # cluster
        assert engine.steps[1].requires_client is False  # argocd
        assert engine.steps[2].requires_client is False  # nginx
        assert engine.steps[3].requires_client is False  # secrets
        assert engine.steps[4].requires_client is True  # repo-creds
        assert engine.steps[5].requires_client is True  # apps

    def test_lazy_client_initialization(self):
        """Test that ArgoCD client is only created when needed."""
        # Create steps where only second one requires client
        step1 = ExecutionStep(
            name="no-client",
            description="Step that doesn't need client",
            check_function=lambda m, c: StepStatus(  # noqa: ARG005
                state="pending", reason="Not done"
            ),
            execute_function=lambda m, c: None,  # noqa: ARG005
            requires_client=False,
        )

        step2 = ExecutionStep(
            name="needs-client",
            description="Step that needs client",
            check_function=lambda m, c: StepStatus(  # noqa: ARG005
                state="pending", reason="Not done"
            ),
            execute_function=lambda m, c: None,  # noqa: ARG005
            requires_client=True,
        )

        engine = ExecutionEngine([step1, step2])
        manifest = Mock()

        # Execute without providing a client - should work for first step
        # and attempt to create client for second step (which will fail but that's ok)
        engine.execute(manifest, client=None, force=True)

        # Verify both steps were attempted
        assert len(engine.results) == 2
        assert "no-client" in engine.results
        assert "needs-client" in engine.results
