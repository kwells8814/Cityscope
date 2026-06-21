"""Repository layer — the single place the app reads curated config + persisted
fetches. Falls back to the hardcoded Python data when the DB is disabled, so
behavior is identical with or without Postgres (just not editable-at-runtime
without it).

Callers (discovery, rss_source, geocode, orchestrator) use these functions
instead of importing the hardcoded dicts directly.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from ..core.logging_setup import get_logger
from .engine import db_enabled, session_scope

logger = get_logger("db.repo")


# --- curated config: aliases (nicknames) ------------------------------------

# hardcoded fallbacks (same data as before, used when DB is off)
_FALLBACK_ALIASES = {
    "durham": ["bullcity"],
    "neworleans": ["NOLA", "AskNOLA"],
    "pittsburgh": ["yinzer"],
    "minneapolis": ["twincities"],
    "stpaul": ["twincities"],
    "lasvegas": ["vegas"],
    "sanfrancisco": ["bayarea"],
    "philadelphia": ["philly"],
}


def get_city_aliases(city_key: str) -> list[str]:
    if not db_enabled():
        return list(_FALLBACK_ALIASES.get(city_key, []))
    from .models import CityAlias
    with session_scope() as s:
        rows = s.query(CityAlias).filter(CityAlias.city_key == city_key).all()
        return [r.subreddit for r in rows]


# --- curated config: RSS feeds ----------------------------------------------

_FALLBACK_FEEDS = {
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


def get_city_feeds(city_key: str) -> list[tuple[str, str]]:
    """Return [(paper, feed_url), ...] for a city."""
    if not db_enabled():
        hit = _FALLBACK_FEEDS.get(city_key)
        return [hit] if hit else []
    from .models import CityFeed
    with session_scope() as s:
        rows = (s.query(CityFeed)
                .filter(CityFeed.city_key == city_key, CityFeed.active.is_(True)).all())
        return [(r.paper, r.feed_url) for r in rows]


# --- curated config: gazetteer + zips ---------------------------------------

_FALLBACK_CITIES = {
    "Austin": (30.2672, -97.7431, "TX"), "Portland": (45.5152, -122.6784, "OR"),
    "NYC": (40.7128, -74.0060, "NY"), "Chicago": (41.8781, -87.6298, "IL"),
    "Seattle": (47.6062, -122.3321, "WA"), "Asheville": (35.5951, -82.5515, "NC"),
    "Durham": (35.9940, -78.8986, "NC"), "Boise": (43.6150, -116.2023, "ID"),
    "Savannah": (32.0809, -81.0912, "GA"), "Marfa": (30.3094, -104.0205, "TX"),
    "New Orleans": (29.9511, -90.0715, "LA"), "Pittsburgh": (40.4406, -79.9959, "PA"),
    "Las Vegas": (36.1699, -115.1398, "NV"),
}
_FALLBACK_ZIPS = {
    "78701": ("Austin", "TX"), "97201": ("Portland", "OR"), "04101": ("Portland", "ME"),
    "10001": ("NYC", "NY"), "60601": ("Chicago", "IL"), "98101": ("Seattle", "WA"),
    "28801": ("Asheville", "NC"), "27701": ("Durham", "NC"), "83702": ("Boise", "ID"),
    "31401": ("Savannah", "GA"), "70112": ("New Orleans", "LA"),
    "15222": ("Pittsburgh", "PA"), "89101": ("Las Vegas", "NV"),
}


def get_gazetteer() -> dict[str, tuple[float, float, str]]:
    if not db_enabled():
        return dict(_FALLBACK_CITIES)
    from .models import GazetteerCity
    with session_scope() as s:
        return {r.name: (r.lat, r.lng, r.region) for r in s.query(GazetteerCity).all()}


def get_zip(zip_code: str) -> Optional[tuple[str, str]]:
    if not db_enabled():
        return _FALLBACK_ZIPS.get(zip_code)
    from .models import ZipCode
    with session_scope() as s:
        row = s.get(ZipCode, zip_code)
        return (row.city, row.region) if row else None


# --- operational: persisted fetches -----------------------------------------

def load_city_fetch(city_key: str, max_age_s: int) -> Optional[dict]:
    """Return a stored CityResult payload if present and fresh, else None."""
    if not db_enabled():
        return None
    from .models import CityFetch
    with session_scope() as s:
        row = s.query(CityFetch).filter(CityFetch.city_key == city_key).one_or_none()
        if row is None:
            return None
        age = (datetime.now(timezone.utc) - row.fetched_at).total_seconds()
        if age > max_age_s:
            return None
        return row.payload


def save_city_fetch(city_key: str, payload: dict) -> None:
    """Upsert a fetched city's result (one row per city_key)."""
    if not db_enabled():
        return
    from .models import CityFetch
    with session_scope() as s:
        row = s.query(CityFetch).filter(CityFetch.city_key == city_key).one_or_none()
        count = len(payload.get("happenings", []))
        if row is None:
            row = CityFetch(city_key=city_key)
            s.add(row)
        row.city = payload.get("city", "")
        row.region = payload.get("region")
        row.status = payload.get("status", "ok")
        row.payload = payload
        row.happening_count = count
        row.fetched_at = datetime.now(timezone.utc)
