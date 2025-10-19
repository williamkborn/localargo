"""Minimal retry/backoff utilities for transient failures."""

from __future__ import annotations

import random
import time
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:  # imported only for type checking
    from collections.abc import Callable

T = TypeVar("T")


# pylint: disable=too-many-arguments
def retry(
    func: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 5.0,
    jitter: float = 0.1,
    retry_on: tuple[type[Exception], ...] = (Exception,),
) -> T:  # pylint: disable=too-many-arguments
    """Retry a zero-arg callable with exponential backoff and jitter.

    Args:
        func (Callable[[], T]): Callable with no arguments to execute.
        attempts (int): Total attempts including the first try.
        base_delay (float): Initial delay in seconds.
        max_delay (float): Maximum delay cap in seconds.
        jitter (float): Proportional jitter to add/subtract from delay.
        retry_on (tuple[type[Exception], ...]): Exception types to retry on.

    Returns:
        T: The return value from ``func`` when it succeeds.

    Raises:
        RuntimeError: If attempts are exhausted; wraps the last exception if present.
    """
    last_exc: BaseException | None = None
    for i in range(attempts):
        try:
            return func()
        except retry_on as e:
            last_exc = e
            if i == attempts - 1:
                break
            delay = min(max_delay, base_delay * (2**i))
            jitter_amt = delay * jitter
            # Use random.random(); suppress security lint as this is non-crypto usage
            time.sleep(max(0.0, delay + (random.random() * 2 - 1) * jitter_amt))  # noqa: S311
    if last_exc is None:
        msg = "retry: exhausted attempts without result"
        raise RuntimeError(msg)
    # Wrap the final exception to provide a consistent, documented exception type
    final_msg = f"retry: failed after {attempts} attempts"
    raise RuntimeError(final_msg) from last_exc
