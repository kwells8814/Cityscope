"""Synthesize believable RawPosts for any city (keyless/standalone mode).

Used when live Reddit is off, so the app demos for any discovered city.
Deterministic per city for stable output.
"""

from __future__ import annotations

import random
import time

from ..models import RawPost

_DAY = 86400
_HOUR = 3600

_TEMPLATES = [
    ("event", (120, 480), (15, 70),
     "Pop-up night market in {city} this Saturday — local makers + food trucks",
     "Doors 5pm, free entry, runs til late. Cash and venmo. Heard it's a monthly thing now."),
    ("event", (90, 350), (10, 50),
     "Free outdoor movie night downtown {city} on Friday",
     "Showing a classic at sundown, ~8:30pm. Bring a blanket. Food trucks lined up."),
    ("event", (110, 300), (12, 44),
     "Secret warehouse show in {city} tonight — touring act, word of mouth only",
     "DM for the address. Doors 10pm, $15 cash at the door. Limited capacity."),
    ("gem", (200, 620), (30, 95),
     "Hidden gem in {city}: tiny ramen counter with no sign, cash only",
     "Six seats, best tonkotsu in town and nobody knows about it. Open Wed-Sun lunch only."),
    ("gem", (180, 500), (25, 80),
     "Underrated {city} spot: a basement bookstore that only opens weekend nights",
     "Candlelit, plays jazz, owner makes tea. Feels like a secret. No website on purpose."),
    ("news", (100, 320), (10, 40),
     "New mural just went up in {city} — three stories, worth a detour",
     "Artist worked on it all week, finished today. Whole side of a building."),
    ("news", (120, 360), (12, 50),
     "Wildflowers are peaking right now just outside {city}",
     "Best viewing this week along the river trail. Go early before it gets hot."),
    ("noise", (40, 600), (40, 300),
     "Why is traffic in {city} always this bad??",
     "Sat for 40 minutes today. Rant over."),
    ("noise", (10, 80), (15, 120),
     "Looking for a good plumber recommendation in {city}",
     "Pipe burst, need someone reliable. Thanks."),
]


def generate_posts(city: str, subreddits, candidates=None, seed=None) -> list:
    rng_seed = seed if seed is not None else abs(hash(city.lower())) % (2**31)
    rng = random.Random(rng_seed)

    scale_by_sub = {}
    if candidates:
        max_subs = max((c["subscribers"] for c in candidates), default=1)
        for c in candidates:
            scale_by_sub[c["name"]] = min(1.0, c["subscribers"] / max(max_subs, 1))

    posts = []
    for s_i, sub in enumerate(subreddits):
        scale = scale_by_sub.get(sub, 0.6)
        n = 8 if s_i == 0 else 3
        chosen = rng.sample(_TEMPLATES, min(n, len(_TEMPLATES)))
        for t_i, (_cat, srange, crange, title, body) in enumerate(chosen):
            score = int(rng.uniform(*srange) * (0.4 + 0.6 * scale))
            comments = int(rng.uniform(*crange) * (0.4 + 0.6 * scale))
            max_age = 1 + (1 - scale) * 6
            created = time.time() - rng.uniform(2 * _HOUR, max_age * _DAY)
            posts.append(RawPost(
                id=f"{sub}_{s_i}{t_i}",
                source_label=sub,
                title=title.format(city=city),
                body=body.format(city=city),
                url=f"https://reddit.com/r/{sub}/comments/{sub}_{s_i}{t_i}",
                score=score,
                num_comments=comments,
                created_utc=created,
                author=f"user_{s_i}{t_i}",
                origin="reddit",
            ))
    return posts
