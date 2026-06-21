"""The pipeline: RawPost[] -> ranked Happening[].

Classification + extraction + ranking. Keyword classifier by default; an LLM
classifier (Claude Haiku) can be swapped in via config without touching callers.
"""

from __future__ import annotations

import re
import time
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
]
_NEWS_HINTS = [
    "just went up", "new mural", "peaking", "emergence", "reported",
    "bioluminescent", "just opened", "spotted", "right now", "wildflowers",
]
_NOISE_HINTS = [
    "recommendation", "anyone else", "why is", "why even", "rant",
    "best place to buy", "looking for a", "settle the debate", "confused",
]

_TIME_RE = re.compile(r"\b(\d{1,2}(?::\d{2})?\s?(?:am|pm))\b", re.I)
_PRICE_RE = re.compile(r"(free|\$\d+|donation|cash only|byob)", re.I)
_DAY_WORDS = ["today", "tonight", "tomorrow", "monday", "tuesday", "wednesday",
              "thursday", "friday", "saturday", "sunday", "this weekend", "this week"]

CATEGORY_LABELS = {"event": "Events & gigs", "gem": "Hidden gems", "news": "Local happenings"}


def _count(text: str, hints) -> int:
    t = text.lower()
    return sum(1 for h in hints if h in t)


def classify_keyword(post: RawPost) -> tuple[str, float]:
    """Heuristic classifier. Returns (category, confidence)."""
    text = f"{post.title} {post.body}"
    noise = _count(text, _NOISE_HINTS)
    scores = {
        "event": _count(text, _EVENT_HINTS),
        "gem": _count(text, _GEM_HINTS),
        "news": _count(text, _NEWS_HINTS),
    }
    is_question = post.title.strip().endswith("?")
    best = max(scores, key=scores.get)

    if is_question and scores[best] < 2:
        return "noise", 0.9
    if noise >= 1 and scores[best] <= noise:
        return "noise", 0.85
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


def _extract(post: RawPost) -> dict:
    text = f"{post.title} {post.body}"
    t = text.lower()
    time_m = _TIME_RE.search(text)
    day = next((w for w in _DAY_WORDS if w in t), None)
    price_m = _PRICE_RE.search(text)
    parts = []
    if day:
        parts.append(day.title())
    if time_m:
        parts.append(time_m.group(1).lower())
    return {
        "when": " ".join(parts) if parts else None,
        "price": price_m.group(0).lower() if price_m else None,
        "is_free": bool(price_m and "free" in price_m.group(0).lower()),
    }


def _summarize(post: RawPost) -> str:
    body = post.body.strip()
    if not body:
        return post.title
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
    return round(engagement * recency * confidence, 1)


def _source_label(post: RawPost) -> str:
    if post.origin == "reddit":
        return f"r/{post.source_label}"
    return post.source_label


def process(posts, categories=None, min_confidence: Optional[float] = None) -> list:
    """RawPost[] -> ranked Happening[]."""
    if min_confidence is None:
        min_confidence = settings.min_confidence
    wanted = set(categories) if categories else {"event", "gem", "news"}
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
            title=post.title,
            summary=_summarize(post),
            when=ex["when"],
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
