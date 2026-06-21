"""Domain models — typed dataclasses shared across the app.

Using dataclasses (stdlib) keeps the core testable here with no deps. The
FastAPI layer mirrors these as Pydantic models for request/response validation;
`to_dict()` gives the JSON shape both expect.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class RawPost:
    """A post as fetched from a source, before classification."""
    id: str
    source_label: str          # "Austin" (subreddit) or "Austin Chronicle" (paper)
    title: str
    body: str
    url: str
    score: int
    num_comments: int
    created_utc: float
    author: str
    origin: str                # "reddit" | "rss" | ...

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Happening:
    """A classified, ranked happening — the user-facing unit."""
    id: str
    category: str              # event | gem | news
    category_label: str
    title: str
    summary: str
    when: Optional[str]
    price: Optional[str]
    is_free: bool
    source: str
    origin: str
    url: str
    score: int
    comments: int
    confidence: float
    rank_score: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SourceReport:
    """Per-source outcome for transparency in the API response."""
    source: str
    label: str
    status: str                # ok | quiet | none | error | ambiguous | skipped
    count: int = 0
    note: str = ""
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CityResult:
    """Everything the API needs to render a city's feed."""
    city: str
    region: Optional[str]
    status: str                # ok | quiet | none | ambiguous
    note: str
    happenings: list = field(default_factory=list)
    subreddits: list = field(default_factory=list)
    sources: list = field(default_factory=list)
    alternatives: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "city": self.city,
            "region": self.region,
            "status": self.status,
            "note": self.note,
            "happenings": [h.to_dict() if isinstance(h, Happening) else h
                           for h in self.happenings],
            "subreddits": self.subreddits,
            "sources": [s.to_dict() if isinstance(s, SourceReport) else s
                        for s in self.sources],
            "alternatives": self.alternatives,
        }
