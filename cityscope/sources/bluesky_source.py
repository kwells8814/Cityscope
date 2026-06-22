"""Bluesky source — real people posting about a city, in real time.

This is the "boots on the ground" source that replaces what Reddit gave us:
informal, timely, word-of-mouth local chatter. Bluesky's AT Protocol exposes a
PUBLIC search endpoint that needs NO authentication, NO API key, and NO
approval — unlike Reddit. We query public posts mentioning the city alongside
event-ish terms, and feed them through the same classifier as every other
source.

Live mode (CITYSCOPE_LIVE_BLUESKY): calls the public AppView search API at
https://public.api.bsky.app. Mock mode: synthesizes plausible posts so the app
runs and tests pass with no network.

Endpoint (public, unauthenticated):
  GET https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts?q=...&limit=...

Rate limits are generous (thousands of requests per 5 min per IP); we cache and
pace anyway so we never come close.
"""

from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request

from ..config import settings
from ..core.logging_setup import get_logger
from ..core.resilience import with_retries, RetryableError
from ..models import RawPost
from .base import Source, FetchResult, register

logger = get_logger("source.bluesky")

_PUBLIC_API = "https://public.api.bsky.app"
_AUTH_API = "https://bsky.social"          # for creating an auth session
_SEARCH_PATH = "/xrpc/app.bsky.feed.searchPosts"
_SESSION_PATH = "/xrpc/com.atproto.server.createSession"
_UA = "cityscope/0.2 (local discovery; non-commercial)"

# Cached auth session (access token) so we don't log in on every request.
# Bluesky access tokens last ~2 hours; we refresh when expired.
_session: dict = {"token": None, "did": None, "pds": None, "obtained": 0.0}
_SESSION_TTL_S = 90 * 60   # refresh well before the ~2h expiry

# Event-ish terms we pair with the city to bias toward "things happening"
# rather than generic chatter. Kept short; the classifier does the fine sorting.
_QUERY_TERMS = ["tonight", "this weekend", "pop-up", "show", "market", "live music"]


_auth_error: str | None = None  # last auth failure reason, surfaced in diag


def _get_auth_token() -> str | None:
    """Return a valid access token if Bluesky credentials are configured.
    Logs in (creating a session) and caches the token. Returns None if no
    credentials are set — caller then falls back to the public endpoint."""
    global _auth_error
    handle = settings.bluesky_handle
    app_password = settings.bluesky_app_password
    if not handle or not app_password:
        _auth_error = "no_credentials"
        return None
    # tolerate common input mistakes: leading @, surrounding spaces
    handle = handle.strip().lstrip("@")
    app_password = app_password.strip()
    # reuse cached token if still fresh
    if _session["token"] and (time.time() - _session["obtained"]) < _SESSION_TTL_S:
        return _session["token"]
    try:
        body = json.dumps({"identifier": handle, "password": app_password}).encode()
        req = urllib.request.Request(
            f"{_AUTH_API}{_SESSION_PATH}", data=body,
            headers={"User-Agent": _UA, "Content-Type": "application/json"},
            method="POST")
        with urllib.request.urlopen(req, timeout=settings.source_timeout_s) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        # The session may tell us the account's PDS host via didDoc; authenticated
        # app.bsky reads work reliably through bsky.social (which proxies to the
        # AppView), so we default to that for the search host.
        _session.update(token=data.get("accessJwt"), did=data.get("did"),
                        pds=_AUTH_API, obtained=time.time())
        _auth_error = None
        logger.info("bluesky: authenticated session established")
        return _session["token"]
    except urllib.error.HTTPError as exc:
        # capture the body so we can see Bluesky's actual error message
        try:
            detail = exc.read().decode("utf-8")[:200]
        except Exception:
            detail = ""
        _auth_error = f"login_http_{exc.code}: {detail}"
        logger.warning("bluesky auth failed: %s %s", exc.code, detail)
        return None
    except Exception as exc:
        _auth_error = f"login_error: {type(exc).__name__}: {exc}"
        logger.warning("bluesky auth failed (will try public endpoint): %s", exc)
        return None



def _http_get_json(url: str, token: str | None = None) -> dict:
    def _do():
        headers = {"User-Agent": _UA, "Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=settings.source_timeout_s) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                raise RetryableError("bluesky 429 rate limited") from exc
            raise
    return with_retries(_do, retries=settings.http_retries,
                        backoff_base=settings.http_backoff_base_s,
                        retry_on=(RetryableError, urllib.error.URLError, OSError))


# Captures the outcome of the most recent live search for diagnostics, surfaced
# in the /happenings 'detail' so we can see what Bluesky actually returned on
# the live server (instead of guessing).
_last_diag: dict = {}


def _search_live(city: str, region: str | None) -> list[RawPost]:
    """Query Bluesky search for city posts. Uses an authenticated session if
    credentials are configured (more reliable from servers), otherwise falls
    back to the public no-auth endpoint."""
    posts: list[RawPost] = []
    seen: set[str] = set()
    token = _get_auth_token()
    # Host selection is the crux: the public AppView (public.api.bsky.app) now
    # returns 403 for server-side requests even WITH a token. Authenticated
    # app.bsky reads work when sent to bsky.social (the PDS/entryway), which
    # proxies to the AppView. So: authed -> bsky.social+token, else public AppView.
    base = (_session.get("pds") or _AUTH_API) if token else _PUBLIC_API
    creds_seen = bool(settings.bluesky_handle and settings.bluesky_app_password)
    diag = {"mode": "auth" if token else "public",
            "host": base,
            "creds_seen": creds_seen,
            "auth_error": _auth_error,
            "queries": [], "raw_total": 0, "errors": []}
    queries = [
        city,                                  # broadest: just the city name
        f"{city} tonight",
        f"{city} this weekend",
    ]
    for q in queries:
        params = urllib.parse.urlencode({"q": q, "limit": 25})
        url = f"{base}{_SEARCH_PATH}?{params}"
        try:
            data = _http_get_json(url, token=token)
        except Exception as exc:
            logger.warning("bluesky query failed (%s): %s", q, exc)
            diag["errors"].append(f"{q}: {type(exc).__name__}: {exc}")
            continue
        raw = data.get("posts", [])
        diag["queries"].append({"q": q, "got": len(raw)})
        diag["raw_total"] += len(raw)
        for item in raw:
            p = _normalise(item, city)
            if p and p.id not in seen:
                seen.add(p.id)
                posts.append(p)
    _last_diag.clear()
    _last_diag.update(diag)
    return posts


def _normalise(item: dict, city: str) -> RawPost | None:
    rec = item.get("record", {}) or {}
    text = (rec.get("text") or "").strip()
    if not text:
        return None
    author = item.get("author", {}) or {}
    handle = author.get("handle", "unknown")
    uri = item.get("uri", "")
    # build a web URL to the post: bsky.app/profile/<handle>/post/<rkey>
    rkey = uri.rsplit("/", 1)[-1] if uri else ""
    web_url = f"https://bsky.app/profile/{handle}/post/{rkey}" if rkey else f"https://bsky.app/profile/{handle}"
    created = rec.get("createdAt", "")
    created_ts = _parse_iso(created)
    return RawPost(
        id=uri or f"bsky_{handle}_{rkey}",
        source_label="Bluesky",
        title=text[:120],                 # first chunk as the headline
        body=text,
        url=web_url,
        score=int(item.get("likeCount", 0)),
        num_comments=int(item.get("replyCount", 0)),
        created_utc=created_ts,
        author=handle,
        origin="bluesky",
    )


def _parse_iso(s: str) -> float:
    if not s:
        return time.time()
    try:
        import datetime as dt
        s = s.replace("Z", "+00:00")
        return dt.datetime.fromisoformat(s).timestamp()
    except Exception:
        return time.time()


# --- mock mode (no network) ---

_MOCK = [
    ("event", "anyone going to the warehouse show in {city} tonight? doors at 9, byob",
     12, 4),
    ("gem", "found the best little taco spot in {city}, no sign, cash only, tucked behind the laundromat",
     48, 11),
    ("event", "free outdoor movie in {city} this weekend, bringing blankets, starts at sundown",
     27, 6),
    ("news", "the murals going up in {city} right now are unreal, whole block transformed",
     33, 5),
    ("event", "pop-up market in {city} saturday, like 40 local makers, found out by word of mouth",
     19, 3),
    ("noise", "why is parking in {city} impossible lately", 8, 14),
]


def _city_is_known(city: str) -> bool:
    """True if the city appears in the app's known data (gazetteer or feeds).
    Used only in mock mode to avoid fabricating posts for fictional cities."""
    key = city.strip().lower()
    try:
        from ..db.repository import _FALLBACK_CITIES, _FALLBACK_FEEDS
        known = {c.lower() for c in _FALLBACK_CITIES} | set(_FALLBACK_FEEDS)
        return key in known
    except Exception:
        return True  # if we can't check, don't suppress


def _search_mock(city: str) -> list[RawPost]:
    # In mock mode, only generate for cities that plausibly exist, so mock
    # behavior matches live (where a fake city returns nothing). We treat a city
    # as real if it's in the gazetteer/feed data the app knows about.
    if not _city_is_known(city):
        return []
    rng = random.Random(abs(hash("bsky:" + city.lower())) % (2**31))
    out = []
    for i, (_cat, tmpl, likes, replies) in enumerate(_MOCK):
        text = tmpl.format(city=city)
        age_h = rng.uniform(1, 48)
        out.append(RawPost(
            id=f"bsky_mock_{city.lower()}_{i}",
            source_label="Bluesky",
            title=text[:120],
            body=text,
            url=f"https://bsky.app/profile/user{i}.bsky.social/post/mock{i}",
            score=int(likes * rng.uniform(0.6, 1.4)),
            num_comments=int(replies * rng.uniform(0.6, 1.4)),
            created_utc=time.time() - age_h * 3600,
            author=f"user{i}.bsky.social",
            origin="bluesky",
        ))
    return out


class BlueskySource(Source):
    name = "bluesky"
    label = "Bluesky"
    priority = 15   # between reddit (10) and rss (20)

    def fetch(self, city: str, region: str | None = None) -> FetchResult:
        city = (city or "").strip()
        if not city:
            return FetchResult(self.name, [], "none", "No city given.")
        if settings.use_live_bluesky:
            try:
                posts = _search_live(city, region)
            except Exception as exc:
                logger.warning("bluesky fetch failed for %s: %s", city, exc)
                return FetchResult(self.name, [], "error", "Bluesky unavailable.")
        elif settings.demo_mode:
            posts = _search_mock(city)
        else:
            # production with Bluesky off: contribute nothing (no fake data)
            return FetchResult(self.name, [], "skipped", "Bluesky is off.")
        status = "ok" if posts else "none"
        note = (f"From Bluesky ({len(posts)} posts)." if posts
                else "No Bluesky chatter found.")
        detail = {"query_city": city}
        if settings.use_live_bluesky and _last_diag:
            detail["diag"] = dict(_last_diag)
        return FetchResult(self.name, posts, status, note, detail)


def register_bluesky():
    register(BlueskySource())
