"""Local RSS / alt-weekly source.

Live mode (CITYSCOPE_LIVE_RSS): fetches + parses real RSS feeds. Uses
feedparser if available, falling back to stdlib xml parsing so it works without
the dependency. Mock mode: synthesizes alt-weekly-style entries.

CITY_FEEDS maps a city to its alt-weekly RSS URL(s). Grow as you add cities.
"""

from __future__ import annotations

import time
import random

from ..config import settings
from ..core.logging_setup import get_logger
from ..core.resilience import with_retries, RetryableError
from ..models import RawPost
from .base import Source, FetchResult, register

logger = get_logger("source.rss")

# city -> (display name, feed url). In live mode the URL is fetched; in mock
# mode only the display name is used. Real URLs filled in for a few examples.
CITY_FEEDS = {
    "austin":     ("Austin Chronicle", "https://www.austinchronicle.com/feeds/events/"),
    "portland":   ("Willamette Week", "https://www.wweek.com/feed/"),
    "nyc":        ("The Village Voice", "https://www.villagevoice.com/feed/"),
    "chicago":    ("Chicago Reader", "https://chicagoreader.com/feed/"),
    "seattle":    ("The Stranger", "https://www.thestranger.com/feeds/"),
    "asheville":  ("Mountain Xpress", "https://mountainx.com/feed/"),
    "durham":     ("INDY Week", "https://indyweek.com/feed/"),
    "savannah":   ("Connect Savannah", "https://www.connectsavannah.com/feed/"),
    "neworleans": ("Gambit", "https://www.nola.com/gambit/feed/"),
    "pittsburgh": ("Pittsburgh City Paper", "https://www.pghcitypaper.com/feed/"),
    "boise":      ("Boise Weekly", "https://www.boiseweekly.com/feed/"),
}

_MOCK_TEMPLATES = [
    ("{paper} Picks: {city} gallery crawl this Friday night",
     "Dozens of galleries open late downtown {city}, free, 6–10pm."),
    ("Live this weekend in {city}: indie showcase at the old theater",
     "Three local bands Saturday, doors 8pm, $12 advance. All ages until 10."),
    ("{city} farmers + makers market returns Sunday morning",
     "Produce, crafts, coffee, 8am–1pm at the riverfront lot. Free, dog friendly."),
    ("Food truck festival rolls into {city} this Saturday",
     "40+ trucks, live DJ, beer garden. Noon–9pm, free entry."),
    ("Outdoor film series kicks off in {city} Thursday",
     "A cult classic under the stars, 8:30pm, bring a chair. Free, donations welcome."),
]


def _parse_feed(url: str) -> list[dict]:
    """Fetch + parse an RSS feed into entry dicts. Prefers feedparser."""
    def _do():
        try:
            import feedparser  # type: ignore
            parsed = feedparser.parse(url)
            return [{"title": e.get("title", ""),
                     "summary": e.get("summary", ""),
                     "link": e.get("link", ""),
                     "published": e.get("published_parsed")}
                    for e in parsed.entries]
        except ImportError:
            # stdlib fallback
            import urllib.request, xml.etree.ElementTree as ET
            req = urllib.request.Request(url, headers={"User-Agent": "cityscope/0.2"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                root = ET.fromstring(resp.read())
            out = []
            for item in root.iter("item"):
                out.append({"title": item.findtext("title", ""),
                            "summary": item.findtext("description", ""),
                            "link": item.findtext("link", ""),
                            "published": None})
            return out
    return with_retries(_do, retries=settings.http_retries,
                        backoff_base=settings.http_backoff_base_s,
                        retry_on=(RetryableError, OSError))


def _mock_entries(city: str, paper: str) -> list[dict]:
    rng = random.Random(abs(hash("rss:" + city.lower())) % (2**31))
    chosen = rng.sample(_MOCK_TEMPLATES, min(5, len(_MOCK_TEMPLATES)))
    entries = []
    for i, (title, summary) in enumerate(chosen):
        published = time.time() - rng.uniform(0, 3 * 86400)
        entries.append({"title": title.format(city=city, paper=paper),
                        "summary": summary.format(city=city, paper=paper),
                        "link": f"https://altweekly.example/{city.lower()}/{i}",
                        "published": published})
    return entries


def _to_post(entry: dict, idx: int, city: str, paper: str) -> RawPost:
    pub = entry.get("published")
    if isinstance(pub, (int, float)):
        created = float(pub)
    elif pub and hasattr(pub, "__getitem__"):
        try:
            created = time.mktime(pub)  # struct_time from feedparser
        except Exception:
            created = time.time()
    else:
        created = time.time()
    return RawPost(
        id=f"rss_{city.lower().replace(' ', '')}_{idx}",
        source_label=paper,
        title=entry.get("title", "") or "",
        body=entry.get("summary", "") or "",
        url=entry.get("link", "") or "",
        score=60,
        num_comments=0,
        created_utc=created,
        author=paper,
        origin="rss",
    )


class RSSSource(Source):
    name = "rss"
    label = "Local paper"
    priority = 20

    def fetch(self, city: str, region: str | None = None) -> FetchResult:
        key = (city or "").strip().lower()
        from ..db.repository import get_city_feeds
        feeds = get_city_feeds(key)
        if not feeds:
            return FetchResult(self.name, [], "none",
                               f"No local paper feed for {city} yet.")
        paper, url = feeds[0]
        if settings.use_live_rss:
            try:
                entries = _parse_feed(url)
            except Exception as exc:
                logger.warning("RSS fetch failed for %s: %s", city, exc)
                return FetchResult(self.name, [], "error",
                                   f"{paper} feed unavailable.")
        else:
            entries = _mock_entries(city, paper)
        posts = [_to_post(e, i, city, paper) for i, e in enumerate(entries)]
        return FetchResult(self.name, posts, "ok" if posts else "none",
                           f"From {paper}." if posts else f"{paper} had nothing.",
                           {"papers": [paper]})


def register_rss():
    register(RSSSource())
