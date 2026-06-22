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
    # Existing (Austin path corrected to standard /feed/ — verified live 2026)
    "austin":     ("Austin Chronicle", "https://www.austinchronicle.com/feed/"),
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
    # New cities — Voice Media / New Times family, standard /feed/ path
    "losangeles": ("LA Weekly", "https://www.laweekly.com/feed/"),
    "denver":     ("Westword", "https://www.westword.com/feed/"),
    "nashville":  ("Nashville Scene", "https://www.nashvillescene.com/feed/"),
    "phoenix":    ("Phoenix New Times", "https://www.phoenixnewtimes.com/feed/"),
    "dallas":     ("Dallas Observer", "https://www.dallasobserver.com/feed/"),
    "houston":    ("Houston Press", "https://www.houstonpress.com/feed/"),
    "miami":      ("Miami New Times", "https://www.miaminewtimes.com/feed/"),
    "cleveland":  ("Cleveland Scene", "https://www.clevescene.com/feed/"),
    "orlando":    ("Orlando Weekly", "https://www.orlandoweekly.com/feed/"),
    "tampa":      ("Creative Loafing Tampa", "https://www.cltampa.com/feed/"),
    "detroit":    ("Detroit Metro Times", "https://www.metrotimes.com/feed/"),
    "lasvegas":   ("Las Vegas Weekly", "https://lasvegasweekly.com/feeds/headlines/"),
    "memphis":    ("Memphis Flyer", "https://www.memphisflyer.com/feed/"),
    "sanantonio": ("San Antonio Current", "https://www.sacurrent.com/feed/"),
    "spokane":    ("Pacific NW Inlander", "https://www.inlander.com/feed/"),
}

# Event-calendar feeds — dedicated "things to do" sites, distinct from
# newspapers. These are closer to the goal (lists of upcoming events). Seeded
# conservatively; expand/verify with the rss_discovery tool on a networked
# machine. Merged with _FALLBACK_FEEDS per city by get_city_feeds().
_EVENT_FEEDS = {
    "austin":     [("Do512", "https://do512.com/feed")],
}


def get_city_feeds(city_key: str) -> list[tuple[str, str]]:
    """Return [(source_name, feed_url), ...] for a city — newspaper feed(s)
    plus any event-calendar feeds."""
    if not db_enabled():
        feeds = []
        hit = _FALLBACK_FEEDS.get(city_key)
        if hit:
            feeds.append(hit)
        feeds.extend(_EVENT_FEEDS.get(city_key, []))
        return feeds
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
    "Los Angeles": (34.0522, -118.2437, "CA"), "Denver": (39.7392, -104.9903, "CO"),
    "Nashville": (36.1627, -86.7816, "TN"), "Phoenix": (33.4484, -112.0740, "AZ"),
    "Dallas": (32.7767, -96.7970, "TX"), "Houston": (29.7604, -95.3698, "TX"),
    "Miami": (25.7617, -80.1918, "FL"), "Cleveland": (41.4993, -81.6944, "OH"),
    "Orlando": (28.5383, -81.3792, "FL"), "Tampa": (27.9506, -82.4572, "FL"),
    "Detroit": (42.3314, -83.0458, "MI"), "Memphis": (35.1495, -90.0490, "TN"),
    "San Antonio": (29.4241, -98.4936, "TX"), "Spokane": (47.6588, -117.4260, "WA"),
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
