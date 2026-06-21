"""Database layer tests.

Run against SQLite (file-less, in-memory-ish via a temp file) so they need no
Postgres. Skipped automatically if SQLAlchemy isn't installed, so the core
suite still runs in a minimal environment.

These verify: schema creation, the repository's read/write against a real DB,
and that persisted fetches round-trip.
"""

import os
import tempfile

import pytest

try:
    import sqlalchemy  # noqa: F401
    HAVE_SQLALCHEMY = True
except Exception:
    HAVE_SQLALCHEMY = False

pytestmark = pytest.mark.skipif(not HAVE_SQLALCHEMY, reason="sqlalchemy not installed")


@pytest.fixture()
def db(tmp_path, monkeypatch):
    """Spin up a SQLite-backed engine + schema for one test."""
    from cityscope.config import settings
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path}", raising=False)

    # reset engine module globals so it rebuilds against sqlite
    from cityscope.db import engine as eng
    eng._engine = None
    eng._SessionLocal = None
    eng.init_engine()

    from cityscope.db.models import Base
    Base.metadata.create_all(eng.get_engine())
    yield eng
    eng._engine = None
    eng._SessionLocal = None


def test_alias_roundtrip(db):
    from cityscope.db import repository as repo
    from cityscope.db.engine import session_scope
    from cityscope.db.models import CityAlias

    with session_scope() as s:
        s.add(CityAlias(city_key="durham", subreddit="bullcity"))

    assert repo.get_city_aliases("durham") == ["bullcity"]
    assert repo.get_city_aliases("nowhere") == []


def test_feed_roundtrip(db):
    from cityscope.db import repository as repo
    from cityscope.db.engine import session_scope
    from cityscope.db.models import CityFeed

    with session_scope() as s:
        s.add(CityFeed(city_key="durham", paper="INDY Week",
                       feed_url="https://indyweek.com/feed/", active=True))

    feeds = repo.get_city_feeds("durham")
    assert feeds == [("INDY Week", "https://indyweek.com/feed/")]


def test_gazetteer_and_zip(db):
    from cityscope.db import repository as repo
    from cityscope.db.engine import session_scope
    from cityscope.db.models import GazetteerCity, ZipCode

    with session_scope() as s:
        s.add(GazetteerCity(name="Durham", lat=35.99, lng=-78.90, region="NC"))
        s.add(ZipCode(zip="27701", city="Durham", region="NC"))

    gaz = repo.get_gazetteer()
    assert gaz["Durham"] == (35.99, -78.90, "NC")
    assert repo.get_zip("27701") == ("Durham", "NC")
    assert repo.get_zip("00000") is None


def test_city_fetch_persist_and_load(db):
    from cityscope.db import repository as repo

    payload = {"city": "Durham", "region": None, "status": "ok",
               "note": "test", "happenings": [{"id": "x"}], "sources": []}
    repo.save_city_fetch("durham|", payload)

    loaded = repo.load_city_fetch("durham|", max_age_s=3600)
    assert loaded is not None
    assert loaded["city"] == "Durham"
    assert len(loaded["happenings"]) == 1


def test_city_fetch_staleness(db):
    from cityscope.db import repository as repo

    repo.save_city_fetch("durham|", {"city": "Durham", "status": "ok", "happenings": []})
    # max_age 0 => always considered stale => None
    assert repo.load_city_fetch("durham|", max_age_s=0) is None


def test_city_fetch_upsert(db):
    """Saving the same key twice updates, not duplicates."""
    from cityscope.db import repository as repo
    from cityscope.db.engine import session_scope
    from cityscope.db.models import CityFetch

    repo.save_city_fetch("durham|", {"city": "Durham", "status": "ok", "happenings": []})
    repo.save_city_fetch("durham|", {"city": "Durham", "status": "quiet", "happenings": [{"id": "1"}]})

    with session_scope() as s:
        rows = s.query(CityFetch).filter(CityFetch.city_key == "durham|").all()
    assert len(rows) == 1
    assert rows[0].status == "quiet"
