"""Tests for the TTL cache."""

import time

from cityscope.core.cache import TTLCache


def test_get_set_roundtrip():
    c = TTLCache(ttl=10)
    assert c.get("k") is None
    c.set("k", 42)
    assert c.get("k") == 42


def test_expiry():
    c = TTLCache(ttl=0.05)
    c.set("k", "v")
    assert c.get("k") == "v"
    time.sleep(0.08)
    assert c.get("k") is None


def test_lru_eviction():
    c = TTLCache(ttl=100, max_entries=2)
    c.set("a", 1)
    c.set("b", 2)
    c.get("a")            # touch a so b is oldest
    c.set("c", 3)         # evicts b
    assert c.get("a") == 1
    assert c.get("b") is None
    assert c.get("c") == 3


def test_get_or_set_computes_once():
    c = TTLCache(ttl=100)
    calls = {"n": 0}

    def producer():
        calls["n"] += 1
        return "computed"

    assert c.get_or_set("k", producer) == "computed"
    assert c.get_or_set("k", producer) == "computed"
    assert calls["n"] == 1     # second call served from cache


def test_stats_hit_rate():
    c = TTLCache(ttl=100)
    c.set("k", 1)
    c.get("k")        # hit
    c.get("missing")  # miss
    s = c.stats()
    assert s["hits"] == 1 and s["misses"] == 1
    assert s["hit_rate"] == 0.5
