"""Tests for the Bluesky source (mock mode + normalisation)."""

from cityscope.sources.bluesky_source import (
    BlueskySource, _normalise, _search_mock,
)


def test_mock_returns_posts():
    posts = _search_mock("Austin")
    assert len(posts) > 0
    assert all(p.origin == "bluesky" for p in posts)
    assert all("Austin" in p.body for p in posts)


def test_mock_is_deterministic():
    a = _search_mock("Denver")
    b = _search_mock("Denver")
    assert [p.id for p in a] == [p.id for p in b]


def test_source_fetch_mock_mode():
    # default settings: live bluesky off -> mock
    src = BlueskySource()
    res = src.fetch("Seattle")
    assert res.status == "ok"
    assert len(res.posts) > 0
    assert res.source == "bluesky"


def test_source_empty_city():
    src = BlueskySource()
    res = src.fetch("")
    assert res.status == "none"
    assert res.posts == []


def test_normalise_real_shape():
    # a realistic AT Protocol searchPosts item
    item = {
        "uri": "at://did:plc:abc/app.bsky.feed.post/xyz123",
        "author": {"handle": "alice.bsky.social"},
        "record": {"text": "warehouse show in Austin tonight, doors at 9",
                   "createdAt": "2026-06-21T02:30:00.000Z"},
        "likeCount": 14,
        "replyCount": 3,
    }
    p = _normalise(item, "Austin")
    assert p is not None
    assert p.origin == "bluesky"
    assert p.author == "alice.bsky.social"
    assert p.score == 14
    assert p.num_comments == 3
    assert "xyz123" in p.url
    assert "alice.bsky.social" in p.url


def test_normalise_skips_empty_text():
    item = {"uri": "at://x/y/z", "author": {"handle": "h"},
            "record": {"text": "   "}}
    assert _normalise(item, "Austin") is None
