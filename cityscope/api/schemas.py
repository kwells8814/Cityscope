"""Pydantic schemas for the API layer.

These mirror the dataclasses in cityscope.models for request/response
validation and OpenAPI docs. The core stays dataclass-based (testable with no
deps); the API converts at the boundary.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class HappeningOut(BaseModel):
    id: str
    category: str
    category_label: str
    title: str
    summary: str
    when: Optional[str] = None
    price: Optional[str] = None
    is_free: bool = False
    source: str
    origin: str
    url: str
    score: int
    comments: int
    confidence: float
    rank_score: float


class SourceReportOut(BaseModel):
    source: str
    label: str
    status: str
    count: int = 0
    note: str = ""
    detail: dict = Field(default_factory=dict)


class HappeningsResponse(BaseModel):
    city: str
    region: Optional[str] = None
    status: str
    note: str = ""
    happenings: list[HappeningOut] = Field(default_factory=list)
    subreddits: list[str] = Field(default_factory=list)
    sources: list[SourceReportOut] = Field(default_factory=list)
    alternatives: list[dict] = Field(default_factory=list)


class ResolveResponse(BaseModel):
    city: Optional[str] = None
    region: Optional[str] = None
    source: str
    note: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    version: str
    cache: dict
    db_enabled: bool
    live_reddit: bool
    live_rss: bool
