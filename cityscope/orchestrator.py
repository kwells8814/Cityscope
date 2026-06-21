"""Orchestrator — cached, resilient, multi-source happenings for any city.

This is where robustness lives:
  - per-source timeout + error isolation (one bad source can't sink the request)
  - retries/backoff inside each source's HTTP client
  - TTL caching of the final result per (city, region)
  - graceful degradation: partial results + per-source status reported

resolve_city() / get_happenings() are the two entry points the API calls.
"""

from __future__ import annotations

from .config import settings
from .core.cache_backend import get_cache
from .core.logging_setup import get_logger
from .core.resilience import run_with_timeout
from .models import SourceReport, CityResult
from . import geocode, pipeline
from .db import repository as repo
from .sources.base import all_sources
from .sources.reddit_source import register_reddit
from .sources.rss_source import register_rss
from .sources.bluesky_source import register_bluesky

logger = get_logger("orchestrator")

# register sources once on import
register_reddit()
register_rss()
register_bluesky()

_happenings_cache = get_cache()


def resolve_city(*, city=None, zip_code=None, lat=None, lng=None) -> dict:
    return geocode.resolve(city=city, zip_code=zip_code, lat=lat, lng=lng)


def _dedupe(posts):
    seen, out = set(), []
    for p in posts:
        key = (p.origin, p.id)
        if key in seen or p.url in seen:
            continue
        seen.add(key); seen.add(p.url)
        out.append(p)
    return out


def _fetch_all_sources(city, region):
    """Run every source with timeout + error isolation. Returns (posts, reports, subreddits, ambiguous)."""
    posts, reports, subreddits = [], [], []
    for src in all_sources():
        try:
            res = run_with_timeout(lambda: src.fetch(city, region), settings.source_timeout_s)
        except TimeoutError:
            logger.warning("source %s timed out", src.name)
            reports.append(SourceReport(src.name, src.label, "error", 0,
                                        "Timed out.").to_dict())
            continue
        except Exception as exc:  # isolate any source failure
            logger.warning("source %s errored: %s", src.name, exc)
            reports.append(SourceReport(src.name, src.label, "error", 0,
                                        f"Source error: {exc}").to_dict())
            continue

        # Reddit ambiguity short-circuits the whole request
        if res.status == "ambiguous":
            return None, None, None, res

        if res.posts:
            posts.extend(res.posts)
        if src.name == "reddit":
            subreddits = res.detail.get("subreddits", [])
        reports.append(SourceReport(src.name, src.label, res.status,
                                    len(res.posts), res.note, res.detail).to_dict())
    return posts, reports, subreddits, None


def _build_result(city, region) -> CityResult:
    posts, reports, subreddits, ambiguous = _fetch_all_sources(city, region)

    if ambiguous is not None:
        return CityResult(city=city, region=region, status="ambiguous",
                          note=ambiguous.note, happenings=[],
                          alternatives=ambiguous.detail.get("alternatives", []),
                          sources=[])

    merged = _dedupe(posts)
    happenings = pipeline.process(merged)

    if not happenings:
        return CityResult(city=city, region=region, status="none",
                          note=f"Nothing found for {city} right now.",
                          happenings=[], sources=reports, subreddits=subreddits)

    contributing = [r for r in reports if r["count"] > 0]
    reddit_rep = next((r for r in reports if r["source"] == "reddit"), None)
    rss_rep = next((r for r in reports if r["source"] == "rss"), None)
    # "Quiet" means the city is genuinely thin: Reddit is quiet AND there's no
    # real local paper contributing. Bluesky is a universal source, so it alone
    # doesn't lift a city out of "quiet" — it's not a signal of local depth.
    rss_contributing = bool(rss_rep and rss_rep["count"] > 0)
    if reddit_rep and reddit_rep["status"] == "quiet" and not rss_contributing:
        status, note = "quiet", reddit_rep["note"]
    else:
        status = "ok"
        note = "Pulled from " + ", ".join(r["label"] for r in contributing) + "."

    return CityResult(city=city, region=region, status=status, note=note,
                      happenings=happenings, sources=reports, subreddits=subreddits)


def _result_from_payload(payload: dict) -> CityResult:
    """Rebuild a CityResult from a stored/cached dict payload."""
    return CityResult(
        city=payload.get("city", ""),
        region=payload.get("region"),
        status=payload.get("status", "ok"),
        note=payload.get("note", ""),
        happenings=payload.get("happenings", []),   # already dicts; fine for API
        subreddits=payload.get("subreddits", []),
        sources=payload.get("sources", []),
        alternatives=payload.get("alternatives", []),
    )


def get_happenings(city, region=None, *, use_cache=True) -> CityResult:
    """Cached entry point with a three-tier read path:
        1. Redis/in-memory cache (fast, short TTL)
        2. Postgres persisted fetch (survives restarts, shared across instances)
        3. live multi-source build (and write back to both tiers)
    Returns a CityResult.
    """
    city = (city or "").strip()
    if not city:
        return CityResult(city=city, region=region, status="none",
                          note="No city given.", happenings=[])

    key = f"{city.lower()}|{(region or '').lower()}"

    if use_cache:
        cached = _happenings_cache.get(key)
        if cached is not None:
            logger.info("cache hit: %s", key)
            # Redis returns a dict; in-memory returns a CityResult. Normalize.
            return cached if isinstance(cached, CityResult) else _result_from_payload(cached)

        # tier 2: persisted DB fetch (if DB enabled and fresh)
        payload = repo.load_city_fetch(key, settings.cache_ttl_happenings)
        if payload is not None:
            logger.info("db hit: %s", key)
            result = _result_from_payload(payload)
            _happenings_cache.set(key, result.to_dict())
            return result

    result = _build_result(city, region)

    # write back to cache + DB for ok/quiet (not ambiguous/none)
    if use_cache and result.status in ("ok", "quiet"):
        _happenings_cache.set(key, result.to_dict())
        repo.save_city_fetch(key, result.to_dict())
    return result


def cache_stats() -> dict:
    return _happenings_cache.stats()


def clear_cache() -> None:
    _happenings_cache.clear()
