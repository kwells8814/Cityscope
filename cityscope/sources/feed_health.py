"""Feed health tracking — self-healing for RSS feeds.

Goal: a feed that goes dead should never repeatedly slow down requests or risk
dropping a city silently. We track each feed's recent success/failure. After a
feed fails enough times in a row it's marked "cooling" and skipped on most
requests — but we periodically let one request retry it, so if the feed comes
back (or its host recovers) it heals automatically.

This is in-memory (per process). It resets on redeploy, which is fine: the
worst case is we re-learn a feed is dead after a restart. No external storage,
no cost. A snapshot is exposed via the orchestrator for a /feed-health endpoint.
"""

from __future__ import annotations

import time
import threading

from ..core.logging_setup import get_logger

logger = get_logger("feed.health")

# Tuning knobs.
_FAIL_THRESHOLD = 3          # consecutive fails before a feed starts "cooling"
_COOLDOWN_S = 30 * 60        # how long to skip a cooling feed between retries
_lock = threading.Lock()

# url -> {"fails": int, "last_fail": ts, "last_ok": ts, "last_try": ts,
#         "paper": str, "cooling": bool}
_state: dict[str, dict] = {}


def _entry(url: str, paper: str = "") -> dict:
    e = _state.get(url)
    if e is None:
        e = {"fails": 0, "last_fail": 0.0, "last_ok": 0.0, "last_try": 0.0,
             "paper": paper, "cooling": False}
        _state[url] = e
    if paper and not e["paper"]:
        e["paper"] = paper
    return e


def should_skip(url: str, paper: str = "") -> bool:
    """Return True if this feed is cooling and we should skip it this time.
    We still let it retry once per cooldown window so it can self-heal."""
    now = time.time()
    with _lock:
        e = _entry(url, paper)
        if not e["cooling"]:
            return False
        # Allow a retry if enough time has passed since the last attempt.
        if now - e["last_try"] >= _COOLDOWN_S:
            e["last_try"] = now
            return False  # let this request retry it (self-heal probe)
        return True


def record_ok(url: str, paper: str = "") -> None:
    now = time.time()
    with _lock:
        e = _entry(url, paper)
        was_cooling = e["cooling"]
        e["fails"] = 0
        e["last_ok"] = now
        e["last_try"] = now
        e["cooling"] = False
    if was_cooling:
        logger.info("feed recovered, healed: %s (%s)", paper or url, url)


def record_fail(url: str, paper: str = "") -> None:
    now = time.time()
    with _lock:
        e = _entry(url, paper)
        e["fails"] += 1
        e["last_fail"] = now
        e["last_try"] = now
        if e["fails"] >= _FAIL_THRESHOLD and not e["cooling"]:
            e["cooling"] = True
            logger.warning("feed marked cooling after %d fails: %s (%s)",
                           e["fails"], paper or url, url)


def snapshot() -> dict:
    """A health summary for the /feed-health endpoint."""
    now = time.time()
    healthy, cooling = [], []
    with _lock:
        for url, e in _state.items():
            row = {
                "paper": e["paper"],
                "url": url,
                "fails": e["fails"],
                "cooling": e["cooling"],
                "minutes_since_ok": round((now - e["last_ok"]) / 60, 1) if e["last_ok"] else None,
                "minutes_since_fail": round((now - e["last_fail"]) / 60, 1) if e["last_fail"] else None,
            }
            (cooling if e["cooling"] else healthy).append(row)
    return {
        "tracked": len(_state),
        "healthy": len(healthy),
        "cooling": len(cooling),
        "cooling_feeds": cooling,    # the ones needing a human look
    }
