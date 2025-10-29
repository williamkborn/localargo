# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Core type definitions for the execution framework."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from collections.abc import Callable

    from localargo.config.manifest import UpManifest
    from localargo.core.argocd import ArgoClient


@dataclass
class StepStatus:
    """Status of an execution step."""

    state: Literal["pending", "completed", "failed", "skipped"]
    reason: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    @property
    def is_completed(self) -> bool:
        """Return True if step is in a completed state."""
        return self.state in ("completed", "skipped")


@dataclass
class ExecutionStep:
    """A single step in the execution plan."""

    name: str
    description: str
    check_function: Callable[[UpManifest, ArgoClient | None], StepStatus]
    execute_function: Callable[[UpManifest, ArgoClient | None], None]
    requires_client: bool = False

    def check(self, manifest: UpManifest, client: ArgoClient | None = None) -> StepStatus:
        """Check if this step needs to be executed."""
        return self.check_function(manifest, client)

    def execute(self, manifest: UpManifest, client: ArgoClient | None = None) -> None:
        """Execute this step."""
        self.execute_function(manifest, client)
