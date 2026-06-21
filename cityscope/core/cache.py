"""A small thread-safe TTL cache with LRU-ish eviction.

Used to avoid re-fetching the same city on every request. Deliberately
dependency-free and simple; swap for Redis in a multi-process deployment by
keeping this same get/set/clear interface.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any, Callable, Optional


class TTLCache:
    def __init__(self, ttl: float, max_entries: int = 500):
        self.ttl = ttl
        self.max_entries = max_entries
        self._store: "OrderedDict[str, tuple[float, Any]]" = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[Any]:
        now = time.time()
        with self._lock:
            item = self._store.get(key)
            if item is None:
                self.misses += 1
                return None
            ts, value = item
            if now - ts > self.ttl:
                # expired
                del self._store[key]
                self.misses += 1
                return None
            # mark as recently used
            self._store.move_to_end(key)
            self.hits += 1
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._store[key] = (time.time(), value)
            self._store.move_to_end(key)
            while len(self._store) > self.max_entries:
                self._store.popitem(last=False)  # evict oldest

    def get_or_set(self, key: str, producer: Callable[[], Any]) -> Any:
        """Return cached value or compute, store, and return it.

        The producer runs OUTSIDE the lock so a slow fetch doesn't block other
        keys. Last-write-wins on concurrent misses for the same key (acceptable
        for read-mostly happenings data).
        """
        cached = self.get(key)
        if cached is not None:
            return cached
        value = producer()
        self.set(key, value)
        return value

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def stats(self) -> dict:
        with self._lock:
            total = self.hits + self.misses
            return {
                "entries": len(self._store),
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": round(self.hits / total, 3) if total else 0.0,
            }
