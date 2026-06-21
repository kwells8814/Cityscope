"""Subreddit discovery — nickname-aware, works for any city.

Takes a `search_backend` with two methods (search_subreddits, subreddit_about),
so it works identically against the live RedditClient or the mock index. This
is what makes discovery both production-capable and unit-testable.
"""

from __future__ import annotations

import math
import re

_TOPICAL_SUFFIXES = ["food", "music", "events", "eats", "beer", "art"]

_CITY_NICKNAME_SUBS = {
    "durham": ["bullcity"],
    "neworleans": ["NOLA", "AskNOLA"],
    "pittsburgh": ["yinzer"],
    "minneapolis": ["twincities"],
    "stpaul": ["twincities"],
    "lasvegas": ["vegas"],
    "sanfrancisco": ["bayarea"],
    "philadelphia": ["philly"],
}

_REJECT_PATTERNS = [
    r"powers$", r"trailblazers$", r"bulls$", r"\bnba\b", r"\bnfl\b",
    r"redskins$", r"lakers$",
]

MIN_SUBSCRIBERS = 5000
QUIET_SUBSCRIBERS = 15000


def _is_team_or_fandom(name: str) -> bool:
    nl = name.lower()
    return any(re.search(p, nl) for p in _REJECT_PATTERNS)


def _name_score(city: str, sub_name: str) -> float:
    c = re.sub(r"[^a-z]", "", city.lower())
    n = re.sub(r"[^a-z]", "", sub_name.lower())
    if n == c:
        return 1.0
    if n.startswith(c):
        return 0.8
    if c in n:
        return 0.5
    return 0.0


def _desc_score(city: str, desc: str, region: str | None = None) -> float:
    if not desc:
        return 0.0
    d = desc.lower()
    c = city.lower()
    if c not in d:
        return 0.0
    score = 0.7
    if region and region.lower() in d:
        score = 0.85
    if re.search(rf"{re.escape(c)}\s*,\s*[a-z]", d):
        score = max(score, 0.8)
    return score


def discover(search_backend, city: str, region: str | None = None, max_subs: int = 6) -> dict:
    """Return a discovery result dict (status, subreddits, candidates, ...)."""
    city = (city or "").strip()
    if not city:
        return {"city": city, "subreddits": [], "candidates": [], "status": "none",
                "alternatives": [], "note": "No city given."}

    raw = list(search_backend.search_subreddits(city))

    # name collision handling (e.g. Portland OR vs ME)
    regions = {s.get("region") for s in raw if s.get("region")}
    if region:
        raw = [s for s in raw if s.get("region") in (None, region)]
    elif len(regions) > 1:
        alts, seen = [], set()
        for s in raw:
            r = s.get("region")
            if r and r not in seen:
                seen.add(r)
                alts.append({"region": r, "example_sub": s["name"],
                             "subscribers": s["subscribers"]})
        return {"city": city, "subreddits": [], "candidates": [], "status": "ambiguous",
                "alternatives": alts, "note": f"More than one {city}. Which one?"}

    base = re.sub(r"[^a-z]", "", city.lower())
    from ..db.repository import get_city_aliases
    alias_list = get_city_aliases(base)
    alias_names = {a.lower() for a in alias_list}
    if alias_names:
        present = {s["name"].lower() for s in raw}
        for alias in alias_list:
            if alias.lower() not in present:
                found = search_backend.subreddit_about(alias)
                if found:
                    raw.append(found)

    scored = []
    for s in raw:
        if _is_team_or_fandom(s["name"]):
            continue
        ns = _name_score(city, s["name"])
        ds = _desc_score(city, s.get("desc", ""), region)
        is_alias = s["name"].lower() in alias_names
        score = max(ns, ds, 0.9 if is_alias else 0.0)
        if score < 0.5:
            continue
        why = ("known local nickname" if is_alias
               else ("name match" if ns >= 0.8 and ns >= ds
                     else ("name match" if ns >= ds else "city named in description")))
        scored.append({"name": s["name"], "subscribers": s["subscribers"],
                       "score": round(score, 2), "active": s.get("active", True), "why": why})

    have = {c["name"].lower() for c in scored}
    for suf in _TOPICAL_SUFFIXES:
        guess = base + suf
        if guess in have:
            continue
        found = search_backend.subreddit_about(guess)
        if found and not _is_team_or_fandom(found["name"]):
            scored.append({"name": found["name"], "subscribers": found["subscribers"],
                           "score": 0.75, "active": found.get("active", True),
                           "why": f"topical guess (+{suf})"})

    def rank_key(c):
        return c["score"] * 2 + math.log10(max(c["subscribers"], 1) + 1)
    scored.sort(key=rank_key, reverse=True)

    kept = [c for c in scored if c["subscribers"] >= MIN_SUBSCRIBERS][:max_subs]
    if not kept and scored:
        kept = scored[:1]
    if not kept:
        return {"city": city, "subreddits": [], "candidates": scored, "status": "none",
                "alternatives": [], "note": f"No active Reddit community found for {city}."}

    best = max(c["subscribers"] for c in kept)
    any_active = any(c["active"] for c in kept)
    status = "quiet" if (best < QUIET_SUBSCRIBERS or not any_active) else "ok"
    note = (f"r/{kept[0]['name']} is small or quiet — results may be thin."
            if status == "quiet" else f"Found {len(kept)} active communities for {city}.")
    return {"city": city, "subreddits": [c["name"] for c in kept], "candidates": kept,
            "status": status, "alternatives": [], "note": note}
