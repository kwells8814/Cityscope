"""Tests for the classification + ranking pipeline."""

import time

from cityscope.models import RawPost
from cityscope import pipeline


def _post(title, body="", score=100, comments=10, origin="reddit", age_h=5):
    return RawPost(
        id="t1", source_label="Austin", title=title, body=body,
        url="https://x", score=score, num_comments=comments,
        created_utc=time.time() - age_h * 3600, author="u", origin=origin,
    )


def test_event_classified():
    cat, conf = pipeline.classify_keyword(
        _post("Free outdoor movie night this Saturday", "Doors 8:30pm, free entry"))
    assert cat == "event"
    assert conf >= 0.5


def test_gem_classified():
    cat, _ = pipeline.classify_keyword(
        _post("Hidden gem: tiny ramen counter with no sign", "Nobody knows about it"))
    assert cat == "gem"


def test_question_is_noise():
    cat, _ = pipeline.classify_keyword(
        _post("What's the best taco spot right now?", "Settle the debate"))
    assert cat == "noise"


def test_rant_is_noise():
    cat, _ = pipeline.classify_keyword(
        _post("Why is traffic always this bad??", "Rant over"))
    assert cat == "noise"


def test_process_filters_noise_and_ranks():
    posts = [
        _post("Hidden gem ramen counter no sign", "nobody knows", score=500),
        _post("Why is traffic so bad??", "rant"),  # noise -> dropped
        _post("Free movie night Saturday", "doors 8pm free", score=200),
    ]
    out = pipeline.process(posts)
    assert len(out) == 2                         # noise dropped
    assert out[0].rank_score >= out[1].rank_score  # sorted by rank


def test_extract_when_and_free():
    out = pipeline.process([_post("Show Friday", "doors 10pm, free entry")])
    assert out and out[0].when and "Friday" in out[0].when
    assert out[0].is_free is True


def test_rss_source_label_not_prefixed():
    p = _post("Gallery crawl Friday night", "free, 6-10pm", origin="rss")
    p.source_label = "Austin Chronicle"
    out = pipeline.process([p])
    assert out and out[0].source == "Austin Chronicle"   # no r/ prefix
    assert out[0].origin == "rss"


def test_reddit_source_label_prefixed():
    out = pipeline.process([_post("Free movie night Saturday", "doors 8pm free")])
    assert out and out[0].source.startswith("r/")


def test_category_filter():
    posts = [
        _post("Hidden gem no sign ramen", "nobody knows", score=500),
        _post("Free movie night Saturday", "doors 8pm free", score=200),
    ]
    out = pipeline.process(posts, categories={"gem"})
    assert all(h.category == "gem" for h in out)
    assert len(out) == 1
