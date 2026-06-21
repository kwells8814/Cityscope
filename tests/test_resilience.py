"""Tests for resilience helpers."""

import pytest

from cityscope.core.resilience import (
    with_retries, run_with_timeout, RetryableError,
)


def test_succeeds_first_try():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        return "ok"

    assert with_retries(fn, retries=3, sleep=lambda s: None) == "ok"
    assert calls["n"] == 1


def test_retries_then_succeeds():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RetryableError("transient")
        return "ok"

    assert with_retries(fn, retries=5, sleep=lambda s: None) == "ok"
    assert calls["n"] == 3


def test_gives_up_after_retries():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise RetryableError("always")

    with pytest.raises(RetryableError):
        with_retries(fn, retries=3, sleep=lambda s: None)
    assert calls["n"] == 3


def test_non_retryable_propagates_immediately():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise ValueError("nope")

    with pytest.raises(ValueError):
        with_retries(fn, retries=3, retry_on=(RetryableError,), sleep=lambda s: None)
    assert calls["n"] == 1


def test_timeout_raises():
    import time

    def slow():
        time.sleep(2)
        return "done"

    with pytest.raises(TimeoutError):
        run_with_timeout(slow, 0.2)


def test_timeout_passes_fast():
    assert run_with_timeout(lambda: "quick", 1.0) == "quick"
