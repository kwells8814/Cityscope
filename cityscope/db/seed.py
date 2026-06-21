"""Seed the curated-config tables from the built-in fallback data.

Run once after migrations against a fresh database:

    python -m cityscope.db.seed

Idempotent: uses merge/get so re-running won't duplicate rows. After seeding,
the same mappings that were hardcoded in Python live in the DB and can be
edited (via SQL or a future admin UI) without a redeploy.
"""

from __future__ import annotations

from ..core.logging_setup import configure_logging, get_logger
from ..config import settings
from .engine import db_enabled, init_engine, session_scope, get_engine
from .models import Base, CityAlias, CityFeed, GazetteerCity, ZipCode
from . import repository as repo

logger = get_logger("db.seed")


def seed() -> None:
    if not db_enabled():
        raise SystemExit("DATABASE_URL is not set — nothing to seed.")

    init_engine()
    Base.metadata.create_all(get_engine())   # safe if migrations already ran

    with session_scope() as s:
        # aliases
        n_alias = 0
        for city_key, subs in repo._FALLBACK_ALIASES.items():
            for sub in subs:
                exists = (s.query(CityAlias)
                          .filter(CityAlias.city_key == city_key,
                                  CityAlias.subreddit == sub).first())
                if not exists:
                    s.add(CityAlias(city_key=city_key, subreddit=sub))
                    n_alias += 1

        # feeds
        n_feed = 0
        for city_key, (paper, url) in repo._FALLBACK_FEEDS.items():
            exists = (s.query(CityFeed)
                      .filter(CityFeed.city_key == city_key,
                              CityFeed.feed_url == url).first())
            if not exists:
                s.add(CityFeed(city_key=city_key, paper=paper, feed_url=url, active=True))
                n_feed += 1

        # gazetteer
        n_city = 0
        for name, (lat, lng, region) in repo._FALLBACK_CITIES.items():
            if not s.query(GazetteerCity).filter(GazetteerCity.name == name).first():
                s.add(GazetteerCity(name=name, lat=lat, lng=lng, region=region))
                n_city += 1

        # zips
        n_zip = 0
        for zip_code, (city, region) in repo._FALLBACK_ZIPS.items():
            if not s.get(ZipCode, zip_code):
                s.add(ZipCode(zip=zip_code, city=city, region=region))
                n_zip += 1

    logger.info("seeded: %d aliases, %d feeds, %d cities, %d zips",
                n_alias, n_feed, n_city, n_zip)
    print(f"Seed complete: {n_alias} aliases, {n_feed} feeds, "
          f"{n_city} gazetteer cities, {n_zip} zips.")


if __name__ == "__main__":
    configure_logging(settings.log_level)
    seed()
