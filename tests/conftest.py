# SPDX-FileCopyrightText: 2025-present U.N. Owen <void@some.where>
#
# SPDX-License-Identifier: MIT
from unittest.mock import MagicMock, patch

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
        if args and len(args[0]) > 0:
            cmd = args[0]
            if isinstance(cmd, list) and len(cmd) > 0:
                if "kind" in cmd[0] and "version" in cmd:
                    result.stdout = "kind v0.20.0 go1.20.0"
                elif "k3s" in cmd[0] and len(cmd) > 1 and cmd[1] == "--version":
                    result.stdout = "k3s version v1.27.0+k3s1"
                elif "kubectl" in cmd[0] and "cluster-info" in cmd:
                    result.stdout = "Kubernetes control plane is running"
                elif "kind" in cmd[0] and "get" in cmd and "clusters" in cmd:
                    result.stdout = "demo\nother-cluster\n"

        return result

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
        }
        return available_tools.get(cmd)

    with patch("shutil.which", side_effect=mock_which) as mock_which_func:
        yield mock_which_func


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Prevent accidental real sleeps during tests."""
    monkeypatch.setattr("time.sleep", lambda *_: None)
