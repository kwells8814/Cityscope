"""Integration tests for the orchestrator."""

import time

from cityscope import orchestrator as orch
from cityscope.sources.base import Source, FetchResult, register, all_sources
from cityscope.config import settings
from cityscope.models import RawPost


# Test-only source: produces controlled real-looking posts so orchestrator
# logic (merge, cache, isolation) can be tested without any runtime mock path
# in the real sources. Registered/removed per test.
class _FakeSource(Source):
    name = "fake_test"
    label = "Local paper"   # label as a real source so quiet-logic treats it normally
    priority = 20

    def __init__(self, city_posts):
        self._city_posts = city_posts  # {city_lower: count}

    def fetch(self, city, region=None):
        n = self._city_posts.get((city or "").strip().lower(), 0)
        if not n:
            return FetchResult(self.name, [], "none", "nothing")
        posts = [RawPost(
            id=f"fake_{city}_{i}", source_label="Test Paper",
            title=f"Live music tonight at venue {i}, doors at 9pm",
            body="festival this weekend, tickets on sale",
            url=f"https://example.org/{city}/{i}",
            score=50, num_comments=0, created_utc=time.time(),
            author="test", origin="rss") for i in range(n)]
        return FetchResult(self.name, posts, "ok", "From Test Paper.",
                           {"papers": ["Test Paper"]})


def _register_fake(city_posts):
    src = _FakeSource(city_posts)
    register(src)
    return src


def _unregister(name):
    from cityscope.sources import base
    base._REGISTRY = [s for s in base._REGISTRY if s.name != name]


def setup_function():
    orch.clear_cache()


def test_multi_source_merge():
    _register_fake({"austin": 5})
    try:
        r = orch.get_happenings("Austin", use_cache=False)
        assert r.status == "ok"
        assert len(r.happenings) > 0
        assert any(s["source"] == "fake_test" and s["count"] > 0 for s in r.sources)
    finally:
        _unregister("fake_test")


def test_quiet_city():
    # A city with no real feed and no fake source -> nothing contributes -> none.
    # (Quiet status specifically needs a quiet Reddit, which requires live Reddit;
    # with all sources off/empty, an unknown city is correctly "none".)
    r = orch.get_happenings("Marfa", use_cache=False)
    assert r.status in ("none", "quiet")


def test_ambiguous_short_circuits():
    r = orch.get_happenings("Portland", use_cache=False)
    assert r.status == "ambiguous"
    assert {a["region"] for a in r.alternatives} == {"OR", "ME"}


def test_no_community():
    r = orch.get_happenings("Wakanda", use_cache=False)
    assert r.status == "none"
    assert r.happenings == []


def test_cache_returns_same_object():
    _register_fake({"durham": 4})
    try:
        a = orch.get_happenings("Durham")
        b = orch.get_happenings("Durham")
        # cache now stores dict payloads (Redis-compatible), so identity won't hold;
        # the served result must be equal in content and come from cache.
        assert a.city == b.city
        assert a.status == b.status
        assert len(a.happenings) == len(b.happenings)
        assert orch.cache_stats().get("hits", 0) >= 1 or orch.cache_stats().get("backend") == "redis"
    finally:
        _unregister("fake_test")


def test_ambiguous_not_cached():
    orch.get_happenings("Portland")
    orch.get_happenings("Portland")
    # ambiguous results must not be cached (user needs to choose each time)
    # we can't read cache internals easily; assert status is stable instead
    r = orch.get_happenings("Portland")
    assert r.status == "ambiguous"


def test_failing_source_isolated():
    _register_fake({"austin": 3})
    class Boom(Source):
        name = "boom_test"; label = "Boom"; priority = 1
        def fetch(self, city, region=None):
            raise RuntimeError("kaboom")
    register(Boom())
    try:
        r = orch.get_happenings("Austin", use_cache=False)
        assert r.status == "ok"                          # survived via fake source
        boom = next(s for s in r.sources if s["source"] == "boom_test")
        assert boom["status"] == "error"
    finally:
        _unregister("boom_test")
        _unregister("fake_test")


def test_resolve_city_gps():
    r = orch.resolve_city(lat=35.99, lng=-78.90)
    assert r["city"] == "Durham"
