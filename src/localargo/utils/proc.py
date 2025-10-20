"""Safe subprocess helpers with timeouts and structured errors.

All helpers avoid shell=True and return normalized outputs. Designed to be
monkeypatch-friendly for tests and snapshotting.
"""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING, Any

from localargo.logging import logger
from localargo.utils.cli import check_cli_availability

if TYPE_CHECKING:  # imported only for type checking
    from collections.abc import Iterator


class ProcessError(RuntimeError):
    """Normalized process error with code/stdout/stderr attached."""

    def __init__(self, message: str, *, code: int | None, stdout: str, stderr: str) -> None:
        super().__init__(message)
        self.code = code
        self.stdout = stdout
        self.stderr = stderr


def _precheck_cli(cmd: list[str]) -> None:
    if not cmd:
        msg = "Empty command"
        raise ValueError(msg)
    cli_name = cmd[0]
    # Validate common tools if referenced by name
    if cli_name in ("kubectl", "argocd", "k3s", "kind", "docker"):
        check_cli_availability(cli_name)


def _fmt_cmd(cmd: list[str]) -> str:
    return " ".join(cmd)


def run(cmd: list[str], *, timeout: int = 120) -> str:
    """Run a command and return stdout text.

    Raises ProcessError on non-zero exit.
    """
    _precheck_cli(cmd)
    logger.info("$ %s", _fmt_cmd(cmd))
    try:
        cp = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        timeout_msg = f"Command timed out after {timeout}s: {' '.join(cmd)}"
        raise ProcessError(
            timeout_msg,
            code=None,
            stdout=str(e.stdout or ""),
            stderr=str(e.stderr or ""),
        ) from e

    if cp.returncode != 0:
        _log_failure(cp, cmd)
        failure_msg = (
            "Command failed"
            f" (exit={cp.returncode})\n"
            f"cmd: {_fmt_cmd(cmd)}\n"
            f"stdout:\n{(cp.stdout or '').strip()}\n"
            f"stderr:\n{(cp.stderr or '').strip()}"
        )
        raise ProcessError(
            failure_msg,
            code=cp.returncode,
            stdout=str(cp.stdout),
            stderr=str(cp.stderr),
        )
    return cp.stdout


def run_json(cmd: list[str], *, timeout: int = 120) -> Any:
    """Run a command and parse stdout as JSON."""
    logger.info("$ %s", _fmt_cmd(cmd))
    out = run(cmd, timeout=timeout)
    try:
        return json.loads(out)
    except json.JSONDecodeError as e:
        decode_msg = "Invalid JSON output"
        raise ProcessError(decode_msg, code=0, stdout=out, stderr=str(e)) from e


def run_stream(cmd: list[str], *, bufsize: int = 1) -> Iterator[str]:
    """Run a command and yield stdout lines as they arrive.

    Caller must consume iterator; termination closes process. Any non-zero exit
    will raise ProcessError at the end (after stream drains) with captured stderr.
    """
    _precheck_cli(cmd)
    logger.info("$ %s", _fmt_cmd(cmd))
    proc = _popen_with_pipes(cmd, bufsize)
    stdout_iter = _get_stdout_iterator(proc)
    try:
        for line in stdout_iter:
            yield line.rstrip("\n")
    finally:
        rc, stdout_data, stderr_data = _finalize_process(proc)
        _raise_on_nonzero_rc(rc, stdout_data, stderr_data)


def _popen_with_pipes(cmd: list[str], bufsize: int) -> subprocess.Popen[str]:
    return subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=bufsize,
    )


def _get_stdout_iterator(proc: subprocess.Popen[str]) -> Iterator[str]:
    if proc.stdout is None:
        proc.kill()
        no_stdout_msg = "No stdout from process"
        raise ProcessError(no_stdout_msg, code=None, stdout="", stderr="")
    return proc.stdout


def _raise_on_nonzero_rc(rc: int | None, stdout_data: str, stderr_data: str) -> None:
    if rc not in (0, None):
        rc_msg = f"Command failed with exit code {rc}"
        raise ProcessError(rc_msg, code=rc, stdout=stdout_data or "", stderr=stderr_data or "")


def _log_failure(cp: subprocess.CompletedProcess[str], cmd: list[str]) -> None:
    logger.debug("Command failed (%s): %s", cp.returncode, " ".join(cmd))
    if cp.stdout:
        logger.debug("Stdout: %s", cp.stdout)
    if cp.stderr:
        logger.debug("Stderr: %s", cp.stderr)


def _finalize_process(proc: subprocess.Popen[str]) -> tuple[int | None, str, str]:
    stdout_data = ""
    stderr_data = ""
    try:
        stdout_data, stderr_data = proc.communicate(timeout=5)
    except (subprocess.TimeoutExpired, OSError):
        proc.kill()
    return proc.returncode, stdout_data, stderr_data
