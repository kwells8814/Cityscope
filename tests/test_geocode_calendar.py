"""Tests for geocoding and .ics calendar generation."""

import datetime as dt

from cityscope import geocode
from cityscope import calendar as cal


# --- geocode ---

def test_city_passthrough():
    r = geocode.resolve(city="Asheville")
    assert r["city"] == "Asheville"


def test_zip_known():
    r = geocode.resolve(zip_code="28801")
    assert r["city"] == "Asheville" and r["region"] == "NC"


def test_zip_collision_maine():
    r = geocode.resolve(zip_code="04101")
    assert r["city"] == "Portland" and r["region"] == "ME"


def test_zip_unknown():
    r = geocode.resolve(zip_code="00000")
    assert r["city"] is None
    assert "not recognized" in r["note"]


def test_gps_nearest():
    r = geocode.resolve(lat=35.99, lng=-78.90)   # Durham
    assert r["city"] == "Durham"


# --- calendar ---

def _sunday_noon():
    return dt.datetime(2026, 6, 21, 12, 0)   # a Sunday


def test_ics_timed_event():
    ics = cal.build_ics(title="Movie", when="Saturday 8:30pm", now=_sunday_noon())
    assert "BEGIN:VCALENDAR" in ics
    assert "DTSTART:20260627T203000" in ics    # next Saturday 20:30
    assert "DTEND:20260627T223000" in ics      # +2h


def test_ics_tonight():
    ics = cal.build_ics(title="Show", when="Tonight 10pm", now=_sunday_noon())
    assert "DTSTART:20260621T220000" in ics


def test_ics_all_day_when_no_time():
    ics = cal.build_ics(title="Market", when="this weekend", now=_sunday_noon())
    assert "DTSTART;VALUE=DATE:20260627" in ics
    assert "Time approximate" in ics


def test_ics_escapes_special_chars():
    ics = cal.build_ics(title="Wine, cheese; fun", when="Friday", now=_sunday_noon())
    assert "Wine\\, cheese\\; fun" in ics


def test_parse_when_no_anchor():
    start, has_time = cal.parse_when("", now=_sunday_noon())
    assert start is None and has_time is False
