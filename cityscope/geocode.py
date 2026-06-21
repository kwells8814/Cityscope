"""Geocoding — ZIP/GPS/name -> city (+ region).

Live mode (CITYSCOPE_LIVE_GEOCODE) uses free public geocoders:
  - GPS reverse:  US Census geocoder (no key) for US coords
  - ZIP:          a ZIP->city lookup
Mock mode uses a small built-in gazetteer so it runs with no network.
"""

from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request

from .config import settings
from .core.logging_setup import get_logger

logger = get_logger("geocode")

_CITIES = {
    "Austin": (30.2672, -97.7431, "TX"),
    "Portland": (45.5152, -122.6784, "OR"),
    "NYC": (40.7128, -74.0060, "NY"),
    "Chicago": (41.8781, -87.6298, "IL"),
    "Seattle": (47.6062, -122.3321, "WA"),
    "Asheville": (35.5951, -82.5515, "NC"),
    "Durham": (35.9940, -78.8986, "NC"),
    "Boise": (43.6150, -116.2023, "ID"),
    "Savannah": (32.0809, -81.0912, "GA"),
    "Marfa": (30.3094, -104.0205, "TX"),
    "New Orleans": (29.9511, -90.0715, "LA"),
    "Pittsburgh": (40.4406, -79.9959, "PA"),
    "Las Vegas": (36.1699, -115.1398, "NV"),
}

_ZIP_TO_CITY = {
    "78701": ("Austin", "TX"), "97201": ("Portland", "OR"),
    "04101": ("Portland", "ME"), "10001": ("NYC", "NY"),
    "60601": ("Chicago", "IL"), "98101": ("Seattle", "WA"),
    "28801": ("Asheville", "NC"), "27701": ("Durham", "NC"),
    "83702": ("Boise", "ID"), "31401": ("Savannah", "GA"),
    "70112": ("New Orleans", "LA"), "15222": ("Pittsburgh", "PA"),
    "89101": ("Las Vegas", "NV"),
}


def _haversine(a, b, c, d):
    R = 6371.0
    p1, p2 = math.radians(a), math.radians(c)
    dphi = math.radians(c - a)
    dl = math.radians(d - b)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def _nearest(lat, lng):
    from .db.repository import get_gazetteer
    cities = get_gazetteer()
    best, bd = None, float("inf")
    for name, (clat, clng, region) in cities.items():
        dist = _haversine(lat, lng, clat, clng)
        if dist < bd:
            bd, best = dist, (name, region, dist)
    return best


def _census_reverse(lat, lng):
    """US Census reverse geocode (no key). Returns (city, state) or None."""
    url = ("https://geocoding.geo.census.gov/geocoder/geographies/coordinates?"
           + urllib.parse.urlencode({
               "x": lng, "y": lat, "benchmark": "Public_AR_Current",
               "vintage": "Current_Current", "format": "json"}))
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        geos = data.get("result", {}).get("geographies", {})
        places = geos.get("Incorporated Places") or geos.get("Census Designated Places")
        states = geos.get("States")
        city = places[0]["NAME"] if places else None
        state = states[0].get("STUSAB") if states else None
        return (city, state) if city else None
    except Exception as exc:
        logger.warning("census reverse geocode failed: %s", exc)
        return None


def resolve(*, city=None, zip_code=None, lat=None, lng=None) -> dict:
    """Return {city, region, source, note}. Priority: city > zip > gps."""
    if city:
        return {"city": city.strip(), "region": None, "source": "name", "note": None}

    if zip_code:
        z = str(zip_code).strip()[:5]
        from .db.repository import get_zip
        hit = get_zip(z)
        if hit:
            return {"city": hit[0], "region": hit[1], "source": "zip", "note": None}
        return {"city": None, "region": None, "source": "zip",
                "note": f"ZIP {z} not recognized. Try a city name."}

    if lat is not None and lng is not None:
        lat, lng = float(lat), float(lng)
        if settings.use_live_geocode:
            got = _census_reverse(lat, lng)
            if got:
                return {"city": got[0], "region": got[1], "source": "gps", "note": None}
            # fall through to nearest-city if the live lookup misses
        name, region, dist = _nearest(lat, lng)
        note = (f"Nearest covered city is {name} (~{dist:.0f} km away)."
                if dist > 60 else None)
        return {"city": name, "region": region, "source": "gps", "note": note}

    return {"city": None, "region": None, "source": "none",
            "note": "Need a city, ZIP, or location."}
