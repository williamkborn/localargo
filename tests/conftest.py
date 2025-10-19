"""Test configuration and global fixtures for localargo tests."""

# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>
#
# SPDX-License-Identifier: MIT
from unittest.mock import MagicMock, Mock, patch

import pytest


@pytest.fixture(autouse=True)
def mock_subprocess_run():
    """Patch subprocess.run globally to prevent actual shell commands."""

    def mock_run_side_effect(*args, **_kwargs):
        # Create a mock result
        result = MagicMock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""

        # Customize based on command
        if not args or not args[0]:
            return result

        cmd = args[0]
        if not isinstance(cmd, list) or not cmd:
            return result

        # Dispatch to prepared handlers
        _apply_mock_command_handlers(cmd, result)
        return result

    def _apply_mock_command_handlers(cmd, result):
        """Apply output adjustments based on the given command list."""
        tool = str(cmd[0])
        if "kind" in tool:
            _handle_kind(cmd, result)
            return
        if "k3s" in tool:
            _handle_k3s(cmd, result)
            return
        if "kubectl" in tool:
            _handle_kubectl(cmd, result)
            return
        if "helm" in tool:
            _handle_helm(cmd, result)
            return

    def _handle_kind(cmd, result):
        if "version" in cmd:
            result.stdout = "kind v0.20.0 go1.20.0"
            return
        if "get" in cmd and "clusters" in cmd:
            result.stdout = "demo\nother-cluster\n"
            return

    def _handle_k3s(cmd, result):
        if len(cmd) > 1 and cmd[1] == "--version":
            result.stdout = "k3s version v1.27.0+k3s1"

    def _handle_kubectl(cmd, result):
        if "cluster-info" in cmd:
            result.stdout = "Kubernetes control plane is running"

    def _handle_helm(cmd, result):
        if "repo" in cmd and "add" in cmd:
            result.stdout = ""
            return
        if "repo" in cmd and "update" in cmd:
            result.stdout = (
                "Hang tight while we grab the latest from your chart repositories..."
            )

    with patch("subprocess.run", side_effect=mock_run_side_effect) as mock_run:
        yield mock_run


@pytest.fixture(autouse=True)
def mock_subprocess_popen():
    """Patch subprocess.Popen for background processes."""
    with patch("subprocess.Popen") as mock_popen:
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Process is running
        mock_process.returncode = 0
        mock_process.pid = 12345
        mock_popen.return_value = mock_process
        yield mock_popen


@pytest.fixture(autouse=True)
def mock_shutil_which():
    """Patch shutil.which to simulate available tools."""

    def mock_which(cmd):
        # Simulate that common tools are available
        available_tools = {
            "kind": "/usr/local/bin/kind",
            "k3s": "/usr/local/bin/k3s",
            "kubectl": "/usr/local/bin/kubectl",
            "helm": "/usr/local/bin/helm",
        }
        return available_tools.get(cmd)

    with patch("shutil.which", side_effect=mock_which) as mock_which_func:
        yield mock_which_func


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Prevent accidental real sleeps during tests."""
    monkeypatch.setattr("time.sleep", lambda *_: None)


# Common test utilities for duplicated test patterns
@pytest.fixture
def sample_cluster_yaml_content():
    """Common YAML content for a single test cluster."""
    return """
clusters:
  - name: test-cluster
    provider: kind
"""


@pytest.fixture
def sample_multi_cluster_yaml_content():
    """Common YAML content for multiple test clusters."""
    return """
clusters:
  - name: cluster1
    provider: kind
  - name: cluster2
    provider: k3s
"""


@pytest.fixture
def create_manifest_file(tmp_path):
    """Create a temporary manifest file with sample cluster YAML."""
    default_content = """
clusters:
  - name: test-cluster
    provider: kind
"""

    def _create_file(yaml_content=None, filename="clusters.yaml"):
        content = yaml_content if yaml_content is not None else default_content
        manifest_file = tmp_path / filename
        manifest_file.write_text(content)
        return manifest_file

    return _create_file


@pytest.fixture
def create_mock_cluster_manager():
    """Create a mock ClusterManager with common return values."""

    def _create_mock(return_value=None, spec=None):
        mock_manager = Mock() if spec is None else Mock(spec=spec)
        if return_value is not None:
            mock_manager.apply.return_value = return_value
            mock_manager.delete.return_value = return_value
            mock_manager.status.return_value = return_value
        return mock_manager

    return _create_mock


@pytest.fixture
def create_mock_provider():
    """Create a mock provider with common return values."""

    def _create_mock(name="test-cluster", **kwargs):
        mock_provider = Mock()
        mock_provider.name = name
        for key, value in kwargs.items():
            setattr(mock_provider, key, value)
        return mock_provider

    return _create_mock
