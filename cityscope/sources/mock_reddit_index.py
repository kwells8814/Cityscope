"""Mock Reddit index — a search backend for tests and keyless standalone mode.

Implements the same two methods the live RedditClient exposes that discovery
needs: search_subreddits(query) and subreddit_about(name). This lets discovery
be tested deterministically and run with no network.
"""

from __future__ import annotations

_INDEX = [
    {"name": "Austin", "subscribers": 720000, "desc": "All things Austin, Texas", "active": True},
    {"name": "austinmusic", "subscribers": 41000, "desc": "Austin live music scene", "active": True},
    {"name": "austinfood", "subscribers": 88000, "desc": "Eating in Austin TX", "active": True},
    {"name": "AustinEvents", "subscribers": 12000, "desc": "Events around Austin", "active": True},
    {"name": "nyc", "subscribers": 980000, "desc": "New York City", "active": True},
    {"name": "FoodNYC", "subscribers": 210000, "desc": "Where to eat in NYC", "active": True},
    {"name": "AskNYC", "subscribers": 430000, "desc": "Questions about New York City", "active": True},
    {"name": "newyorkcity", "subscribers": 160000, "desc": "NYC photos and chatter", "active": True},
    {"name": "chicago", "subscribers": 640000, "desc": "The Windy City", "active": True},
    {"name": "chicagofood", "subscribers": 95000, "desc": "Chicago eats", "active": True},
    {"name": "chibeer", "subscribers": 22000, "desc": "Chicago craft beer", "active": True},
    {"name": "Seattle", "subscribers": 580000, "desc": "Seattle, Washington", "active": True},
    {"name": "SeattleWA", "subscribers": 210000, "desc": "Seattle area", "active": True},
    {"name": "SeattleMusic", "subscribers": 18000, "desc": "PNW shows and gigs", "active": True},
    {"name": "Portland", "subscribers": 520000, "desc": "Portland, Oregon", "active": True, "region": "OR"},
    {"name": "PortlandMusic", "subscribers": 16000, "desc": "PDX live music", "active": True, "region": "OR"},
    {"name": "askportland", "subscribers": 40000, "desc": "Portland OR questions", "active": True, "region": "OR"},
    {"name": "PortlandMaine", "subscribers": 34000, "desc": "Portland, Maine", "active": True, "region": "ME"},
    {"name": "asheville", "subscribers": 95000, "desc": "Asheville, NC mountain town", "active": True},
    {"name": "Boise", "subscribers": 130000, "desc": "Boise, Idaho", "active": True},
    {"name": "savannah", "subscribers": 47000, "desc": "Savannah, Georgia", "active": True},
    {"name": "bullcity", "subscribers": 38000, "desc": "Durham, North Carolina — the Bull City", "active": True},
    {"name": "Durham", "subscribers": 9000, "desc": "Durham NC (smaller, less active)", "active": True},
    {"name": "NOLA", "subscribers": 165000, "desc": "New Orleans, Louisiana", "active": True},
    {"name": "AskNOLA", "subscribers": 22000, "desc": "New Orleans questions", "active": True},
    {"name": "Pittsburgh", "subscribers": 240000, "desc": "Pittsburgh, PA — the Steel City", "active": True},
    {"name": "yinzer", "subscribers": 7000, "desc": "Pittsburgh slang and culture", "active": True},
    {"name": "twincities", "subscribers": 130000, "desc": "Minneapolis–St. Paul, Minnesota", "active": True},
    {"name": "vegas", "subscribers": 310000, "desc": "Las Vegas, Nevada", "active": True},
    {"name": "Marfa", "subscribers": 2100, "desc": "Marfa, Texas", "active": False},
    {"name": "AustinPowers", "subscribers": 30000, "desc": "Movie fan sub", "active": True},
    {"name": "PortlandTrailBlazers", "subscribers": 240000, "desc": "NBA team", "active": True},
    {"name": "chicagobulls", "subscribers": 380000, "desc": "NBA team", "active": True},
]


class MockRedditSearch:
    """Drop-in for RedditClient's discovery methods, backed by a static index."""

    def search_subreddits(self, query: str, limit: int = 25) -> list[dict]:
        q = query.strip().lower()
        return [s for s in _INDEX
                if q in s["name"].lower() or q in s["desc"].lower()][:limit]

    def subreddit_about(self, name: str) -> dict | None:
        nl = name.lower()
        return next((s for s in _INDEX if s["name"].lower() == nl), None)
