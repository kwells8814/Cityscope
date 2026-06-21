"""ORM models.

Two groups:
  1. Curated config — the mappings currently hardcoded in Python, moved to the
     DB so they're editable without a redeploy:
        CityAlias    nickname subreddits (durham -> bullcity)
        CityFeed     alt-weekly RSS feeds (durham -> INDY Week url)
        GazetteerCity / ZipCode  geocoding data
  2. Operational data:
        CityFetch    a fetched city's happenings + when it was fetched
                     (persistence layer: survive restarts, share across instances)
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    String, Integer, Float, Boolean, DateTime, Text, JSON, UniqueConstraint, Index,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --- curated config ---------------------------------------------------------

class CityAlias(Base):
    """A nickname subreddit for a city (durham -> bullcity)."""
    __tablename__ = "city_alias"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    city_key: Mapped[str] = mapped_column(String(80), index=True)   # normalized: "durham"
    subreddit: Mapped[str] = mapped_column(String(120))
    __table_args__ = (UniqueConstraint("city_key", "subreddit", name="uq_alias"),)


class CityFeed(Base):
    """An alt-weekly / community RSS feed for a city."""
    __tablename__ = "city_feed"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    city_key: Mapped[str] = mapped_column(String(80), index=True)
    paper: Mapped[str] = mapped_column(String(160))
    feed_url: Mapped[str] = mapped_column(String(500))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("city_key", "feed_url", name="uq_feed"),)


class GazetteerCity(Base):
    """City coordinates for nearest-city GPS resolution."""
    __tablename__ = "gazetteer_city"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    region: Mapped[str] = mapped_column(String(20))


class ZipCode(Base):
    """ZIP -> city mapping."""
    __tablename__ = "zip_code"
    zip: Mapped[str] = mapped_column(String(10), primary_key=True)
    city: Mapped[str] = mapped_column(String(120))
    region: Mapped[str] = mapped_column(String(20))


# --- operational data -------------------------------------------------------

class CityFetch(Base):
    """A persisted fetch of a city's happenings.

    Stores the full CityResult payload as JSON plus metadata, so:
      - results survive restarts and are shared across instances
      - a background worker can refresh these on a schedule
      - the API can serve the stored copy instantly and refetch only when stale
    """
    __tablename__ = "city_fetch"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    city_key: Mapped[str] = mapped_column(String(120), index=True)   # "durham|" or "portland|me"
    city: Mapped[str] = mapped_column(String(120))
    region: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(20))
    payload: Mapped[dict] = mapped_column(JSON)                       # CityResult.to_dict()
    happening_count: Mapped[int] = mapped_column(Integer, default=0)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    __table_args__ = (
        UniqueConstraint("city_key", name="uq_city_fetch"),
        Index("ix_city_fetch_fetched_at", "fetched_at"),
    )
