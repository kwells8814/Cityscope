"""Reddit source — discovery + fetch, live or mock depending on config.

Live mode (CITYSCOPE_LIVE_REDDIT): uses RedditClient for search + listings.
Mock mode: uses the static index for discovery and synthesizes posts.
Either way it returns RawPost[] and a per-source status.
"""

from __future__ import annotations

import time

from ..config import settings
from ..core.logging_setup import get_logger
from ..models import RawPost
from .base import Source, FetchResult, register
from . import discovery
from .mock_reddit_index import MockRedditSearch
from .mock_posts import generate_posts

logger = get_logger("source.reddit")


def _build_backend():
    if settings.use_live_reddit:
        from .reddit_client import RedditClient
        return RedditClient()
    return MockRedditSearch()


def _normalise_live(d: dict) -> RawPost:
    return RawPost(
        id=d.get("id", ""),
        source_label=d.get("subreddit", ""),
        title=d.get("title", "") or "",
        body=(d.get("selftext", "") or "")[:2000],
        url="https://reddit.com" + d.get("permalink", ""),
        score=int(d.get("score", 0)),
        num_comments=int(d.get("num_comments", 0)),
        created_utc=float(d.get("created_utc", time.time())),
        author=str(d.get("author", "")),
        origin="reddit",
    )


class RedditSource(Source):
    name = "reddit"
    label = "Reddit"
    priority = 10

    def __init__(self):
        self._backend = _build_backend()

    def fetch(self, city: str, region: str | None = None) -> FetchResult:
        disc = discovery.discover(self._backend, city, region=region)

        if disc["status"] == "ambiguous":
            return FetchResult(self.name, [], "ambiguous", disc["note"],
                               {"alternatives": disc["alternatives"], "city": disc["city"]})
        if disc["status"] == "none":
            return FetchResult(self.name, [], "none", disc["note"])

        subs = disc["subreddits"]
        if not settings.use_live_reddit:
            if settings.demo_mode:
                # explicit demo mode: synthesize sample posts
                posts = generate_posts(city, subs, disc["candidates"])
                return FetchResult(self.name, posts, disc["status"],
                                   disc["note"], {"subreddits": subs})
            # production: off means honestly empty, no fabricated data
            return FetchResult(self.name, [], "skipped",
                               "Reddit is off.", {"subreddits": subs})

        posts, seen = [], set()
        for sub in subs:
            for d in self._backend.fetch_listing(sub, "new", 50):
                p = _normalise_live(d)
                if p.id and p.id not in seen:
                    seen.add(p.id)
                    posts.append(p)

        return FetchResult(self.name, posts, disc["status"], disc["note"],
                           {"subreddits": subs})


def register_reddit():
    register(RedditSource())
