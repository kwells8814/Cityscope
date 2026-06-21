"""Cache backend selection: Redis (shared) or in-memory TTLCache (fallback).

The orchestrator calls get_cache() and uses a uniform interface
(get/set/clear/stats), so swapping Redis in or out is invisible to callers.

- REDIS_URL set  -> RedisCache (shared across all app instances)
- REDIS_URL unset -> the in-process TTLCache (fine for a single instance / local)

Values are JSON-serialized for Redis. We store CityResult.to_dict() dicts, so
they round-trip cleanly.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ..config import settings
from .cache import TTLCache
from .logging_setup import get_logger

logger = get_logger("cache.backend")


class RedisCache:
    """Thin wrapper over redis-py giving the same surface as TTLCache."""

    def __init__(self, url: str, ttl: int):
        import redis  # imported only when actually used
        self._r = redis.Redis.from_url(url, decode_responses=True)
        self.ttl = ttl
        self._prefix = "cs:happenings:"
        # fail fast if the server is unreachable, so we can fall back at startup
        self._r.ping()

    def get(self, key: str) -> Optional[Any]:
        raw = self._r.get(self._prefix + key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return None

    def set(self, key: str, value: Any) -> None:
        self._r.set(self._prefix + key, json.dumps(value), ex=self.ttl)

    def clear(self) -> None:
        # only clears our namespace, not the whole Redis db
        keys = list(self._r.scan_iter(self._prefix + "*"))
        if keys:
            self._r.delete(*keys)

    def stats(self) -> dict:
        try:
            info = self._r.info(section="stats")
            hits = info.get("keyspace_hits", 0)
            misses = info.get("keyspace_misses", 0)
            total = hits + misses
            return {"backend": "redis", "hits": hits, "misses": misses,
                    "hit_rate": round(hits / total, 3) if total else 0.0}
        except Exception:
            return {"backend": "redis"}


_cache_singleton = None


def get_cache():
    """Return the process-wide cache backend (Redis if configured, else memory)."""
    global _cache_singleton
    if _cache_singleton is not None:
        return _cache_singleton

    if settings.redis_url:
        try:
            _cache_singleton = RedisCache(settings.redis_url, settings.cache_ttl_happenings)
            logger.info("cache backend: redis")
            return _cache_singleton
        except Exception as exc:
            logger.warning("redis unavailable (%s); falling back to in-memory cache", exc)

    _cache_singleton = TTLCache(settings.cache_ttl_happenings, settings.cache_max_entries)
    # tag the in-memory stats so /health can tell which backend is live
    _orig_stats = _cache_singleton.stats
    _cache_singleton.stats = lambda: {**_orig_stats(), "backend": "memory"}
    logger.info("cache backend: in-memory")
    return _cache_singleton


def reset_cache_singleton():
    """For tests."""
    global _cache_singleton
    _cache_singleton = None
