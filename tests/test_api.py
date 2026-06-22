"""API tests — run with: pytest (requires fastapi, httpx installed).

These use FastAPI's TestClient. They're skipped automatically if fastapi isn't
installed, so the rest of the suite still runs in a minimal environment.
"""

import pytest

try:
    from fastapi.testclient import TestClient
    from cityscope.api.app import app
    client = TestClient(app)
    HAVE_FASTAPI = True
except Exception:
    HAVE_FASTAPI = False

pytestmark = pytest.mark.skipif(not HAVE_FASTAPI, reason="fastapi not installed")


def test_status():
    # /status is the primary endpoint (renamed from /health to dodge ad blockers)
    r = client.get("/status")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert "db_enabled" in body
    assert "cache" in body


def test_health_alias_still_works():
    # /health kept as a backward-compatible alias
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_resolve_zip():
    r = client.get("/resolve", params={"zip": "28801"})
    assert r.status_code == 200
    assert r.json()["city"] == "Asheville"


def test_happenings_ok():
    r = client.get("/happenings", params={"city": "Austin"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert len(body["happenings"]) > 0


def test_happenings_ambiguous():
    r = client.get("/happenings", params={"city": "Portland"})
    assert r.status_code == 200
    assert r.json()["status"] == "ambiguous"


def test_happenings_missing_city():
    r = client.get("/happenings")
    assert r.status_code == 422       # FastAPI validation


def test_happenings_bad_category():
    r = client.get("/happenings", params={"city": "Austin", "categories": "concerts"})
    assert r.status_code == 400


def test_happenings_category_filter():
    r = client.get("/happenings", params={"city": "Austin", "categories": "gem"})
    assert r.status_code == 200
    assert all(h["category"] == "gem" for h in r.json()["happenings"])


def test_ics_download():
    r = client.get("/ics", params={"title": "Movie night", "when": "Saturday 8:30pm"})
    assert r.status_code == 200
    assert "text/calendar" in r.headers["content-type"]
    assert r.text.startswith("BEGIN:VCALENDAR")
