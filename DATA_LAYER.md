# Data layer: Postgres + Redis

CityScope runs fine with **neither** — it falls back to an in-memory cache and
hardcoded mappings. Add them to scale past a single instance and to edit curated
config without redeploying.

## What each gives you

**Redis** — a *shared* cache. Without it, each app instance has its own
in-memory cache; run two instances behind a load balancer and they double the
work. Redis gives all instances one cache. Set `REDIS_URL` and it's used
automatically; unreachable Redis falls back to in-memory (logged, non-fatal).

**Postgres** — persistence + editable config:
- The curated mappings (subreddit nicknames, RSS feeds, gazetteer, ZIPs) move
  from Python into tables you can edit live. No redeploy to add a city.
- Fetched happenings are stored (`city_fetch`), so results survive restarts,
  are shared across instances, and a background worker can refresh them. The API
  reads this tier before doing a live fetch.

The read path is three tiers: **Redis cache → Postgres persisted fetch → live
multi-source build** (which writes back to both).

## Setup

1. **Provision** a Postgres and a Redis (Render/Railway/Fly all offer both as
   one-click add-ons; or Supabase/Neon for PG, Upstash for Redis — generous free
   tiers). Copy their connection URLs.

2. **Set env vars** (host dashboard or `.env`):
   ```
   DATABASE_URL=postgresql://user:pass@host:5432/dbname
   REDIS_URL=redis://default:pass@host:6379
   ```
   `postgres://`-style URLs are normalized automatically.

3. **Run migrations** (creates the tables):
   ```
   alembic upgrade head
   ```

4. **Seed the curated config** (loads the built-in mappings into the DB):
   ```
   python -m cityscope.db.seed
   ```

5. **Verify**: `GET /health` now shows `"db_enabled": true` and
   `"cache": {"backend": "redis", ...}`.

## Editing curated config later

Once seeded, add a city's nickname or paper with plain SQL (or build an admin
UI against these tables) — no redeploy:
```sql
INSERT INTO city_alias (city_key, subreddit) VALUES ('denver', 'denverlist');
INSERT INTO city_feed (city_key, paper, feed_url, active)
  VALUES ('denver', 'Westword', 'https://www.westword.com/feed/', true);
```

## Schema changes

After editing `cityscope/db/models.py`, autogenerate a migration:
```
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

## Migrations on deploy

Add a release/predeploy step so the schema is current before new code serves:
- **Render**: set a Pre-Deploy Command: `alembic upgrade head`
- **Railway/Fly**: run `alembic upgrade head` in your release phase
- Or run it once manually after provisioning.
