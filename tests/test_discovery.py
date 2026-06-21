"""Tests for subreddit discovery, incl. nicknames and collisions."""

from cityscope.sources.discovery import discover
from cityscope.sources.mock_reddit_index import MockRedditSearch

BE = MockRedditSearch()


def test_exact_city_match():
    r = discover(BE, "Asheville")
    assert r["status"] == "ok"
    assert "asheville" in [s.lower() for s in r["subreddits"]]


def test_nickname_bullcity_found():
    r = discover(BE, "Durham")
    names = [s.lower() for s in r["subreddits"]]
    assert "bullcity" in names                 # nickname surfaced
    assert names[0] == "bullcity"              # and ranked first (bigger)


def test_nickname_nola():
    r = discover(BE, "New Orleans")
    assert any(s.upper() == "NOLA" for s in r["subreddits"])


def test_collision_is_ambiguous():
    r = discover(BE, "Portland")
    assert r["status"] == "ambiguous"
    regions = {a["region"] for a in r["alternatives"]}
    assert regions == {"OR", "ME"}


def test_collision_resolved_by_region():
    r = discover(BE, "Portland", region="ME")
    assert r["status"] == "ok"
    assert any("maine" in s.lower() for s in r["subreddits"])


def test_quiet_small_town():
    r = discover(BE, "Marfa")
    assert r["status"] == "quiet"
    assert r["subreddits"] == ["Marfa"]


def test_no_community():
    r = discover(BE, "Wakanda")
    assert r["status"] == "none"
    assert r["subreddits"] == []


def test_rejects_sports_team():
    # "Portland" search includes TrailBlazers; it must never be selected
    r = discover(BE, "Portland", region="OR")
    assert all("blazers" not in s.lower() for s in r["subreddits"])


def test_topical_subs_for_big_city():
    r = discover(BE, "Austin")
    names = [s.lower() for s in r["subreddits"]]
    assert "austin" in names
    assert any(n.startswith("austin") and n != "austin" for n in names)
