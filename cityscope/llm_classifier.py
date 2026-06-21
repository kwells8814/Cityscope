"""LLM classifier — Claude Haiku for classification + extraction.

Enabled via CITYSCOPE_LLM_CLASSIFIER=true + ANTHROPIC_API_KEY. The pipeline
imports classify_llm lazily and falls back to the keyword classifier on any
error, so turning this on can never break the request path.

Why Haiku: classification is high-volume and low-complexity — exactly Haiku's
sweet spot (cheap, fast). Cache by post id and batch where possible to control
cost; this module classifies one post per call for clarity.
"""

from __future__ import annotations

import json

from .config import settings
from .core.logging_setup import get_logger
from .models import RawPost

logger = get_logger("llm")

_SYSTEM = (
    "You classify short local posts for a city-happenings app. "
    "Categories: event (a dated thing to attend), gem (an evergreen hidden "
    "spot), news (a notable local happening), noise (questions, complaints, "
    "recommendation requests — anything not worth surfacing). "
    "Return ONLY compact JSON: "
    '{"category":"event|gem|news|noise","confidence":0.0-1.0}'
)


def classify_llm(post: RawPost) -> tuple[str, float]:
    """Classify one post via the Anthropic API. Raises on failure (caller
    falls back to keyword classification)."""
    # Imported here so the dependency is only needed when the feature is on.
    from anthropic import Anthropic

    client = Anthropic(api_key=settings.anthropic_api_key)
    user = f"Title: {post.title}\nBody: {post.body[:600]}"
    resp = client.messages.create(
        model=settings.llm_model,
        max_tokens=60,
        system=_SYSTEM,
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(block.text for block in resp.content if block.type == "text")
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    data = json.loads(text)
    category = data["category"]
    confidence = float(data.get("confidence", 0.7))
    if category not in ("event", "gem", "news", "noise"):
        raise ValueError(f"unexpected category: {category}")
    return category, round(confidence, 2)
