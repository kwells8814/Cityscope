"""Live Reddit HTTP client (stdlib urllib, no third-party deps).

Real OAuth client-credentials flow, token caching, conservative rate limiting,
429 backoff, and the required User-Agent. Used only when CITYSCOPE_LIVE_REDDIT
is on; otherwise the Reddit source uses synthesized mock posts.

Compliance: OAuth required, descriptive UA, you must purge content deleted from
Reddit (this client holds nothing persistently).
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from ..config import settings
from ..core.logging_setup import get_logger
from ..core.resilience import RetryableError, with_retries

logger = get_logger("reddit.client")

_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
_API_BASE = "https://oauth.reddit.com"


class RedditConfigError(RuntimeError):
    """Missing/invalid credentials."""


class RedditClient:
    def __init__(self):
        self._lock = threading.Lock()
        self._token = None
        self._token_expiry = 0.0
        self._last_request = 0.0
        self._min_interval = 60.0 / max(settings.reddit_qpm, 1)

    # --- helpers ---
    def _user_agent(self) -> str:
        return f"python:cityscope:0.2 (by /u/{settings.reddit_username})"

    def _require_creds(self):
        if not settings.reddit_client_id or not settings.reddit_client_secret:
            raise RedditConfigError(
                "Missing REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET. "
                "Create a 'script' app at https://www.reddit.com/prefs/apps"
            )

    def _throttle(self):
        with self._lock:
            wait = self._min_interval - (time.time() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.time()

    # --- auth ---
    def _get_token(self) -> str:
        with self._lock:
            if self._token and time.time() < self._token_expiry - 60:
                return self._token
        self._require_creds()
        self._throttle()
        data = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode()
        req = urllib.request.Request(_TOKEN_URL, data=data,
                                     headers={"User-Agent": self._user_agent()})
        auth = urllib.request.HTTPBasicAuthHandler()
        auth.add_password("reddit", _TOKEN_URL,
                          settings.reddit_client_id, settings.reddit_client_secret)
        opener = urllib.request.build_opener(auth)
        try:
            with opener.open(req, timeout=15) as resp:
                payload = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            raise RedditConfigError(
                f"OAuth failed ({exc.code}). Check credentials and app type 'script'."
            ) from exc
        with self._lock:
            self._token = payload["access_token"]
            self._token_expiry = time.time() + payload.get("expires_in", 3600)
            return self._token

    # --- requests ---
    def _do_get(self, path: str, params: dict | None = None):
        token = self._get_token()
        url = _API_BASE + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        self._throttle()
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": self._user_agent(),
        })
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                raise RetryableError("reddit 429 rate limited") from exc
            if exc.code in (401, 403):
                # force token refresh and let retry try again
                with self._lock:
                    self._token = None
                raise RetryableError(f"reddit auth {exc.code}") from exc
            raise

    def get(self, path: str, params: dict | None = None):
        return with_retries(
            lambda: self._do_get(path, params),
            retries=settings.http_retries,
            backoff_base=settings.http_backoff_base_s,
        )

    # --- high level ---
    def search_subreddits(self, query: str, limit: int = 25) -> list[dict]:
        payload = self.get("/subreddits/search",
                           {"q": query, "limit": limit, "include_over_18": "false"})
        return [c["data"] for c in payload.get("data", {}).get("children", [])]

    def subreddit_about(self, name: str) -> dict | None:
        try:
            d = self.get(f"/r/{name}/about")["data"]
            return {"name": d["display_name"], "subscribers": d.get("subscribers", 0),
                    "desc": d.get("public_description", ""), "active": True}
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise

    def fetch_listing(self, sub: str, listing: str = "new", limit: int = 50) -> list[dict]:
        try:
            payload = self.get(f"/r/{sub}/{listing}", {"limit": limit})
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 404):
                return []
            raise
        return [c["data"] for c in payload.get("data", {}).get("children", [])
                if c.get("kind") == "t3"]
