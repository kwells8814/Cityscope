"""The pipeline: RawPost[] -> ranked Happening[].

Classification + extraction + ranking. Keyword classifier by default; an LLM
classifier (Claude Haiku) can be swapped in via config without touching callers.
"""

from __future__ import annotations

import re
import time
import html
from typing import Optional

from .config import settings
from .core.logging_setup import get_logger
from .models import RawPost, Happening

logger = get_logger("pipeline")

# --- keyword signals --------------------------------------------------------

_EVENT_HINTS = [
    "tonight", "saturday", "sunday", "monday", "tuesday", "wednesday",
    "thursday", "friday", "this week", "this weekend", "pop-up", "popping up",
    "doors", "pm", "am", "free entry", "tickets", "show", "market", "screening",
    "movie night", "series", "opening", "one night only", "lottery", "walk",
    "festival", "crawl", "fair", "live",
]
_GEM_HINTS = [
    "hidden gem", "underrated", "secret", "no sign", "unmarked", "nobody knows",
    "hole in the wall", "tiny", "off the beaten", "no website", "feels like a secret",
    "best-kept",
    # Nonsense-style underground / rule-of-three weirdness: unusual venues,
    # one-off site-specific happenings, DIY, immersive multi-activity events.
    "warehouse", "loft", "rooftop", "basement", "abandoned", "undisclosed",
    "immersive", "site-specific", "one night only", "one-night", "diy",
    "underground", "guerrilla", "guerilla", "pop-up", "popup", "speakeasy",
    "invite only", "byob", "after-hours", "afterhours", "experimental",
    "interactive", "in a parking lot", "in an alley", "secret location",
    "address tba", "location tba", "dm for", "you won't believe", "weird",
]
_NEWS_HINTS = [
    "just went up", "new mural", "peaking", "emergence", "reported",
    "bioluminescent", "just opened", "spotted", "right now", "wildflowers",
    "review:", "profile", "press release", "remains", "explores", "is a love letter",
    "obituary", "remembering", "the secret history",
]
# Food/restaurant signals — written by people who live there (alt-weekly food
# sections, local food blogs), surfaced as their own category.
_FOOD_HINTS = [
    "restaurant", "taco", "ramen", "pizza", "bbq", "barbecue", "burger",
    "sandwich", "noodle", "dumpling", "taqueria", "bakery", "cafe", "coffee",
    "brunch", "dinner", "lunch", "menu", "chef", "kitchen", "dish", "eat",
    "eats", "food", "dining", "bar", "brewery", "cocktail", "bites", "bite",
    "supper", "deli", "diner", "pop-up dinner", "tasting menu", "happy hour",
    "new spot", "just opened", "soft open", "now serving", "best meal",
]
_NOISE_HINTS = [
    "recommendation", "anyone else", "why is", "why even", "rant",
    "best place to buy", "looking for a", "settle the debate", "confused",
]

# Anti-aggregator / anti-tourist filter. Food content from these sources or with
# this listicle-style framing is dropped — the goal is LOCAL voice, not Yelp,
# travel guides, or SEO "best of" roundups.
_AGGREGATOR_HINTS = [
    "yelp", "tripadvisor", "trip advisor", "opentable", "best restaurants in",
    "top 10 restaurants", "top ten restaurants", "where to eat in",
    "must-try restaurants", "tourist", "travel guide", "bucket list",
    "ultimate guide", "you must visit", "before you die", "michelin guide",
]

# Content-safety blocklist. Items matching these are dropped entirely — not
# shown in any category. Covers adult content and obvious sponsored/SEO spam
# that slips into newspaper RSS feeds (e.g. "best AI hentai generators").
_BLOCK_HINTS = [
    "hentai", "porn", "nsfw", "xxx", "onlyfans", "escort", "camgirl",
    "sex toy", "adult content", "best ai girlfriend", "nude", "fetish",
    "casino", "betting odds", "sportsbook promo", "crypto casino",
]

_TIME_RE = re.compile(r"\b(\d{1,2}(?::\d{2})?\s?(?:am|pm))\b", re.I)
_PRICE_RE = re.compile(r"(free|\$\d+|donation|cash only|byob)", re.I)
_DAY_WORDS = ["today", "tonight", "tomorrow", "monday", "tuesday", "wednesday",
              "thursday", "friday", "saturday", "sunday", "this weekend", "this week"]

CATEGORY_LABELS = {"event": "Events & gigs", "gem": "Hidden gems",
                   "news": "Local happenings", "food": "Local eats"}


def _count(text: str, hints) -> int:
    t = text.lower()
    return sum(1 for h in hints if h in t)


def _is_blocked(post: RawPost) -> bool:
    text = f"{post.title} {post.body} {post.url}".lower()
    if any(h in text for h in _BLOCK_HINTS):
        return True
    # Drop aggregator/tourist food content — we want local voice, not Yelp,
    # travel guides, or "best restaurants in X" SEO roundups.
    if any(h in text for h in _AGGREGATOR_HINTS):
        return True
    return False


_DATE_SIGNAL_RE = re.compile(
    r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b"  # weekday
    r"|\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d"  # month + day
    r"|\b\d{1,2}(:\d{2})?\s?(am|pm)\b"                     # clock time
    r"|\btonight\b|\btoday\b|\btomorrow\b|\bthis (week|weekend)\b"
    r"|\bnext (week|weekend|month)\b|\bdoors\b"
    r"|\bthrough\b\s+\w+\s+\d|\b\d{1,2}/\d{1,2}\b",
    re.I,
)

# Words that strongly indicate coverage/criticism rather than an upcoming event.
_COVERAGE_HINTS = [
    "review:", "review ", "remains", "explores", "is a love letter", "profile",
    "obituary", "remembering", "the secret history", "looks back", "retrospective",
    "interview", "is a delight", "is a", "tackles", "ruminates", "carves",
    "best ", "ranked", "we tried", "first look", "recap", "oral history",
]


def _has_date_signal(text: str) -> bool:
    return bool(_DATE_SIGNAL_RE.search(text))


def classify_keyword(post: RawPost) -> tuple[str, float]:
    """Heuristic classifier. Returns (category, confidence)."""
    if _is_blocked(post):
        return "blocked", 0.99
    text = f"{post.title} {post.body}"
    tl = text.lower()
    noise = _count(text, _NOISE_HINTS)
    coverage = _count(text, _COVERAGE_HINTS)
    raw_event = _count(text, _EVENT_HINTS)
    food = _count(text, _FOOD_HINTS)
    has_date = _has_date_signal(text)

    # An "event" must have a real date/time signal. Arts vocabulary alone
    # (show, live, series, opening) is NOT enough — that's what was mislabeling
    # reviews and profiles as events. No date -> it's coverage, not an event.
    event_score = raw_event if has_date else 0

    scores = {
        "event": event_score,
        "gem": _count(text, _GEM_HINTS),
        "news": _count(text, _NEWS_HINTS),
        "food": food,
    }
    is_question = post.title.strip().endswith("?")
    # Noise checks run FIRST, against raw signals — question-bait and rants
    # stay noise even if they contain coverage words like "best".
    raw_best = max(scores, key=scores.get)
    if is_question and scores[raw_best] < 2:
        return "noise", 0.9
    if noise >= 1 and scores[raw_best] <= noise:
        return "noise", 0.85

    # Coverage language pushes toward "news" (local happenings) over "event".
    if coverage and not has_date:
        scores["news"] += coverage

    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "noise", 0.6

    total = sum(scores.values()) + noise
    conf = scores[best] / total if total else 0.5
    return best, round(min(0.99, 0.5 + conf / 2), 2)


def classify(post: RawPost) -> tuple[str, float]:
    """Dispatch to LLM or keyword classifier based on config."""
    if settings.use_llm_classifier and settings.anthropic_api_key:
        try:
            from .llm_classifier import classify_llm  # lazy import
            return classify_llm(post)
        except Exception as exc:  # never let the LLM break the request
            logger.warning("LLM classify failed, falling back to keyword: %s", exc)
    return classify_keyword(post)


_VENUE_RE = re.compile(
    r"\b(?:at|@)\s+(?:the\s+)?"
    r"([A-Z][A-Za-z0-9'&.]+(?:\s+[A-Z][A-Za-z0-9'&.]+){0,3})"
    r"(?:\s+(?:Theatre|Theater|Hall|Bar|Club|Lounge|Gallery|Bottle|Room|"
    r"Stage|Arena|Park|Bowl|Center|Centre|Cafe|Tavern|Saloon|Pub|Brewery))?"
)
# Venue suffixes that strongly signal a real place name.
_VENUE_SUFFIX = ("theatre", "theater", "hall", "bar", "club", "lounge", "gallery",
                 "bottle", "room", "stage", "arena", "bowl", "tavern", "brewery",
                 "saloon", "ballroom", "amphitheater", "amphitheatre")


def _extract_venue(text: str) -> Optional[str]:
    """Pull a likely venue name from 'at the Empty Bottle' / '@ Metro' phrasing.
    Returns a clean venue string or None."""
    for m in _VENUE_RE.finditer(text):
        cand = m.group(1).strip()
        # Trim trailing day/time words the regex may have swept in
        # (e.g. "Empty Bottle Friday" -> "Empty Bottle").
        words = cand.split()
        while words and words[-1].lower() in _DAY_WORDS:
            words.pop()
        cand = " ".join(words)
        if not cand:
            continue
        low = cand.lower()
        if low in _DAY_WORDS or low in ("the", "a", "an"):
            continue
        full = m.group(0).lower()
        if any(s in full for s in _VENUE_SUFFIX) or len(cand.split()) >= 2:
            return cand
    return None


def _extract(post: RawPost) -> dict:
    text = _clean_html(f"{post.title} {post.body}")
    t = text.lower()
    time_m = _TIME_RE.search(text)
    day = next((w for w in _DAY_WORDS if w in t), None)
    price_m = _PRICE_RE.search(text)
    venue = _extract_venue(text)
    parts = []
    if day:
        parts.append(day.title())
    if time_m:
        parts.append(time_m.group(1).lower())
    return {
        "when": " ".join(parts) if parts else None,
        "venue": venue,
        "price": price_m.group(0).lower() if price_m else None,
        "is_free": bool(price_m and "free" in price_m.group(0).lower()),
    }


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _clean_html(text: str) -> str:
    """Strip HTML tags and decode entities — RSS titles and bodies are full of
    <i>/<em>/<figure> markup and &amp;-style entities we don't want to display."""
    if not text:
        return ""
    # Decode entities first (so &lt;i&gt; becomes <i>), then strip tags, then
    # decode again in case stripping exposed more, then collapse whitespace.
    text = html.unescape(text)
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    return _WS_RE.sub(" ", text).strip()


def _summarize(post: RawPost) -> str:
    body = _clean_html(post.body)
    if not body:
        return _clean_html(post.title)
    first = re.split(r"(?<=[.!?])\s", body)[0]
    return first if len(first) <= 160 else first[:157] + "..."


def _summarize(post: RawPost) -> str:
    body = _clean_html(post.body)
    if not body:
        return _clean_html(post.title) or post.title
    first = re.split(r"(?<=[.!?])\s", body)[0]
    return first if len(first) <= 160 else first[:157] + "..."


def _rank_score(post: RawPost, category: str, confidence: float) -> float:
    age_hours = (time.time() - post.created_utc) / 3600
    engagement = post.score + post.num_comments * 2
    if category == "event":
        recency = max(0.1, 1 - age_hours / 72)
    elif category == "news":
        recency = max(0.1, 1 - age_hours / 120)
    else:
        recency = max(0.4, 1 - age_hours / 720)
    score = engagement * recency * confidence
    # Hidden gems are the point of the app — surface the off-the-radar weird
    # stuff above routine listings. Boost gems so they don't get buried.
    if category == "gem":
        score *= 1.5
    return round(score, 1)


def _source_label(post: RawPost) -> str:
    if post.origin == "reddit":
        return f"r/{post.source_label}"
    return post.source_label


def process(posts, categories=None, min_confidence: Optional[float] = None) -> list:
    """RawPost[] -> ranked Happening[]."""
    if min_confidence is None:
        min_confidence = settings.min_confidence
    wanted = set(categories) if categories else {"event", "gem", "news", "food"}
    out = []
    for post in posts:
        category, confidence = classify(post)
        if category == "noise" or confidence < min_confidence or category not in wanted:
            continue
        ex = _extract(post)
        out.append(Happening(
            id=post.id,
            category=category,
            category_label=CATEGORY_LABELS[category],
            title=_clean_html(post.title) or post.title,
            summary=_summarize(post),
            when=ex["when"],
            venue=ex["venue"],
            price=ex["price"],
            is_free=ex["is_free"],
            source=_source_label(post),
            origin=post.origin,
            url=post.url,
            score=post.score,
            comments=post.num_comments,
            confidence=confidence,
            rank_score=_rank_score(post, category, confidence),
        ))
    out.sort(key=lambda h: h.rank_score, reverse=True)
    return out
