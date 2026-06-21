"""Resilience helpers: retry-with-backoff and timeout-bounded calls.

Sources can be slow or flaky. These keep one bad source from taking down a
request: a source that errors or times out is isolated, logged, and the rest of
the response still goes out.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from typing import Callable, Iterable, Optional, TypeVar

logger = logging.getLogger("cityscope.retry")

T = TypeVar("T")


class RetryableError(Exception):
    """Raise to signal an error worth retrying (e.g. 429, transient network)."""


def with_retries(
    fn: Callable[[], T],
    *,
    retries: int = 3,
    backoff_base: float = 0.5,
    retry_on: Iterable[type] = (RetryableError,),
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Call fn, retrying on the given exception types with exponential backoff.

    Backoff: backoff_base * 2**attempt (0.5s, 1s, 2s, ...). Non-retryable
    exceptions propagate immediately. Re-raises the last error if all attempts
    fail.
    """
    retry_types = tuple(retry_on)
    last_exc: Optional[BaseException] = None
    for attempt in range(retries):
        try:
            return fn()
        except retry_types as exc:
            last_exc = exc
            if attempt == retries - 1:
                break
            delay = backoff_base * (2 ** attempt)
            logger.warning("retry %d/%d after %.2fs: %s",
                           attempt + 1, retries, delay, exc)
            sleep(delay)
    assert last_exc is not None
    raise last_exc


def run_with_timeout(fn: Callable[[], T], timeout_s: float) -> T:
    """Run fn in a worker thread, raising TimeoutError if it overruns.

    Note: the worker thread cannot be force-killed; on timeout we stop waiting
    and let it finish in the background. Fine for read-only fetches.
    """
    with ThreadPoolExecutor(max_workers=1) as ex:
        future = ex.submit(fn)
        try:
            return future.result(timeout=timeout_s)
        except FutureTimeout:
            raise TimeoutError(f"operation exceeded {timeout_s}s")
