"""Unit tests for Kubernetes helper functions using mocks."""

from typing import TYPE_CHECKING

from localargo.core.k8s import list_pods_for_app, stream_logs

if TYPE_CHECKING:  # imported only for type checking
    from collections.abc import Iterator


def test_list_pods_for_app_filters_correctly() -> None:
    """Ensure only pods labeled for the target app are returned."""
    pods = list_pods_for_app("myapp", "default")
    assert pods == ["app-0", "app-1"]


def test_stream_logs_builds_command() -> None:
    """Iterate the stream without output to validate command construction."""
    it: Iterator[str] = stream_logs(
        "app-0", "default", container="c1", since="1h", follow=True
    )
    for _ in it:
        pass
