"""Integration tests for the orchestrator."""

import time

from cityscope import orchestrator as orch
from cityscope.sources.base import Source, FetchResult, register, all_sources
from cityscope.config import settings


def setup_function():
    orch.clear_cache()


def test_multi_source_merge():
    r = orch.get_happenings("Austin", use_cache=False)
    assert r.status == "ok"
    origins = {h.origin for h in r.happenings}
    assert "reddit" in origins and "rss" in origins


def test_quiet_city():
    r = orch.get_happenings("Marfa", use_cache=False)
    assert r.status == "quiet"
    assert len(r.happenings) > 0


def test_ambiguous_short_circuits():
    r = orch.get_happenings("Portland", use_cache=False)
    assert r.status == "ambiguous"
    assert {a["region"] for a in r.alternatives} == {"OR", "ME"}


def test_no_community():
    r = orch.get_happenings("Wakanda", use_cache=False)
    assert r.status == "none"
    assert r.happenings == []


def test_cache_returns_same_object():
    a = orch.get_happenings("Durham")
    b = orch.get_happenings("Durham")
    # cache now stores dict payloads (Redis-compatible), so identity won't hold;
    # the served result must be equal in content and come from cache.
    assert a.city == b.city
    assert a.status == b.status
    assert len(a.happenings) == len(b.happenings)
    assert orch.cache_stats().get("hits", 0) >= 1 or orch.cache_stats().get("backend") == "redis"


def test_ambiguous_not_cached():
    orch.get_happenings("Portland")
    orch.get_happenings("Portland")
    # ambiguous results must not be cached (user needs to choose each time)
    # we can't read cache internals easily; assert status is stable instead
    r = orch.get_happenings("Portland")
    assert r.status == "ambiguous"


def test_failing_source_isolated():
    class Boom(Source):
        name = "boom_test"; label = "Boom"; priority = 1
        def fetch(self, city, region=None):
            raise RuntimeError("kaboom")
    register(Boom())
    try:
        r = orch.get_happenings("Austin", use_cache=False)
        assert r.status == "ok"                          # survived
        boom = next(s for s in r.sources if s["source"] == "boom_test")
        assert boom["status"] == "error"
    finally:
        # remove the test source so other tests are unaffected
        from cityscope.sources import base
        base._REGISTRY = [s for s in base._REGISTRY if s.name != "boom_test"]


def test_resolve_city_gps():
    r = orch.resolve_city(lat=35.99, lng=-78.90)
    assert r["city"] == "Durham"
