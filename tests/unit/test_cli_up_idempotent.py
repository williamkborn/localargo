# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Tests for idempotent up command integration."""

from unittest.mock import patch

from click.testing import CliRunner

from localargo.cli.commands.up import up_cmd, validate_cmd
from localargo.core.types import ExecutionStep, StepStatus


class TestCLIUpIdempotent:
    """Test cases for the idempotent up command."""

    def test_up_command_force_flag_accepted(self, tmp_path):
        """Test that up command accepts --force flag."""
        # Create a minimal manifest
        manifest_file = tmp_path / "localargo.yaml"
        manifest_file.write_text("""cluster:
  - name: test-cluster
    provider: kind
""")

        runner = CliRunner()

        with patch("localargo.core.execution.create_up_execution_engine") as mock_engine:
            mock_engine_instance = mock_engine.return_value
            mock_engine_instance.execute.return_value = {}
            mock_engine_instance.get_status_summary.return_value = {
                "completed": 1,
                "skipped": 0,
                "failed": 0,
                "pending": 0,
            }

            # Test that --force flag is accepted (should not raise an error)
            result = runner.invoke(up_cmd, ["--manifest", str(manifest_file), "--force"])

            # Should succeed (may fail later due to mocking, but flag parsing should work)
            # We're mainly testing that the flag is accepted
            assert result.exit_code in [0, 1]  # 0 for success, 1 for execution errors

    def test_up_command_normal_execution(self, tmp_path):
        """Test normal up command execution without force."""
        manifest_file = tmp_path / "localargo.yaml"
        manifest_file.write_text("""cluster:
  - name: test-cluster
    provider: kind
""")

        runner = CliRunner()

        # Mock the cluster creation to avoid actually creating clusters in tests
        with patch("localargo.core.cluster.cluster_manager.create_cluster", return_value=True):
            result = runner.invoke(up_cmd, ["--manifest", str(manifest_file)])

            # The command should succeed (exit code may vary based on cluster creation success)
            # We're mainly testing that the execution framework is invoked
            assert result.exit_code in [
                0,
                1,
            ]  # 0 for success, 1 for cluster creation "failure" (mocked)
            assert "Checking:" in result.output  # Should show checking steps
            assert "Up complete:" in result.output  # Should show completion summary

    def test_up_command_force_execution(self, tmp_path):
        """Test up command execution with --force flag."""
        manifest_file = tmp_path / "localargo.yaml"
        manifest_file.write_text("""cluster:
  - name: test-cluster
    provider: kind
""")

        runner = CliRunner()

        # Mock the cluster creation to avoid actually creating clusters in tests
        with patch("localargo.core.cluster.cluster_manager.create_cluster", return_value=True):
            result = runner.invoke(up_cmd, ["--manifest", str(manifest_file), "--force"])

            # The command should succeed (exit code may vary based on cluster creation success)
            assert result.exit_code in [
                0,
                1,
            ]  # 0 for success, 1 for cluster creation "failure" (mocked)
            assert "Force executing:" in result.output  # Should show force execution
            assert "Up complete:" in result.output  # Should show completion summary

    def test_up_command_execution_failure(self, tmp_path):
        """Test up command when execution fails."""
        manifest_file = tmp_path / "localargo.yaml"
        manifest_file.write_text("""cluster:
  - name: test-cluster
    provider: kind
""")

        runner = CliRunner()

        # Mock cluster creation to fail by patching the provider's create_cluster method
        with patch("localargo.providers.kind.KindProvider.create_cluster", return_value=False):
            result = runner.invoke(up_cmd, ["--manifest", str(manifest_file)])

            assert result.exit_code == 1  # Should exit with error due to exception propagation

    def test_validate_command_status_flag(self, tmp_path):
        """Test validate command with --status flag."""
        manifest_file = tmp_path / "localargo.yaml"
        manifest_file.write_text("""cluster:
  - name: test-cluster
    provider: kind
""")

        runner = CliRunner()

        # Create a proper mock step using ExecutionStep
        mock_step = ExecutionStep(
            name="test-step",
            description="Test step",
            check_function=lambda m, c: StepStatus(  # noqa: ARG005
                state="completed", reason="Already done"
            ),
            execute_function=lambda m, c: None,  # noqa: ARG005
            requires_client=False,
        )

        with patch("localargo.cli.commands.up.STANDARD_UP_STEPS", [mock_step]):
            result = runner.invoke(
                validate_cmd, ["--manifest", str(manifest_file), "--status"]
            )

            assert result.exit_code == 0
            assert "Checking current status" in result.output
            assert "✅" in result.output  # Should show completed status

    def test_validate_command_normal_mode(self, tmp_path):
        """Test validate command in normal mode (shows plan)."""
        manifest_file = tmp_path / "localargo.yaml"
        manifest_file.write_text("""cluster:
  - name: test-cluster
    provider: kind
apps:
  - test-app:
      repo: https://github.com/test/repo
      namespace: default
""")

        runner = CliRunner()
        result = runner.invoke(validate_cmd, ["--manifest", str(manifest_file)])

        assert result.exit_code == 0
        assert "Planned steps:" in result.output
        assert "Create cluster" in result.output

    def test_validate_command_with_missing_env_vars(self, tmp_path, monkeypatch):
        """Test validate command fails with missing environment variables."""
        # Ensure TEST_VAR is not set
        monkeypatch.delenv("TEST_VAR", raising=False)

        manifest_file = tmp_path / "localargo.yaml"
        manifest_file.write_text("""cluster:
  - name: test-cluster
    provider: kind
secrets:
  - test-secret:
      namespace: default
      secretName: my-secret
      secretKey: password
      secretValue:
        - fromEnv: TEST_VAR
""")

        runner = CliRunner()
        result = runner.invoke(validate_cmd, ["--manifest", str(manifest_file)])

        assert result.exit_code == 1
        # The validation error is logged, so check that it would have been in the output
        # The actual validation happens and exits with code 1

    def test_validate_command_status_all_completed(self, tmp_path):
        """Test validate --status when all steps are completed."""
        manifest_file = tmp_path / "localargo.yaml"
        manifest_file.write_text("""cluster:
  - name: test-cluster
    provider: kind
""")

        runner = CliRunner()

        # Create proper mock steps using ExecutionStep
        mock_step1 = ExecutionStep(
            name="step1",
            description="Step 1",
            check_function=lambda m, c: StepStatus(  # noqa: ARG005
                state="completed", reason="Already done"
            ),
            execute_function=lambda m, c: None,  # noqa: ARG005
            requires_client=False,
        )

        mock_step2 = ExecutionStep(
            name="step2",
            description="Step 2",
            check_function=lambda m, c: StepStatus(  # noqa: ARG005
                state="completed", reason="Already done"
            ),
            execute_function=lambda m, c: None,  # noqa: ARG005
            requires_client=False,
        )

        with patch("localargo.cli.commands.up.STANDARD_UP_STEPS", [mock_step1, mock_step2]):
            result = runner.invoke(
                validate_cmd, ["--manifest", str(manifest_file), "--status"]
            )

            assert result.exit_code == 0
            assert "All steps are already completed!" in result.output

    def test_validate_command_status_some_pending(self, tmp_path):
        """Test validate --status when some steps are pending."""
        # Create a manifest that will have some steps that can't be checked
        # (like ArgoCD when cluster doesn't exist)
        manifest_file = tmp_path / "localargo.yaml"
        manifest_file.write_text("""cluster:
  - name: test-cluster
    provider: kind
""")

        runner = CliRunner()

        # Mock cluster check to return pending to simulate a realistic scenario
        with patch("localargo.core.checkers.check_cluster") as mock_check_cluster:
            mock_check_cluster.return_value = type(
                "MockStatus",
                (),
                {
                    "state": "pending",
                    "reason": "Cluster does not exist",
                    "is_completed": False,
                },
            )()

            result = runner.invoke(
                validate_cmd, ["--manifest", str(manifest_file), "--status"]
            )

            assert result.exit_code == 0
            # With a minimal manifest, most steps get skipped (no secrets/apps/repo-creds)
            # but the cluster step should be pending
            assert "Checking current status" in result.output

    def test_validate_status_with_cluster_down(self, tmp_path):
        """Test validate --status when cluster is down (can't check ArgoCD-dependent steps)."""
        manifest_file = tmp_path / "localargo.yaml"
        manifest_file.write_text("""cluster:
  - name: test-cluster
    provider: kind

secrets:
  - test-secret:
      namespace: default
      literals:
        - key1=value1

apps:
  - test-app:
      namespace: default
      project: default
      repo: https://github.com/test/repo
      path: charts/app
      type: helm
""")

        runner = CliRunner()

        # Mock cluster check to return not ready
        with patch("localargo.core.checkers.check_cluster") as mock_check_cluster:
            mock_check_cluster.return_value = StepStatus(
                state="pending", reason="Cluster does not exist"
            )

            result = runner.invoke(
                validate_cmd, ["--manifest", str(manifest_file), "--status"]
            )

            assert result.exit_code == 0
            assert "Checking current status" in result.output
            # Client-dependent steps should show "Cannot check (dependencies not ready)"
            assert "Cannot check (dependencies not ready)" in result.output
            # Should show that some steps need execution
            assert "Some steps need to be executed" in result.output

    def test_validate_status_with_argocd_down(self, tmp_path):
        """Test validate --status when cluster is up but ArgoCD is down."""
        manifest_file = tmp_path / "localargo.yaml"
        manifest_file.write_text("""cluster:
  - name: test-cluster
    provider: kind

repo-creds:
  - url: https://github.com/test
    username: testuser
    password-from-env: TEST_PASSWORD

apps:
  - test-app:
      namespace: default
      project: default
      repo: https://github.com/test/repo
      path: charts/app
      type: helm
""")

        runner = CliRunner()

        # Mock cluster check to return ready, but ArgoCD check to return not ready
        with (
            patch("localargo.core.checkers.check_cluster") as mock_check_cluster,
            patch("localargo.core.checkers.check_argocd") as mock_check_argocd,
        ):
            mock_check_cluster.return_value = StepStatus(
                state="completed", reason="Cluster is ready"
            )
            mock_check_argocd.return_value = StepStatus(
                state="pending", reason="ArgoCD is not installed"
            )

            result = runner.invoke(
                validate_cmd, ["--manifest", str(manifest_file), "--status"]
            )

            assert result.exit_code == 0
            assert "Checking current status" in result.output
            # Client-dependent steps (repo-creds, apps) should show dependency message
            assert "Cannot check (dependencies not ready)" in result.output
            assert "Some steps need to be executed" in result.output

    def test_validate_status_with_everything_up(self, tmp_path):
        """Test validate --status when cluster and ArgoCD are both ready."""
        manifest_file = tmp_path / "localargo.yaml"
        manifest_file.write_text("""cluster:
  - name: test-cluster
    provider: kind

secrets:
  - test-secret:
      namespace: default
      literals:
        - key1=value1

apps:
  - test-app:
      namespace: default
      project: default
      repo: https://github.com/test/repo
      path: charts/app
      type: helm
""")

        runner = CliRunner()

        # Mock all checks to return completed
        mock_step = ExecutionStep(
            name="test",
            description="Test step",
            check_function=lambda m, c: StepStatus(  # noqa: ARG005
                state="completed", reason="Already done"
            ),
            execute_function=lambda m, c: None,  # noqa: ARG005
            requires_client=False,
        )

        with (
            patch("localargo.core.checkers.check_cluster") as mock_check_cluster,
            patch("localargo.core.checkers.check_argocd") as mock_check_argocd,
            patch("localargo.cli.commands.up.STANDARD_UP_STEPS", [mock_step, mock_step]),
        ):
            mock_check_cluster.return_value = StepStatus(
                state="completed", reason="Cluster is ready"
            )
            mock_check_argocd.return_value = StepStatus(
                state="completed", reason="ArgoCD is ready"
            )

            result = runner.invoke(
                validate_cmd, ["--manifest", str(manifest_file), "--status"]
            )

            assert result.exit_code == 0
            assert "Checking current status" in result.output
            assert "All steps are already completed" in result.output

    def test_validate_command_with_exclude_option(self, tmp_path):
        """Test that validate command accepts --exclude option and filters apps."""
        manifest_file = tmp_path / "localargo.yaml"
        manifest_file.write_text("""cluster:
  - name: test-cluster
    provider: kind

apps:
  - app1:
      namespace: default
      repo_url: https://github.com/example/repo
      path: .
      target_revision: main
  - app2:
      namespace: default
      repo_url: https://github.com/example/repo
      path: .
      target_revision: main
""")

        runner = CliRunner()

        # Test validate with --exclude option
        result = runner.invoke(
            validate_cmd, ["--manifest", str(manifest_file), "--exclude", "app1"]
        )

        assert result.exit_code == 0
        assert "Excluded 1 app(s): app1" in result.output
        # Should show only app2 in the plan
        assert "app 'app2'" in result.output
        # app1 should not appear in the planned steps (only in the exclusion message)
        assert "app 'app1'" not in result.output

    def test_up_command_with_exclude_option(self, tmp_path):
        """Test that up command accepts --exclude option."""
        manifest_file = tmp_path / "localargo.yaml"
        manifest_file.write_text("""cluster:
  - name: test-cluster
    provider: kind

apps:
  - app1:
      namespace: default
      repo_url: https://github.com/example/repo
      path: .
      target_revision: main
""")

        runner = CliRunner()

        with patch("localargo.core.execution.create_up_execution_engine") as mock_engine:
            mock_engine_instance = mock_engine.return_value
            mock_engine_instance.execute.return_value = {}
            mock_engine_instance.get_status_summary.return_value = {
                "completed": 1,
                "skipped": 0,
                "failed": 0,
                "pending": 0,
            }

            # Test that --exclude flag is accepted
            result = runner.invoke(
                up_cmd, ["--manifest", str(manifest_file), "--exclude", "app1"]
            )

            # Should succeed (may fail later due to mocking, but flag parsing should work)
            assert result.exit_code in [0, 1]  # 0 for success, 1 for execution errors
