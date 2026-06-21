# CityScope backend

Cool things happening in **any** city, mined from Reddit + local alt-weeklies,
filtered and ranked. Production-structured FastAPI service with caching,
per-source resilience, and a tested core.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn cityscope.api.app:app --reload
```

Open http://localhost:8000/docs for interactive API docs.

Runs on mock data out of the box (no keys). Flip on live sources via env vars
(see `.env.example`).

## API

| Endpoint | Purpose |
|---|---|
| `GET /health` | status, version, cache stats, live-source flags |
| `GET /resolve?zip=28801` | ZIP / GPS / name → city (+ region) |
| `GET /resolve?lat=..&lng=..` | reverse-geocode GPS |
| `GET /happenings?city=Austin` | ranked happenings (multi-source) |
| `GET /happenings?city=Portland` | `status: ambiguous` + region choices |
| `GET /happenings?city=Austin&categories=event,gem` | filter |
| `GET /happenings?city=Austin&nocache=true` | bypass cache |
| `GET /ics?title=..&when=..` | downloadable `.ics` calendar file |

## Architecture

```
cityscope/
  config.py            env-driven settings (one place for all tunables)
  models.py            typed domain models (RawPost, Happening, ...)
  pipeline.py          classify + extract + rank  (keyword or LLM)
  geocode.py           ZIP/GPS/name -> city (mock or live Census)
  orchestrator.py      cached, resilient, multi-source fetch  <-- the heart
  calendar.py          .ics generation
  core/
    cache.py           thread-safe TTL + LRU cache
    resilience.py      retry/backoff + timeout isolation
    logging_setup.py
  sources/
    base.py            Source contract + registry
    discovery.py       nickname-aware subreddit discovery (backend-injected)
    reddit_client.py   live Reddit OAuth client (stdlib urllib)
    reddit_source.py   Reddit source (live or mock)
    rss_source.py      alt-weekly RSS source (live feedparser or mock)
    mock_*.py          keyless standalone backends
  api/
    app.py             FastAPI routes (thin layer over orchestrator)
    schemas.py         Pydantic request/response models
```

### What makes it "solid"

- **Caching** — results cached per (city, region) with TTL + LRU eviction; the
  same city isn't re-fetched every request. `/health` exposes hit rate.
- **Resilience** — each source runs with a timeout and full error isolation. A
  source that throws or hangs is logged, reported as `error`, and the rest of
  the response still goes out. Verified by tests.
- **Retries** — HTTP clients retry transient failures (429, network) with
  exponential backoff.
- **Config** — everything tunable via env vars; no hard-coded secrets.
- **Typed** — dataclasses in the core, Pydantic at the API boundary.
- **Tested** — 47 core tests (cache, resilience, pipeline, discovery, geocode,
  calendar, orchestrator incl. failure isolation) + API tests.

## Going live

Set the toggles in `.env`:

- `CITYSCOPE_LIVE_RSS=true` — real alt-weekly feeds (needs `feedparser`,
  already in requirements). No keys.
- `CITYSCOPE_LIVE_GEOCODE=true` — real GPS reverse-geocoding via the free US
  Census geocoder. No keys.
- `CITYSCOPE_LIVE_REDDIT=true` + `REDDIT_CLIENT_ID/SECRET/USERNAME` — real
  Reddit. Register a 'script' app and request access (Reddit requires approval
  as of Nov 2025).
- `CITYSCOPE_LLM_CLASSIFIER=true` + `ANTHROPIC_API_KEY` — swap the keyword
  classifier for Claude Haiku (the `llm_classifier` module is the integration
  point; keyword is the automatic fallback).

Each toggle is independent — you can run live RSS + geocoding with no keys while
Reddit stays mocked.

## Tests

```bash
pytest                      # full suite (needs fastapi+httpx for API tests)
python run_tests.py         # core suite, no deps (stdlib runner)
```
