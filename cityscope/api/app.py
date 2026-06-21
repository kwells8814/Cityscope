"""FastAPI application for CityScope.

Thin HTTP layer over the tested core (cityscope.orchestrator). All the logic,
caching, resilience, and source handling live in the core; this just validates
requests, calls the orchestrator, and shapes responses.

Run:
    uvicorn cityscope.api.app:app --reload
Docs at /docs (Swagger) and /redoc.
"""

from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .. import __version__
from ..config import settings
from ..core.logging_setup import configure_logging, get_logger
from .. import orchestrator as orch
from .. import calendar as cal
from .schemas import (
    HappeningsResponse, ResolveResponse, HealthResponse,
)

configure_logging(settings.log_level)
logger = get_logger("api")

app = FastAPI(
    title="CityScope API",
    version=__version__,
    description="Cool things happening in any city, mined from forums + local papers.",
)

# CORS: open by default for the static frontend; tighten allow_origins in prod.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled(request, exc):
    logger.exception("unhandled error: %s", exc)
    return JSONResponse(status_code=500,
                        content={"error": "internal error", "detail": str(exc)})


@app.get("/health", response_model=HealthResponse)
def health():
    from ..db.engine import db_enabled
    return HealthResponse(
        status="ok",
        version=__version__,
        cache=orch.cache_stats(),
        db_enabled=db_enabled(),
        live_reddit=settings.use_live_reddit,
        live_rss=settings.use_live_rss,
    )


@app.get("/resolve", response_model=ResolveResponse)
def resolve(
    city: Optional[str] = None,
    zip: Optional[str] = None,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
):
    res = orch.resolve_city(city=city, zip_code=zip, lat=lat, lng=lng)
    return ResolveResponse(**res)


@app.get("/happenings", response_model=HappeningsResponse)
def happenings(
    city: str = Query(..., min_length=1, description="City name"),
    region: Optional[str] = Query(None, description="State/region to disambiguate"),
    categories: Optional[str] = Query(None, description="comma list: event,gem,news"),
    nocache: bool = Query(False, description="bypass cache"),
):
    result = orch.get_happenings(city, region, use_cache=not nocache)
    payload = result.to_dict()

    # optional category filter applied at the edge (keeps core cache category-agnostic)
    if categories:
        wanted = {c.strip().lower() for c in categories.split(",") if c.strip()}
        valid = {"event", "gem", "news"}
        bad = wanted - valid
        if bad:
            return JSONResponse(status_code=400,
                                content={"error": f"invalid categories: {sorted(bad)}",
                                         "valid": sorted(valid)})
        payload["happenings"] = [h for h in payload["happenings"]
                                 if h["category"] in wanted]
    return payload


@app.get("/ics")
def ics(
    title: str = Query(..., min_length=1),
    when: str = "",
    summary: str = "",
    url: str = "",
    location: str = "",
):
    body = cal.build_ics(title=title, when=when, summary=summary,
                         url=url, location=location)
    return Response(content=body, media_type="text/calendar",
                    headers={"Content-Disposition": 'attachment; filename="event.ics"'})


# --- serve the PWA frontend (single deployable unit) ------------------------
# The static files live in cityscope/web/. Serving them from the same app means
# one URL, no CORS, and the simplest possible deploy. API routes are declared
# above, so they take precedence; everything else falls through to the SPA.
import os
from fastapi.staticfiles import StaticFiles

_WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web")
if os.path.isdir(_WEB_DIR):
    # html=True serves index.html at "/" and handles the manifest/sw/icons.
    app.mount("/", StaticFiles(directory=_WEB_DIR, html=True), name="web")
